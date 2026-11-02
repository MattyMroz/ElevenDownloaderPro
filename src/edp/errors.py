"""EDP error hierarchy: retryable and permanent failures with structured context."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

__all__ = [
    "EdpError",
    "ErrorCode",
    "ErrorContext",
    "FatalError",
    "TransientError",
    "TtsAuthError",
    "TtsCancelledError",
    "TtsClipValidationError",
    "TtsConfigError",
    "TtsError",
    "TtsInputError",
    "TtsProviderUnavailableError",
    "TtsQuotaError",
    "TtsRateLimitError",
    "TtsTimeoutError",
    "TtsVoiceError",
]


class ErrorCode(StrEnum):
    """Enumerated error codes."""

    # Generic
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"

    # Input / IO
    IO_ERROR = "IO_ERROR"

    # TTS
    TTS_FAILED = "TTS_FAILED"
    TTS_AUTH_FAILED = "TTS_AUTH_FAILED"
    TTS_CONFIG_INVALID = "TTS_CONFIG_INVALID"
    TTS_ENGINE_UNAVAILABLE = "TTS_ENGINE_UNAVAILABLE"
    TTS_INPUT_INVALID = "TTS_INPUT_INVALID"
    TTS_CLIP_INVALID = "TTS_CLIP_INVALID"
    TTS_QUOTA_EXHAUSTED = "TTS_QUOTA_EXHAUSTED"
    TTS_RATE_LIMITED = "TTS_RATE_LIMITED"
    TTS_TIMEOUT = "TTS_TIMEOUT"
    TTS_VOICE_INVALID = "TTS_VOICE_INVALID"


@dataclass(frozen=True, slots=True)
class ErrorContext:
    """Structured error metadata — code + message + suggestion + docs link."""

    code: ErrorCode
    message: str
    suggestion: str = ""
    docs_url: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class EdpError(Exception):
    """Base exception for all EDP errors."""

    def __init__(
        self,
        message: str = "",
        *,
        context: ErrorContext | None = None,
    ) -> None:
        """Initialise with an optional plain *message* or structured *context*."""
        if context and not message:
            message = context.message
        super().__init__(message)
        self.context = context or ErrorContext(
            code=ErrorCode.UNKNOWN,
            message=message,
        )


class TransientError(EdpError):
    """Base class for retryable errors (network, rate-limit, timeout)."""


class FatalError(EdpError):
    """Base class for non-retryable errors (config, missing binary, bad input)."""


class TtsError(EdpError):
    """Base class for every TTS-domain failure."""

    error_code: ClassVar[ErrorCode] = ErrorCode.TTS_FAILED

    def __init__(
        self,
        message: str = "",
        *,
        context: ErrorContext | None = None,
    ) -> None:
        """Initialize a TTS error with its specific default error code."""
        resolved_context: ErrorContext = context or ErrorContext(
            code=self.error_code,
            message=message,
        )
        super().__init__(message, context=resolved_context)


class TtsConfigError(TtsError, FatalError):
    """Invalid TTS configuration."""

    error_code = ErrorCode.TTS_CONFIG_INVALID


class TtsAuthError(TtsError, FatalError):
    """Missing or rejected TTS provider credentials."""

    error_code = ErrorCode.TTS_AUTH_FAILED


class TtsVoiceError(TtsError, FatalError):
    """Unknown, unavailable, or incompatible voice."""

    error_code = ErrorCode.TTS_VOICE_INVALID


class TtsInputError(TtsError, FatalError):
    """Invalid text or synthesis request contract."""

    error_code = ErrorCode.TTS_INPUT_INVALID


class TtsQuotaError(TtsError, FatalError):
    """Provider account has no synthesis credits left."""

    error_code = ErrorCode.TTS_QUOTA_EXHAUSTED


class TtsClipValidationError(TtsError, TransientError):
    """Provider output is empty, corrupt, or not decodable."""

    error_code = ErrorCode.TTS_CLIP_INVALID


class TtsCancelledError(TtsError, FatalError):
    """TTS operation cancelled by its caller."""

    error_code = ErrorCode.CANCELLED


class TtsRateLimitError(TtsError, TransientError):
    """Provider rate limit reached."""

    error_code = ErrorCode.TTS_RATE_LIMITED

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_s: float | None = None,
        context: ErrorContext | None = None,
    ) -> None:
        """Initialize a rate-limit error with an optional retry delay."""
        self.retry_after_s: float | None = retry_after_s
        super().__init__(message, context=context)


class TtsTimeoutError(TtsError, TransientError):
    """Provider or worker request timed out."""

    error_code = ErrorCode.TTS_TIMEOUT


class TtsProviderUnavailableError(TtsError, TransientError):
    """Provider is temporarily unavailable."""

    error_code = ErrorCode.TTS_ENGINE_UNAVAILABLE

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_s: float | None = None,
        context: ErrorContext | None = None,
    ) -> None:
        """Initialize an availability error with an optional retry delay."""
        self.retry_after_s: float | None = retry_after_s
        super().__init__(message, context=context)
