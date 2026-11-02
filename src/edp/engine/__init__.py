"""ElevenReader engine package; importing it does not load Playwright."""

from __future__ import annotations

from .api_backend import read_session, sign_in
from .config import ElevenReaderConfig, find_chrome, resolve_voice
from .constants import DEFAULT_VOICE_ALIAS, MAX_DOCUMENT_CHARS, MAX_PARALLEL_DOCUMENTS, VOICES
from .hub import CLEANUP_WARNING
from .service import ElevenReaderTtsEngine
from .types import (
    DocumentPart,
    DocumentResult,
    DocumentSynthesisRequest,
    ElevenReaderVoice,
    PartTiming,
    SessionRecord,
    SignInOutcome,
)

__all__ = [
    "CLEANUP_WARNING",
    "DEFAULT_VOICE_ALIAS",
    "MAX_DOCUMENT_CHARS",
    "MAX_PARALLEL_DOCUMENTS",
    "VOICES",
    "DocumentPart",
    "DocumentResult",
    "DocumentSynthesisRequest",
    "ElevenReaderConfig",
    "ElevenReaderTtsEngine",
    "ElevenReaderVoice",
    "PartTiming",
    "SessionRecord",
    "SignInOutcome",
    "find_chrome",
    "read_session",
    "resolve_voice",
    "sign_in",
]
