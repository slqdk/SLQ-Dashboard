"""Links' API, under /api/s/links. Everything is the signed-in person's own."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from . import store

router = APIRouter(prefix="/api/s/links", tags=["links"])


def _guarded(fn, *args):
    try:
        return fn(*args)
    except store.Problem as exc:
        raise HTTPException(400, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.get("/tree")
def tree(request: Request):
    return store.tree(request.state.user["id"])


@router.post("/folders")
def add_folder(body: dict, request: Request):
    return _guarded(store.add_folder, request.state.user["id"], body.get("name"), body.get("parentId"))


@router.patch("/folders/{folder_id}")
def update_folder(folder_id: int, body: dict, request: Request):
    _guarded(store.update_folder, request.state.user["id"], folder_id, body)
    return {"ok": True}


@router.get("/folders/{folder_id}/size")
def folder_size(folder_id: int, request: Request):
    return _guarded(store.folder_size, request.state.user["id"], folder_id)


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, request: Request):
    _guarded(store.delete_folder, request.state.user["id"], folder_id)
    return {"ok": True}


@router.post("/items")
def add_link(body: dict, request: Request):
    return _guarded(store.add_link, request.state.user["id"], body)


@router.patch("/items/{link_id}")
def update_link(link_id: int, body: dict, request: Request):
    return _guarded(store.update_link, request.state.user["id"], link_id, body)


@router.delete("/items/{link_id}")
def delete_link(link_id: int, request: Request):
    _guarded(store.delete_link, request.state.user["id"], link_id)
    return {"ok": True}
