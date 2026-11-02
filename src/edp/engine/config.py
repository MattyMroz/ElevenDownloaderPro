"""Validated configuration for the ElevenReader engine."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Final

from edp.errors import ErrorCode, ErrorContext, TtsVoiceError

from .constants import CHROME_LOCATIONS, CHROME_STEM, VOICES
from .types import ElevenReaderVoice

__all__ = ["ElevenReaderConfig", "find_chrome", "profile_dir", "resolve_voice", "session_file"]

# ── Constants ─────────────────────────────────────────────────────────────────

_PROFILE_DIR_NAME: Final[str] = "chrome-profile"
"""Chrome user data directory inside the ElevenReader root."""

_SESSION_FILE_NAME: Final[str] = "session.json"
"""Last session check result inside the ElevenReader root."""


@dataclass(frozen=True, slots=True)
class ElevenReaderConfig:
    """Voice and home directory of one ElevenReader engine."""

    voice: ElevenReaderVoice
    profile_root: Path


def profile_dir(root: Path) -> Path:
    """Return the Chrome user data directory under the ElevenReader *root*."""
    return root / _PROFILE_DIR_NAME


def session_file(root: Path) -> Path:
    """Return the session check record under the ElevenReader *root*."""
    return root / _SESSION_FILE_NAME


def find_chrome() -> Path | None:
    """Return the Google Chrome executable from a standard install location, then from ``PATH``, or None."""
    for variable, relative in CHROME_LOCATIONS:
        root: str = os.environ.get(variable, "")
        if not root:
            continue
        candidate: Path = Path(root) / relative
        if candidate.is_file():
            return candidate
    found: str | None = which(CHROME_STEM)
    return Path(found) if found else None


def resolve_voice(alias_or_id: str) -> ElevenReaderVoice:
    """Return the offered voice named by alias (any case) or provider voice id."""
    wanted: str = alias_or_id.strip()
    by_alias: ElevenReaderVoice | None = VOICES.get(wanted.casefold())
    if by_alias is not None:
        return by_alias
    for voice in VOICES.values():
        if voice.voice_id == wanted:
            return voice
    offered: str = ", ".join(VOICES)
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_VOICE_INVALID,
        message=f"Unknown ElevenReader voice. Offered: {offered}",
        suggestion=f"Choose one of the voices listed by `edp voices`: {offered}.",
        details={"voice_id": wanted},
    )
    raise TtsVoiceError(context=context)
