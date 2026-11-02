"""Thread-safe cancellation shared by sync and async callers."""

from __future__ import annotations

import asyncio
import threading
from contextlib import suppress

__all__ = ["Cancellation"]


class Cancellation:
    """One run-scoped cancellation token shared by sync and async callers."""

    __slots__ = ("_event", "_lock", "_waiters")

    def __init__(self) -> None:
        """Create a token that is not cancelled yet."""
        self._event: threading.Event = threading.Event()
        self._lock: threading.Lock = threading.Lock()
        self._waiters: dict[asyncio.Future[None], asyncio.AbstractEventLoop] = {}

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation was requested."""
        return self._event.is_set()

    async def wait(self) -> None:
        """Wait without binding the thread-safe event to one event loop."""
        if self._event.is_set():
            return
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        waiter: asyncio.Future[None] = loop.create_future()
        with self._lock:
            if self._event.is_set():
                return
            self._waiters[waiter] = loop
        try:
            await waiter
        finally:
            with self._lock:
                self._waiters.pop(waiter, None)

    def cancel(self) -> None:
        """Request cancellation and wake every waiter."""
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            waiters: tuple[tuple[asyncio.Future[None], asyncio.AbstractEventLoop], ...] = tuple(
                self._waiters.items(),
            )
            self._waiters.clear()
        for waiter, loop in waiters:
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(_resolve_waiter, waiter)


def _resolve_waiter(waiter: asyncio.Future[None]) -> None:
    if not waiter.done():
        waiter.set_result(None)
