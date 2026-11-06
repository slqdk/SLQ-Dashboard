"""Keep go2rtc's streams in step with the cameras, and fetch pictures from it.

Each camera is two streams: `cam<id>` is its full picture (stream1), and
`cam<id>_lo` its small one (stream2), which is what the overview and the grid use.
They are sent with PATCH: a PUT would also write the login into go2rtc's config
file, in plain text. This way it stays in go2rtc's memory and the job sends it
again if go2rtc restarts. PATCH leaves a stream that is playing alone.

Nothing about a failed request is passed on but the type of the error, because
the text of an httpx error can hold the address, and so the login.
"""
from __future__ import annotations

import re
import time
from typing import AsyncIterator

import httpx

from ...core import settings
from . import store

TIMEOUT = 10.0
FRAME_CACHE = "2s"          # go2rtc answers from this, so viewers share a frame
STALL_SECONDS = 30.0        # a live stream with no data this long is over
LIVE_SECONDS = 1800         # a login is checked once, so a live view has an end
STREAMS = {"lo": ("_lo", "stream2"), "hi": ("", "stream1")}
OURS = re.compile(r"^cam\d+(_lo)?$")

_status: dict = {"ok": False, "text": ""}


class NoPicture(RuntimeError):
    """go2rtc gave no picture; the text is shown to the person."""


def reset() -> None:
    _status.update(ok=False, text="")


def _base() -> str:
    return (settings.load().get("go2rtcUrl") or "").rstrip("/")


def _name(camera_id: int, size: str) -> str:
    return f"cam{camera_id}{STREAMS[size][0]}"


def job() -> None:
    base = _base()
    cameras = store.all_cameras()
    if not base:
        _status.update(ok=False, text="Adressen til go2rtc mangler.")
        return
    wanted = {_name(c["id"], size): store.source(c["id"], STREAMS[size][1]) for c in cameras for size in STREAMS}
    try:
        for name, source in wanted.items():
            httpx.patch(f"{base}/api/streams", params={"name": name, "src": source},
                        timeout=TIMEOUT).raise_for_status()
        present = httpx.get(f"{base}/api/streams", timeout=TIMEOUT).json()
        for name in present:
            if OURS.match(name) and name not in wanted:
                httpx.delete(f"{base}/api/streams", params={"src": name}, timeout=TIMEOUT)
    except (httpx.HTTPError, ValueError) as exc:
        _status.update(ok=False, text=f"go2rtc svarer ikke ({type(exc).__name__}).")
        return
    count = len(cameras)
    _status.update(ok=bool(count), text=f"go2rtc svarer, {count} {'kamera' if count == 1 else 'kameraer'} sat op.")


def frame(camera_id: int, size: str) -> bytes:
    base = _base()
    if size not in STREAMS or not base or not store.source(camera_id, "stream1"):
        raise NoPicture("Kameraet er ikke sat op.")
    try:
        r = httpx.get(f"{base}/api/frame.jpeg", params={"src": _name(camera_id, size), "cache": FRAME_CACHE},
                      timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise NoPicture(f"Intet billede ({type(exc).__name__}).") from None
    # go2rtc answers 200 with nothing when it cannot reach the camera.
    if r.status_code != 200 or not r.content:
        raise NoPicture("Kameraet svarer ikke.")
    return r.content


async def live(camera_id: int) -> tuple[str, AsyncIterator[bytes]]:
    """The full picture as the camera sends it: H.264 in fragmented MP4, nothing
    transcoded and no sound. Ends when the page goes away, or after LIVE_SECONDS."""
    base = _base()
    if not base or not store.source(camera_id, "stream1"):
        raise NoPicture("Kameraet er ikke sat op.")
    http = httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT, read=STALL_SECONDS))
    request = http.build_request("GET", f"{base}/api/stream.mp4",
                                 params={"src": _name(camera_id, "hi"), "video": "h264"})
    try:
        upstream = await http.send(request, stream=True)
    except httpx.HTTPError as exc:
        await http.aclose()
        raise NoPicture(f"Intet billede ({type(exc).__name__}).") from None
    if upstream.status_code != 200:
        await upstream.aclose()
        await http.aclose()
        raise NoPicture("Kameraet svarer ikke.")

    async def body() -> AsyncIterator[bytes]:
        ends = time.monotonic() + LIVE_SECONDS
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
                if time.monotonic() > ends:
                    break
        except httpx.HTTPError:
            pass
        finally:
            await upstream.aclose()
            await http.aclose()

    return upstream.headers.get("content-type", "video/mp4"), body()


def overview(_me: dict) -> dict:
    return {"cameras": [{"id": c["id"], "name": c["name"]} for c in store.all_cameras()]}


def setup_status() -> dict:
    if _status["text"]:
        return dict(_status)
    return {"ok": False, "text": "Ingen kameraer sat op." if not store.all_cameras() else "Venter på go2rtc."}
