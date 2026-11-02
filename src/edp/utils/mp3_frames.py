"""Parse MPEG audio Layer III frames: headers, durations, cuts and broken-frame splices."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

__all__ = [
    "HEADER_BYTES",
    "ID3_HEADER_BYTES",
    "FrameHeader",
    "audio_offset",
    "cut_before_ms",
    "frames_duration_ms",
    "iter_frames",
    "parse_frame_header",
    "splice_times",
    "to_decoded",
]

# ── Constants ────────────────────────────────────────────────────────────────

HEADER_BYTES: Final[int] = 4
"""Number of bytes in one MPEG audio frame header."""

ID3_HEADER_BYTES: Final[int] = 10
"""Number of bytes in an ID3v2 header or footer."""

_CUT_TOLERANCE_MS: Final[float] = 0.5
"""Slack absorbing float drift when summed frame durations land just short of a cut."""

_MPEG_LAYER_III: Final[int] = 1
"""Bit-field value identifying MPEG Layer III."""

_MPEG_SYNC_WORD: Final[int] = 0x7FF
"""Eleven-bit synchronization word starting every MPEG audio frame."""

_MPEG1_VERSION: Final[int] = 3
"""Bit-field value identifying MPEG-1."""

_RESERVED_VERSION: Final[int] = 1
"""Reserved version bit-field value rejected by the MPEG audio specification."""

_RESERVED_SAMPLE_RATE: Final[int] = 3
"""Reserved sample-rate index rejected by the MPEG audio specification."""

_INVALID_BITRATES: Final[frozenset[int]] = frozenset({0, 0b1111})
"""Free-format and reserved bitrate indexes, both rejected."""

_SINGLE_CHANNEL_MODE: Final[int] = 3
"""Channel-mode value identifying a single-channel stream."""

_MPEG1_SAMPLES: Final[int] = 1152
"""Samples in one MPEG-1 Layer III frame."""

_MPEG2_SAMPLES: Final[int] = 576
"""Samples in one MPEG-2 or MPEG-2.5 Layer III frame."""

_MPEG1_BITRATES_KBPS: Final[tuple[int, ...]] = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
"""Layer III bitrates indexed by an MPEG-1 frame header."""

_MPEG2_BITRATES_KBPS: Final[tuple[int, ...]] = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
"""Layer III bitrates indexed by an MPEG-2 or MPEG-2.5 frame header."""

_SAMPLE_RATES: Final[dict[int, tuple[int, int, int]]] = {
    0: (11_025, 12_000, 8_000),
    2: (22_050, 24_000, 16_000),
    3: (44_100, 48_000, 32_000),
}
"""Sample rates indexed first by MPEG version bits, then frequency bits."""


@dataclass(frozen=True, slots=True)
class FrameHeader:
    """One Layer III frame located in a byte buffer."""

    offset: int
    size: int
    sample_rate: int
    channels: int
    samples: int
    version: int

    @property
    def duration_ms(self) -> float:
        """Return the playing time of this frame."""
        return self.samples * 1000 / self.sample_rate


def parse_frame_header(data: bytes, offset: int) -> FrameHeader | None:
    """Return the Layer III frame header at ``offset``, or None when the bytes are not one."""
    if offset < 0 or offset + HEADER_BYTES > len(data):
        return None
    header: int = int.from_bytes(data[offset : offset + HEADER_BYTES])
    if header >> 21 != _MPEG_SYNC_WORD:
        return None
    version: int = (header >> 19) & 0b11
    layer: int = (header >> 17) & 0b11
    bitrate_index: int = (header >> 12) & 0b1111
    sample_rate_index: int = (header >> 10) & 0b11
    if (
        version == _RESERVED_VERSION
        or layer != _MPEG_LAYER_III
        or bitrate_index in _INVALID_BITRATES
        or sample_rate_index == _RESERVED_SAMPLE_RATE
    ):
        return None
    mpeg1: bool = version == _MPEG1_VERSION
    bitrate: int = (_MPEG1_BITRATES_KBPS if mpeg1 else _MPEG2_BITRATES_KBPS)[bitrate_index] * 1000
    sample_rate: int = _SAMPLE_RATES[version][sample_rate_index]
    padding: int = (header >> 9) & 1
    channel_mode: int = (header >> 6) & 0b11
    return FrameHeader(
        offset=offset,
        size=(144 if mpeg1 else 72) * bitrate // sample_rate + padding,
        sample_rate=sample_rate,
        channels=1 if channel_mode == _SINGLE_CHANNEL_MODE else 2,
        samples=_MPEG1_SAMPLES if mpeg1 else _MPEG2_SAMPLES,
        version=version,
    )


def audio_offset(data: bytes) -> int:
    """Return the offset after a leading ID3v2 tag; raise ValueError for a truncated or invalid tag."""
    if not data.startswith(b"ID3"):
        return 0
    if len(data) < ID3_HEADER_BYTES:
        message: str = "truncated ID3v2 header"
        raise ValueError(message)
    size_bytes: bytes = data[6:10]
    if any(byte & 0x80 for byte in size_bytes):
        message = "invalid ID3v2 size"
        raise ValueError(message)
    tag_size: int = 0
    for byte in size_bytes:
        tag_size = (tag_size << 7) | byte
    footer_size: int = ID3_HEADER_BYTES if data[5] & 0x10 else 0
    return ID3_HEADER_BYTES + tag_size + footer_size


def iter_frames(data: bytes) -> Iterator[FrameHeader]:
    """Yield valid frames after any ID3v2 tag; a frame is valid when the next header is valid or data ends."""
    offset: int = audio_offset(data)
    while offset + HEADER_BYTES <= len(data):
        frame: FrameHeader | None = _valid_frame(data, offset)
        if frame is None:
            offset += 1
            continue
        yield frame
        offset += frame.size


def frames_duration_ms(data: bytes) -> float:
    """Return the server playing time: every decoded frame plus one frame per dropped run starting with a header."""
    return sum(duration_ms for _, duration_ms, _ in _server_frames(data))


def cut_before_ms(data: bytes, cut_ms: float) -> tuple[bytes, float]:
    """Drop the frames that start before server time ``cut_ms``; return the remaining data and the time dropped."""
    dropped: float = 0.0
    for offset, duration_ms, _ in _server_frames(data):
        if dropped >= cut_ms - _CUT_TOLERANCE_MS:
            return data[offset:], dropped
        dropped += duration_ms
    return b"", dropped


def splice_times(data: bytes) -> tuple[float, ...]:
    """Return decoded-timeline times of byte runs starting with a header, each one frame the decoder drops."""
    decoded_ms: float = 0.0
    splices: list[float] = []
    for _, duration_ms, dropped in _server_frames(data):
        if dropped:
            splices.append(decoded_ms)
            continue
        decoded_ms += duration_ms
    return tuple(splices)


def to_decoded(server_ms: float, splices: Sequence[float], frame_ms: float) -> float:
    """Map a server-timeline time onto the decoded timeline that lost ``frame_ms`` at every splice."""
    lost: int = 0
    for splice in splices:
        if splice + lost * frame_ms >= server_ms:
            break
        lost += 1
    return server_ms - lost * frame_ms


def _valid_frame(data: bytes, offset: int) -> FrameHeader | None:
    frame: FrameHeader | None = parse_frame_header(data, offset)
    if frame is None:
        return None
    following: int = offset + frame.size
    if following + HEADER_BYTES > len(data) or parse_frame_header(data, following) is not None:
        return frame
    return None


def _server_frames(data: bytes) -> Iterator[tuple[int, float, bool]]:
    expected: int = audio_offset(data)
    for frame in iter_frames(data):
        dropped: FrameHeader | None = parse_frame_header(data, expected)
        if frame.offset != expected and dropped is not None:
            yield expected, dropped.duration_ms, True
        yield frame.offset, frame.duration_ms, False
        expected = frame.offset + frame.size
    trailing: FrameHeader | None = parse_frame_header(data, expected)
    if trailing is not None:
        yield expected, trailing.duration_ms, False
