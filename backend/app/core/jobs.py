"""Background work: each section's jobs in their own daemon thread.

A job that fails is logged and tried again at its next turn; one slow upstream
never holds up another section. APP_NO_JOBS=1 turns them off (the tests).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

from . import logs
from ..meta import APP_ID

log = logging.getLogger(APP_ID)
_stop = threading.Event()
_threads: list[threading.Thread] = []
_wakes: list[threading.Event] = []


def _loop(name: str, seconds: float, fn: Callable[[], None], wake: threading.Event) -> None:
    while not _stop.is_set():
        started = time.monotonic()
        try:
            fn()
        except Exception as exc:            # a job must never kill its thread
            logs.record_exception(exc, f"job {name}")
        wake.wait(max(1.0, seconds - (time.monotonic() - started)))
        wake.clear()


def kick() -> None:
    """Run every job now instead of at its next turn: Admin just changed
    something, and the page should show it without waiting ten minutes."""
    for wake in _wakes:
        wake.set()


def start() -> None:
    if os.environ.get("APP_NO_JOBS"):
        return
    from ..sections import SECTIONS
    from . import netwatch
    _stop.clear()
    work = [("netwatch", 30.0, netwatch.job)]
    for section in SECTIONS:
        for index, (seconds, fn) in enumerate(section.jobs):
            work.append((f"{section.id}.{index}", seconds, fn))
    for name, seconds, fn in work:
        wake = threading.Event()
        t = threading.Thread(target=_loop, args=(name, seconds, fn, wake), name=name, daemon=True)
        t.start()
        _threads.append(t)
        _wakes.append(wake)
    log.info("started %d background jobs", len(_threads))


def stop() -> None:
    _stop.set()
    kick()
    _threads.clear()
    _wakes.clear()
