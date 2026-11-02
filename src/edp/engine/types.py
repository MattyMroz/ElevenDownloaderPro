"""Value types of the ElevenReader engine: document requests and results, account and stream state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime
    from pathlib import Path

__all__ = [
    "AccountCleanup",
    "AccountSettings",
    "AlignmentChunk",
    "DocumentPart",
    "DocumentResult",
    "DocumentSynthesisRequest",
    "DocumentTrace",
    "ElevenReaderVoice",
    "LibraryState",
    "PartTiming",
    "PlayerState",
    "SessionRecord",
    "SignInOutcome",
    "UploadedRead",
]


@dataclass(frozen=True, slots=True)
class DocumentPart:
    """One speech request read as an ordered part of a provider document."""

    request_id: str
    text: str


@dataclass(frozen=True, slots=True)
class DocumentSynthesisRequest:
    """Validated document passed to the engine; *tags* sends square brackets to the server as audio tags."""

    request_id: str
    parts: tuple[DocumentPart, ...]
    voice_id: str
    recording: Path
    deadline_s: float
    progress: Callable[[int, int], Awaitable[None]] | None = field(default=None, compare=False)
    tags: bool = False

    def __post_init__(self) -> None:
        """Reject a document without parts."""
        if not self.parts:
            message: str = "Document synthesis request needs at least one part"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class PartTiming:
    """Server-time span of one document part on the recording timeline; an empty span marks an unspoken part."""

    request_id: str
    start_ms: float
    end_ms: float

    def __post_init__(self) -> None:
        """Reject a reversed span."""
        if self.end_ms < self.start_ms:
            message: str = "Document part timing must not end before it starts"
            raise ValueError(message)

    @property
    def spoken(self) -> bool:
        """Tell whether the server read the part aloud."""
        return self.end_ms > self.start_ms


@dataclass(frozen=True, slots=True)
class ElevenReaderVoice:
    """One selectable ElevenReader voice."""

    alias: str
    label: str
    voice_id: str


class LibraryState(StrEnum):
    """What the library page showed."""

    READY = "ready"
    SIGNED_OUT = "signed_out"
    UNAVAILABLE = "unavailable"


class SignInOutcome(StrEnum):
    """Result of the visible sign-in action."""

    SIGNED_IN = "signed_in"
    SIGNED_OUT = "signed_out"
    BUSY = "busy"
    NO_CHROME = "no_chrome"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AccountSettings:
    """Default voice and playback speed of the account; None marks a field the account did not report."""

    voice_id: str | None
    speed: float | None


@dataclass(frozen=True, slots=True)
class DocumentTrace:
    """One uploaded document until it is deleted: its read id once known, else its upload window and title digests."""

    pressed_at: float
    listed_by: float
    titles: frozenset[str]
    read_id: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """Last observed sign-in state and the account cleanup still owed, without any secret or plain document text."""

    signed_in: bool
    checked_at: datetime
    restore: AccountSettings | None = None
    documents: tuple[DocumentTrace, ...] = ()

    @property
    def delete_document(self) -> bool:
        """Whether an uploaded document may still be in the library."""
        return bool(self.documents)

    @property
    def cleanup_pending(self) -> bool:
        """Whether the account may still hold an uploaded document or changed settings."""
        return self.restore is not None or self.delete_document


@dataclass(slots=True)
class AccountCleanup:
    """Account changes to undo: settings and every uploaded document not yet deleted."""

    restore: AccountSettings | None = None
    documents: list[DocumentTrace] = field(default_factory=list)

    @property
    def pending(self) -> tuple[str, ...]:
        """Return the kinds of steps still to run, in execution order."""
        kinds: list[str] = []
        if self.restore is not None:
            kinds.append("restore_settings")
        if any(document.read_id is not None for document in self.documents):
            kinds.append("delete_read")
        if any(document.read_id is None for document in self.documents):
            kinds.append("delete_orphan")
        return tuple(kinds)

    def swap(self, old: DocumentTrace, new: DocumentTrace) -> None:
        """Put *new* in place of *old*."""
        self.documents[self.documents.index(old)] = new


@dataclass(frozen=True, slots=True)
class UploadedRead:
    """Library entry created by one upload; id and token stay in memory only."""

    read_id: str = field(repr=False)
    char_count: int
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PlayerState:
    """Player position and document length, both in characters."""

    value: float
    length: float


@dataclass(frozen=True, slots=True)
class AlignmentChunk:
    """Characters of one audio chunk with times relative to the chunk start; *silent* marks text sent without speech."""

    offset_ms: float
    chars: tuple[str, ...]
    starts_ms: tuple[float, ...]
    durations_ms: tuple[float, ...]
    silent: bool = False


@dataclass(frozen=True, slots=True)
class DocumentResult:
    """Recording, part timings and stream chunks produced by one document attempt."""

    request_id: str
    recording: Path
    voice_id: str
    request_time_ms: float
    parts: tuple[PartTiming, ...]
    chunks: tuple[AlignmentChunk, ...]
