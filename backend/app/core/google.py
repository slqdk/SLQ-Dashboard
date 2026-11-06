"""Google Calendar, read only.

OAuth 2.0 authorization-code flow with one scope, calendar.readonly: the token
itself cannot write to Google, so "Google to log only" holds even if a bug
tries. Each person connects their own account; the client id and secret are
set once, in Admin → Opsætning.

Base addresses can be replaced from the environment for the test double
(tools/mock_upstreams.py). Tokens never appear in a log or an error text.
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from urllib.parse import quote, urlencode

import httpx

from . import settings

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
TIMEOUT = 30.0
STATE_SECONDS = 600


def _auth_url() -> str:
    return os.environ.get("APP_GOOGLE_AUTH_URL") or "https://accounts.google.com/o/oauth2/v2/auth"


def _token_url() -> str:
    return os.environ.get("APP_GOOGLE_TOKEN_URL") or "https://oauth2.googleapis.com/token"


def _api_base() -> str:
    return (os.environ.get("APP_GOOGLE_API_BASE")
            or "https://www.googleapis.com/calendar/v3").rstrip("/")


class GoogleError(RuntimeError):
    """A Google call failed. The text is safe to show and to log."""


class NeedsReconnect(GoogleError):
    """The refresh token was revoked or expired: the person must connect again."""


class SyncTokenGone(GoogleError):
    """410: the incremental sync token expired; a full sync is needed."""


def configured(s: dict | None = None) -> bool:
    s = s or settings.load()
    return bool(s.get("googleClientId") and s.get("googleClientSecret"))


# ---- the connect flow -------------------------------------------------------

_states: dict[str, tuple[int, float]] = {}
_states_lock = threading.Lock()


def new_state(uid: int) -> str:
    state = secrets.token_urlsafe(24)
    now = time.time()
    with _states_lock:
        for key in [k for k, (_u, t) in _states.items() if t < now]:
            del _states[key]
        _states[state] = (uid, now + STATE_SECONDS)
    return state


def take_state(state: str) -> int | None:
    """The user the state was made for; each state works once."""
    with _states_lock:
        item = _states.pop(state or "", None)
    if item is None or item[1] < time.time():
        return None
    return item[0]


def authorize_url(redirect_uri: str, state: str) -> str:
    return _auth_url() + "?" + urlencode({
        "client_id": settings.load()["googleClientId"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",      # a refresh token, so sync runs unattended
        "prompt": "consent",           # always hand one out, also on a reconnect
        "include_granted_scopes": "false",
        "state": state,
    })


def _post_token(data: dict) -> dict:
    s = settings.load()
    body = {"client_id": s["googleClientId"], "client_secret": s["googleClientSecret"], **data}
    try:
        r = httpx.post(_token_url(), data=body, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise GoogleError(f"Kunne ikke nå Google ({type(exc).__name__}).") from None
    if r.status_code == 200:
        return r.json()
    try:
        code = r.json().get("error", "")
    except ValueError:
        code = ""
    if code == "invalid_grant":
        raise NeedsReconnect("Google afviste forbindelsen. Forbind kontoen igen.")
    raise GoogleError(f"Google svarede {r.status_code} {code}".strip() + ".")


def exchange_code(code: str, redirect_uri: str) -> dict:
    """Authorization code → {access_token, refresh_token?, expires_in}."""
    return _post_token({"code": code, "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code"})


def access_token(refresh_token: str) -> str:
    """A fresh access token. Access tokens are never stored."""
    data = _post_token({"refresh_token": refresh_token, "grant_type": "refresh_token"})
    return data["access_token"]


# ---- reading ------------------------------------------------------------------

def _get(path: str, token: str, params: dict | None = None) -> dict:
    try:
        r = httpx.get(_api_base() + path, params=params,
                      headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise GoogleError(f"Kunne ikke nå Google ({type(exc).__name__}).") from None
    if r.status_code == 410:
        raise SyncTokenGone("Synkroniseringen skal startes forfra.")
    if r.status_code == 401:
        raise NeedsReconnect("Google afviste adgangen. Forbind kontoen igen.")
    if r.status_code != 200:
        raise GoogleError(f"Google svarede {r.status_code}.")
    return r.json()


def calendars(token: str) -> list[dict]:
    """The person's calendars: [{id, summary, primary, color}]."""
    out: list[dict] = []
    page: str | None = None
    while True:
        params = {"maxResults": 250, **({"pageToken": page} if page else {})}
        data = _get("/users/me/calendarList", token, params)
        for c in data.get("items", []):
            out.append({"id": c["id"], "summary": c.get("summaryOverride") or c.get("summary") or c["id"],
                        "primary": bool(c.get("primary")), "color": c.get("backgroundColor") or ""})
        page = data.get("nextPageToken")
        if not page:
            return out


def events(token: str, calendar_id: str, sync_token: str | None) -> tuple[list[dict], str | None]:
    """Everything that changed since `sync_token`, or all events without one.

    singleEvents expands recurring events into one entry each, with stable
    ids; showDeleted brings the cancelled ones, so the log can mark them."""
    out: list[dict] = []
    page: str | None = None
    path = f"/calendars/{quote(calendar_id, safe='')}/events"
    while True:
        params: dict = {"singleEvents": "true", "showDeleted": "true", "maxResults": 2500}
        if sync_token:
            params["syncToken"] = sync_token
        if page:
            params["pageToken"] = page
        data = _get(path, token, params)
        out.extend(data.get("items", []))
        page = data.get("nextPageToken")
        if not page:
            return out, data.get("nextSyncToken")
