"""SLQ Dashboard's FastAPI app: accounts, Admin, the overview, every section.

The shell is small on purpose, as in FamilyLog: what a section does lives in
its package (app/sections/<id>/); this file wires them in from the registry
and keeps the rules that hold for all of them - the session check, section
access, admin-only setup.
"""
from __future__ import annotations

import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .core import auth, db, jobs, logs, netwatch, settings
from .meta import APP_DISPLAY_NAME, APP_ID, APP_VERSION
from .sections import SECTIONS
from .sections.calendar.routes import callback_router, redirect_uri
from .sections.familylog import client as familylog
from .sections.latenight import store as latenight

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logs.setup()
    ran = db.init_db()
    if ran:
        import logging
        logging.getLogger(APP_ID).info("migrations applied: %s", "; ".join(ran))
    settings.apply_timezone()
    latenight.load_seed()
    jobs.start()
    yield
    jobs.stop()


app = FastAPI(title=APP_DISPLAY_NAME, version=APP_VERSION, lifespan=lifespan)

# ---------- authentication ----------
# Everything under /api needs a session except these.
PUBLIC_PATHS = {"/api/auth/status", "/api/auth/setup", "/api/auth/login",
                "/api/auth/logout", "/api/meta"}
SECTION_PATH = re.compile(r"^/api/s/([a-z0-9_-]+)(?:/|$)")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api") or path in PUBLIC_PATHS:
        return await call_next(request)
    me = auth.session_user(request.cookies.get(auth.SESSION_COOKIE))
    if not me:
        return JSONResponse({"detail": "Ikke logget ind."}, status_code=401)
    if path.startswith("/api/admin") and me["role"] != "admin":
        return JSONResponse({"detail": "Kun for administrator."}, status_code=403)
    match = SECTION_PATH.match(path)
    if match and match.group(1) not in auth.sections_of(me):
        return JSONResponse({"detail": "Du har ikke adgang til denne sektion."}, status_code=403)
    request.state.user = me
    return await call_next(request)


def _is_secure(request: Request) -> bool:
    """True when the browser reached us over HTTPS, directly or via the proxy."""
    proto = request.headers.get("x-forwarded-proto", "")
    return request.url.scheme == "https" or proto.split(",")[0].strip() == "https"


def set_session_cookie(response: Response, token: str, secure: bool) -> None:
    response.set_cookie(auth.SESSION_COOKIE, token, max_age=auth.SESSION_DAYS * 86400,
                        httponly=True, samesite="lax", secure=secure, path="/")


class Credentials(BaseModel):
    username: str
    password: str


class PasswordBody(BaseModel):
    password: str


def me_dto(me: dict) -> dict:
    return {**me, "sections": auth.sections_of(me)}


@app.get("/api/meta")
def meta():
    return {"name": APP_DISPLAY_NAME, "version": APP_VERSION}


@app.get("/api/auth/status")
def auth_status(request: Request):
    me = auth.session_user(request.cookies.get(auth.SESSION_COOKIE))
    return {"needsSetup": auth.user_count() == 0, "user": me_dto(me) if me else None}


@app.post("/api/auth/setup")
def auth_setup(body: Credentials, response: Response, request: Request):
    """First run: the first account is the admin."""
    if auth.user_count() > 0:
        raise HTTPException(400, "Allerede sat op.")
    try:
        user = auth.create_user(body.username, body.password, "admin")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    set_session_cookie(response, auth.create_session(user["id"]), _is_secure(request))
    return {"user": me_dto(user)}


@app.post("/api/auth/login")
def auth_login(body: Credentials, response: Response, request: Request):
    token, error = auth.login(body.username, body.password)
    if error:
        raise HTTPException(401, error)
    set_session_cookie(response, token, _is_secure(request))
    return {"user": me_dto(auth.session_user(token))}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    auth.revoke_session(request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"ok": True}


@app.patch("/api/me/password")
def my_password(body: PasswordBody, request: Request):
    try:
        auth.set_password(request.state.user["id"], body.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


# ---------- the ping indicator ----------

@app.get("/api/ping")
def ping():
    """As small as a request gets: the browser times the round trip, so this
    measures the way from wherever the person is logged on from."""
    return {"t": time.time()}


@app.get("/api/netstatus")
def netstatus():
    return netwatch.status()


# ---------- the overview ----------

@app.get("/api/overview")
def overview(request: Request):
    """Every section the person may open, from what is already here."""
    me = request.state.user
    allowed = set(auth.sections_of(me))
    blocks: dict[str, dict] = {}
    for s in SECTIONS:
        if s.id not in allowed or s.overview is None:
            continue
        try:
            blocks[s.id] = s.overview(me)
        except Exception as exc:                 # one section must not take the page down
            logs.record_exception(exc, f"overview: {s.id}")
            blocks[s.id] = {"error": "Sektionen kunne ikke læses."}
    return {"serverTime": db.utcnow(), "blocks": blocks}


# ---------- Admin: users ----------

class NewUser(BaseModel):
    username: str
    password: str
    role: str = auth.FAMILY_ROLE
    name: str = ""


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    sections: list[str] | None = None


class KeyBody(BaseModel):
    key: str | None = None


def _user_row(u: dict, online: set[int]) -> dict:
    return {**u, "sections": auth.sections_of(u), "online": u["id"] in online,
            "familylogKey": familylog.key_hint(u["id"])}


def _online() -> set[int]:
    return {s["userId"] for s in auth.active_sessions()}


@app.get("/api/admin/users")
def admin_users():
    online = _online()
    return [_user_row(u, online) for u in auth.list_users()]


@app.post("/api/admin/users")
def admin_create_user(body: NewUser):
    try:
        u = auth.create_user(body.username, body.password, body.role, body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return _user_row(u, _online())


def _admins() -> int:
    return sum(1 for u in auth.list_users() if u["role"] == "admin")


@app.patch("/api/admin/users/{uid}")
def admin_update_user(uid: int, body: UserPatch, request: Request):
    target = auth.get_user(uid)
    if target is None:
        raise HTTPException(404, "Kontoen findes ikke.")
    try:
        if body.name is not None:
            auth.set_name(uid, body.name)
        if body.role is not None:
            if body.role not in auth.ROLES:
                raise ValueError("Ukendt rolle.")
            if target["role"] == "admin" and body.role != "admin" and _admins() <= 1:
                raise ValueError("Der skal være mindst én administrator.")
            auth.set_role(uid, body.role)
        if body.sections is not None:
            auth.set_sections(uid, body.sections)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return _user_row(auth.get_user(uid), _online())


@app.patch("/api/admin/users/{uid}/password")
def admin_password(uid: int, body: PasswordBody, request: Request):
    if auth.get_user(uid) is None:
        raise HTTPException(404, "Kontoen findes ikke.")
    try:
        auth.set_password(uid, body.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if uid != request.state.user["id"]:
        auth.revoke_user_sessions(uid)          # a new login with the new password
    return {"ok": True}


@app.put("/api/admin/users/{uid}/familylog-key")
def admin_familylog_key(uid: int, body: KeyBody):
    if auth.get_user(uid) is None:
        raise HTTPException(404, "Kontoen findes ikke.")
    familylog.set_key(uid, body.key)
    return {"familylogKey": familylog.key_hint(uid)}


@app.post("/api/admin/users/{uid}/sign-out")
def admin_sign_out(uid: int):
    auth.revoke_user_sessions(uid)
    return {"ok": True}


@app.delete("/api/admin/users/{uid}")
def admin_delete_user(uid: int, request: Request):
    if uid == request.state.user["id"]:
        raise HTTPException(400, "Du kan ikke slette din egen konto.")
    auth.delete_user(uid)
    for s in SECTIONS:
        if s.on_user_deleted:
            try:
                s.on_user_deleted(uid)
            except Exception as exc:             # the account is gone either way
                logs.record_exception(exc, f"{s.id}: cleaning up after a deleted account")
    return {"ok": True}


# ---------- Admin: setup ----------

def _setup_view(request: Request) -> dict:
    status = {}
    for s in SECTIONS:
        if s.setup:
            try:
                status[s.id] = s.setup()
            except Exception as exc:
                logs.record_exception(exc, f"setup status: {s.id}")
                status[s.id] = {"ok": False, "text": "Kunne ikke læses."}
    return {"settings": settings.public(), "status": status,
            "googleRedirectUri": redirect_uri(request), "version": APP_VERSION}


@app.get("/api/admin/setup")
def admin_setup(request: Request):
    return _setup_view(request)


@app.put("/api/admin/setup")
def admin_save_setup(body: dict, request: Request):
    try:
        settings.save(body)
    except settings.Invalid as exc:
        raise HTTPException(400, str(exc))
    jobs.kick()
    return _setup_view(request)


@app.get("/api/admin/log")
def admin_log():
    return {"recent": logs.recent(50), "tail": logs.tail(200)}


# ---------- the sections ----------

for _section in SECTIONS:
    app.include_router(_section.router)
app.include_router(callback_router)


@app.get("/api/sections")
def sections(request: Request):
    allowed = set(auth.sections_of(request.state.user))
    return [{"id": s.id, "title": s.title} for s in SECTIONS if s.id in allowed]


@app.get("/api/admin/sections")
def all_sections():
    return [{"id": s.id, "title": s.title, "familyDefault": s.family_default} for s in SECTIONS]


# ---------- the frontend ----------
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{rest:path}", include_in_schema=False)
    def spa(rest: str):
        if rest.startswith("api/"):
            raise HTTPException(404, "Findes ikke.")
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def _no_frontend():
        return PlainTextResponse(
            f"{APP_DISPLAY_NAME} {APP_VERSION}: the frontend is not built (no {STATIC_DIR}). "
            "Run `npm run build` in frontend/ and copy dist/ there, or use the container image.",
            status_code=503)
