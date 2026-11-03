"""ElevenDownloaderPro: record ElevenReader speech as MP3 with part timings, word timings and subtitles."""

from __future__ import annotations

from edp.engine import VOICES, SessionRecord, SignInOutcome, read_session
from edp.errors import EdpError, FatalError, TransientError
from edp.reading import RecordResult, default_home, download, record, sign_in

__all__ = [
    "VOICES",
    "EdpError",
    "FatalError",
    "RecordResult",
    "SessionRecord",
    "SignInOutcome",
    "TransientError",
    "default_home",
    "download",
    "read_session",
    "record",
    "sign_in",
]
