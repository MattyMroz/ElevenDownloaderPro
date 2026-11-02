"""Tenacity retry presets for network calls.

- ``NETWORK_RETRY`` — HTTP / connection errors, 60 s budget (decorator).
- ``build_retry()`` — per-call ``AsyncRetrying`` for network engines with an
  attempt budget and a deterministic backoff shape (no jitter).

Usage within this utilities package:

    from ._retry import NETWORK_RETRY, build_retry

    @NETWORK_RETRY
    async def call_api() -> str: ...

    retrying = build_retry(max_attempts=4, backoff="linear", base_s=2.0, cap_s=5.0, retry_on=Exception)
    result = await retrying(fetch, arg)
"""

from __future__ import annotations

import asyncio
from typing import Final, Literal

from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    wait_random,
)
from tenacity.wait import wait_base

from .logger import get_logger

__all__ = ["NETWORK_RETRY", "build_retry"]

logger = get_logger(__name__)

# ── Optional HTTP-library imports (safe if not installed) ─────────────────────

try:
    import httpx as _httpx

    _HTTPX_RETRYABLE: tuple[type[Exception], ...] = (
        _httpx.TimeoutException,
        _httpx.ConnectError,
        _httpx.ReadError,
    )
    _HTTPX_STATUS_ERROR: type[Exception] | None = _httpx.HTTPStatusError
except ImportError:
    _HTTPX_RETRYABLE = ()
    _HTTPX_STATUS_ERROR = None

_RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})
"""HTTP status codes treated as transient and worth retrying."""

_NETWORK_BUDGET_SEC: Final[int] = 60
"""Max retry window for HTTP / connection errors."""

_NETWORK_MAX_WAIT_SEC: Final[int] = 15
"""Upper bound for exponential backoff on network retries."""


# ── Predicates ────────────────────────────────────────────────────────────────


def _is_retryable_network_error(exc: BaseException) -> bool:
    """Return True when *exc* is a retryable network / HTTP error."""
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    mro_names: set[str] = {cls.__name__ for cls in type(exc).__mro__}
    if "TransientError" in mro_names:
        return True
    # Optional download libraries signal terminal offline mode separately.
    if "DownloadError" in mro_names and "OfflineError" not in mro_names:
        return True
    if _HTTPX_RETRYABLE and isinstance(exc, _HTTPX_RETRYABLE):
        return True
    if _HTTPX_STATUS_ERROR and isinstance(exc, _HTTPX_STATUS_ERROR):
        response = getattr(exc, "response", None)
        return response is not None and response.status_code in _RETRYABLE_STATUS_CODES
    return False


def _log_before_retry(retry_state: RetryCallState) -> None:
    """Log each retry attempt with context."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    fn_name = getattr(retry_state.fn, "__name__", "?")
    logger.warning(
        "Network retry scheduled",
        attempt=retry_state.attempt_number,
        operation=fn_name,
        error_type=type(exc).__name__ if exc is not None else "unknown",
    )


# ── Presets ───────────────────────────────────────────────────────────────────

NETWORK_RETRY: Final = retry(
    retry=retry_if_exception(_is_retryable_network_error),
    stop=stop_after_delay(_NETWORK_BUDGET_SEC),
    wait=wait_exponential(multiplier=1, min=2, max=_NETWORK_MAX_WAIT_SEC) + wait_random(0, 2),
    before_sleep=_log_before_retry,
    reraise=True,
)
"""Network retry: HTTP / connection errors with exp backoff + jitter."""


# ── build_retry ───────────────────────────────────────────────────────────────

BackoffKind = Literal["linear", "exponential"]
"""Backoff growth shape for retry waits."""


class _BackoffWait(wait_base):
    """Compute backoff wait: linear = min(base*n, cap), exponential = base*2^(n-1)."""

    def __init__(self, kind: BackoffKind, base_s: float, cap_s: float | None) -> None:
        self._kind = kind
        self._base_s = base_s
        self._cap_s = cap_s

    def __call__(self, retry_state: RetryCallState) -> float:
        n = retry_state.attempt_number
        raw = self._base_s * n if self._kind == "linear" else self._base_s * (2 ** (n - 1))
        return raw if self._cap_s is None else min(raw, self._cap_s)


def build_retry(
    *,
    max_attempts: int,
    backoff: BackoffKind,
    base_s: float,
    cap_s: float | None = None,
    retry_on: type[BaseException] | tuple[type[BaseException], ...],
) -> AsyncRetrying:
    """Retry for network engines. ``max_attempts`` = TOTAL number of calls.

    Note:
        ``asyncio.sleep`` is passed by reference (late-binding) so tests that
        patch it via ``monkeypatch.setattr(asyncio, "sleep", ...)`` still take
        effect. Do NOT move it to a parameter default — that freezes the
        reference, and tenacity's own default (``_portable_async_sleep``) would
        bypass the monkeypatch.
    """
    return AsyncRetrying(
        sleep=asyncio.sleep,
        stop=stop_after_attempt(max_attempts),
        wait=_BackoffWait(backoff, base_s, cap_s),
        retry=retry_if_exception_type(retry_on),
        before_sleep=_log_before_retry,
        reraise=True,
    )
