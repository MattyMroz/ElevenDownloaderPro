"""Payload secret redaction for logs and event envelopes.

Single redaction rule: case-insensitive substring match against a
fixed set of known-sensitive key fragments. Used by:

* Event emitters before persisting payload rows.
* Logger scrubber and any caller that wants to render a dict safely.

The functions are pure — the input is never mutated; a freshly built
dict (and freshly built nested containers) is returned.
"""

from __future__ import annotations

from typing import Any, Final

__all__ = [
    "REDACTED_VALUE",
    "SECRET_KEY_FRAGMENTS",
    "sanitize_event_payload",
    "sanitize_secrets",
]

REDACTED_VALUE: Final[str] = "***REDACTED***"
"""Replacement value used for every redacted entry."""

SECRET_KEY_FRAGMENTS: Final[tuple[str, ...]] = (
    "password",
    "token",
    "api_key",
    "apikey",
    "secret",
    "authorization",
    "cookie",
    "private_key",
    "bearer",
)
"""Lower-cased substrings; any key containing one of these is redacted."""


def _key_is_secret(key: str) -> bool:
    """Return ``True`` if ``key`` contains a secret fragment (case-insensitive)."""
    lowered = key.lower()
    return any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS)


def _sanitize_value(value: Any) -> Any:
    """Recurse into containers; leave scalars unchanged."""
    if isinstance(value, dict):
        return sanitize_secrets(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def sanitize_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``payload`` with secret-looking keys redacted.

    Args:
        payload: Mapping that may contain credentials at any nesting depth.

    Returns:
        Fresh ``dict`` whose keys matching :data:`SECRET_KEY_FRAGMENTS`
        have their values replaced with :data:`REDACTED_VALUE`. Nested
        dicts and lists are sanitised recursively. The input is never
        mutated.
    """
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(key, str) and _key_is_secret(key):
            sanitized[key] = REDACTED_VALUE
        else:
            sanitized[key] = _sanitize_value(value)
    return sanitized


def sanitize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Semantic alias for :func:`sanitize_secrets`.

    Used at event-emit boundaries (e.g. :class:`DbEventEmitter`) to
    make the intent explicit at call sites that scrub event envelopes
    before persistence or fan-out.
    """
    return sanitize_secrets(payload)
