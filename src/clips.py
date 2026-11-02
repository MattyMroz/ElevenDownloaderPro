"""Cut one ElevenReader recording into a voice-over clip (.mp3) and its text (.txt) per subtitle line.

Workflow:
    uv run src/clips.py prepare film.srt
        writes workspace/input/film.txt with every subtitle line as its own paragraph
    uv run src/auto.py
        records it to workspace/output/film.mp3 and film.align.jsonl
    uv run src/clips.py cut workspace/output/film.align.jsonl film.srt
        writes workspace/output/film_clips/NNN.mp3, NNN.txt and manifest.json
    uv run src/clips.py verify workspace/output/film_clips
        reports clips that start or end at speech level (a cut word); exits with 1 when any do

The character timings run a few hundred milliseconds ahead of the audio, so cut decodes the recording and moves
every line boundary into the silence nearest to it; --no-snap cuts at the character timings alone.
"""

import argparse
import bisect
import itertools
import json
import math
import re
from array import array
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import miniaudio  # type: ignore[import-untyped]  # ships without type hints

from timestamps import BITRATES_KBPS, BREAK_TAG, SAMPLES_PER_FRAME, load_timeline, mp3_frames, srt_time

# ── Constants ────────────────────────────────────────────────────────────────

ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
"""Project root that anchors the default paths."""

INPUT_DIR: Final[Path] = ROOT_DIR / "workspace" / "input"
"""Directory that auto.py uploads documents from."""

SRT_TIME: Final[re.Pattern[str]] = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")
"""Subtitle timestamp such as 00:01:02,345."""

MARKUP: Final[re.Pattern[str]] = re.compile(r"<[^>]*>|\{[^}]*\}")
"""HTML tags like <i> and ASS overrides like {\\an8} inside subtitle text."""

DEFAULT_PAD_BEFORE_MS: Final[float] = 100.0
"""Audio kept before the first letter of a line, limited to half the gap to the previous line."""

DEFAULT_PAD_AFTER_MS: Final[float] = 150.0
"""Audio kept after the last letter of a line, limited to half the gap to the next line."""

MAX_SKIP_CHARS: Final[int] = 300
"""Most letters and digits the recording may hold between two lines before the later one counts as not found."""

ANCHOR_CHARS: Final[int] = 12
"""Letters and digits at each end of a line that locate it when its middle differs from the recording."""

FRAME_HEADER_SIZE: Final[int] = 4
"""Bytes in an MPEG audio frame header."""

RESERVOIR_FRAMES: Final[int] = 2
"""Frames kept before a clip because its first frames borrow bits from them; decoders drop or silence these."""

EDGE_MS: Final[float] = 40.0
"""Length of the clip start and end that verify measures."""

SPEECH_DROP_DB: Final[float] = 12.0
"""An edge less than this many dB below the clip's middle is at speech level, so a word is probably cut."""

SILENCE_DBFS: Final[float] = -50.0
"""Edges above this level but below speech level hold a breath or a fading word rather than silence."""

MIN_DBFS: Final[float] = -120.0
"""Level reported for digital silence."""

FULL_SCALE: Final[float] = 32768.0
"""Peak value of a signed 16-bit sample."""

SAMPLE_RATE: Final[int] = 44100
"""Sample rate that verify decodes clips at."""

ENVELOPE_RATE: Final[int] = 16000
"""Sample rate that cut decodes the recording at to find speech; enough for loudness and four times less work."""

WINDOW_MS: Final[int] = 10
"""Length of one loudness window in the speech envelope."""

LOUD_FLOOR_DBFS: Final[float] = -60.0
"""Windows above this level count towards the typical speech level."""

SILENCE_BELOW_SPEECH_DB: Final[float] = 15.0
"""Windows this many dB below the typical speech level are silence."""

MIN_GAP_MS: Final[float] = 120.0
"""Shortest silence that can separate two lines."""

DELAY_SEARCH_MS: Final[tuple[float, float, float]] = (-500.0, 1000.0, 10.0)
"""Lowest, highest and step of the audio delay behind the character timings tried when snapping."""

SNAP_TOLERANCE_MS: Final[float] = 400.0
"""Farthest a silence may lie from a delayed line boundary and still be taken as that boundary."""

DIP_MS: Final[int] = 50
"""Length of the quietest stretch taken as the boundary where the reader runs two lines together."""

DIP_SEARCH_MS: Final[float] = 200.0
"""Farthest from its place in the speech run that the boundary of two lines read without a pause is looked for."""


@dataclass(frozen=True)
class Cue:
    number: int
    start_ms: float
    end_ms: float
    text: str


@dataclass(frozen=True)
class Span:
    start_ms: float
    end_ms: float


@dataclass(frozen=True)
class Frame:
    start: int
    end: int
    start_ms: float
    end_ms: float


@dataclass(frozen=True)
class Boundary:
    """Audio between two lines: a silence, the quietest dip where none was found, or the bare delayed timing."""

    span: Span
    kind: str


@dataclass(frozen=True)
class Placement:
    """Where a line is cut, where its speech lies and what kind of boundary each side was snapped to."""

    clip: Span
    speech: Span
    start_kind: str
    end_kind: str

    @property
    def snapped(self) -> bool:
        return self.start_kind != "timing" and self.end_kind != "timing"


# ── Subtitles ────────────────────────────────────────────────────────────────


def parse_srt_time(match: re.Match[str]) -> float:
    hours: str
    minutes: str
    seconds: str
    millis: str
    hours, minutes, seconds, millis = match.groups()
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis.ljust(3, "0"))


def clean_text(lines: Sequence[str]) -> str:
    """Join the lines of one subtitle into a single line without markup."""
    return " ".join(MARKUP.sub("", " ".join(lines)).split())


def is_timing(line: str) -> bool:
    return "-->" in line and len(SRT_TIME.findall(line)) >= 2


def parse_cue(lines: list[str], fallback_number: int) -> Cue | None:
    """Parse the number, timing and text lines of one subtitle; return None when it has no text."""
    timing: int = next(k for k, line in enumerate(lines) if is_timing(line))
    start: re.Match[str]
    end: re.Match[str]
    start, end = list(SRT_TIME.finditer(lines[timing]))[:2]
    text: str = clean_text(lines[timing + 1 :])
    if not text:
        return None
    number: int = int(lines[timing - 1]) if timing > 0 and lines[timing - 1].isdigit() else fallback_number
    return Cue(number, parse_srt_time(start), parse_srt_time(end), text)


def parse_srt(path: Path) -> list[Cue]:
    """Return the non-empty subtitles of an .srt file in order, splitting at timing lines, not blank lines."""
    lines: list[str] = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    starts: list[int] = [
        k - 1 if k > 0 and lines[k - 1].isdigit() else k for k, line in enumerate(lines) if is_timing(line)
    ]
    cues: list[Cue] = []
    for n, (first, last) in enumerate(zip(starts, [*starts[1:], len(lines)], strict=True), start=1):
        cue: Cue | None = parse_cue(lines[first:last], n)
        if cue is not None:
            cues.append(cue)
    return cues


def prepare(srt_path: Path, out_path: Path) -> int:
    """Write every subtitle line as its own paragraph and return the number of lines."""
    cues: list[Cue] = parse_srt(srt_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n\n".join(cue.text for cue in cues) + "\n", encoding="utf-8")
    return len(cues)


# ── Matching ─────────────────────────────────────────────────────────────────


def normalize(text: str) -> str:
    return "".join(ch.casefold() for ch in text if ch.isalnum())


def normalize_timeline(text: str) -> tuple[str, list[int]]:
    """Keep the letters and digits outside break tags, casefolded, with each one's index in the original text."""
    in_break: list[bool] = [False] * len(text)
    for match in BREAK_TAG.finditer(text):
        in_break[match.start() : match.end()] = [True] * (match.end() - match.start())
    letters: list[str] = []
    positions: list[int] = []
    for k, ch in enumerate(text):
        if in_break[k] or not ch.isalnum():
            continue
        folded: str = ch.casefold()
        letters.append(folded)
        positions.extend([k] * len(folded))
    return "".join(letters), positions


def find_anchored(key: str, haystack: str, cursor: int) -> tuple[int, int] | None:
    """Locate a line by its first and last letters when its middle differs from the recording."""
    if len(key) <= 2 * ANCHOR_CHARS:
        return None
    head: str
    tail: str
    head, tail = key[:ANCHOR_CHARS], key[-ANCHOR_CHARS:]
    start: int = haystack.find(head, cursor, cursor + MAX_SKIP_CHARS + len(head))
    if start < 0:
        return None
    tail_at: int = haystack.find(tail, start + len(head), start + 2 * len(key))
    if tail_at < 0 or tail_at + len(tail) - start < len(key) // 2:
        return None
    return start, tail_at + len(tail)


def find_line(key: str, haystack: str, cursor: int) -> tuple[int, int] | None:
    """Return the normalized span of a line found at or shortly after cursor."""
    if not key:
        return None
    start: int = haystack.find(key, cursor, cursor + MAX_SKIP_CHARS + len(key))
    if start >= 0:
        return start, start + len(key)
    return find_anchored(key, haystack, cursor)


def locate_lines(cues: list[Cue], align_path: Path) -> list[Span | None]:
    """Time every subtitle line from its first to its last letter, in order; None marks a line that was not found."""
    text: str
    starts: list[float]
    ends: list[float]
    text, starts, ends = load_timeline(align_path)
    haystack: str
    positions: list[int]
    haystack, positions = normalize_timeline(text)
    spans: list[Span | None] = []
    cursor: int = 0
    for cue in cues:
        found: tuple[int, int] | None = find_line(normalize(cue.text), haystack, cursor)
        if found is None:
            spans.append(None)
            continue
        spans.append(Span(starts[positions[found[0]]], ends[positions[found[1] - 1]]))
        cursor = found[1]
    return spans


def pad_spans(spans: list[Span | None], before_ms: float, after_ms: float, total_ms: float) -> list[Span | None]:
    """Widen each span by the padding, but never past the middle of the gap to a neighbouring line."""
    found: list[Span] = [s for s in spans if s is not None]
    padded: list[Span | None] = []
    k: int = 0
    for span in spans:
        if span is None:
            padded.append(None)
            continue
        lower: float = (found[k - 1].end_ms + span.start_ms) / 2 if k > 0 else 0.0
        upper: float = (span.end_ms + found[k + 1].start_ms) / 2 if k + 1 < len(found) else total_ms
        start: float = min(span.start_ms, max(span.start_ms - before_ms, lower))
        end: float = max(span.end_ms, min(span.end_ms + after_ms, upper))
        padded.append(Span(start, end))
        k += 1
    return padded


# ── MP3 ──────────────────────────────────────────────────────────────────────


def frame_table(data: bytes) -> list[Frame]:
    """Return every MPEG-1 Layer III frame with its byte range and its time in the recording."""
    frames: list[Frame] = []
    clock: float = 0.0
    for offset, rate in mp3_frames(data):
        header: bytes = data[offset : offset + FRAME_HEADER_SIZE]
        size: int = 144_000 * BITRATES_KBPS[header[2] >> 4] // rate + ((header[2] >> 1) & 1)
        duration: float = SAMPLES_PER_FRAME * 1000 / rate
        frames.append(Frame(offset, offset + size, clock, clock + duration))
        clock += duration
    return frames


def cut_frames(data: bytes, frames: list[Frame], span: Span) -> tuple[bytes, Span]:
    """Return the frames that cover the span after RESERVOIR_FRAMES lead-in frames, and the time they play."""
    boundaries: list[float] = [f.start_ms for f in frames] + [frames[-1].end_ms]
    first: int = min(max(0, bisect.bisect_right(boundaries, span.start_ms) - 1), len(frames) - 1)
    last: int = max(min(bisect.bisect_left(boundaries, span.end_ms), len(frames)), first + 1)
    clip: bytes = b"".join(data[f.start : f.end] for f in frames[max(0, first - RESERVOIR_FRAMES) : last])
    return clip, Span(frames[first].start_ms, frames[last - 1].end_ms)


# ── Speech envelope ──────────────────────────────────────────────────────────


def decode_mono(data: bytes, sample_rate: int) -> array[int]:
    samples: array[int] = miniaudio.decode(data, nchannels=1, sample_rate=sample_rate).samples
    return samples


def stream_ranges(frames: list[Frame]) -> list[tuple[int, int]]:
    """Return the frame ranges of the separately encoded streams, which ID3 tags or stray bytes separate."""
    starts: list[int] = [0] + [k for k in range(1, len(frames)) if frames[k].start != frames[k - 1].end]
    return list(zip(starts, [*starts[1:], len(frames)], strict=True))


def decode_recording(data: bytes, frames: list[Frame]) -> array[int]:
    """Decode stream by stream, each fitted to its frames' playing time, so samples stay on the frame clock."""
    pcm: array[int] = array("h")
    for first, last in stream_ranges(frames):
        samples: array[int] = decode_mono(data[frames[first].start : frames[last - 1].end], ENVELOPE_RATE)
        expected: int = round((frames[last - 1].end_ms - frames[first].start_ms) * ENVELOPE_RATE / 1000)
        pcm.extend(samples[:expected])
        pcm.extend(array("h", bytes(2 * max(0, expected - len(samples)))))
    return pcm


def envelope(pcm: array[int]) -> list[float]:
    """Return the level of every WINDOW_MS window."""
    size: int = ENVELOPE_RATE * WINDOW_MS // 1000
    return [rms_dbfs(pcm[k : k + size]) for k in range(0, len(pcm) - size + 1, size)]


def silence_threshold(levels: list[float]) -> float:
    """Return the level below which a window is silence, relative to the median level of the louder windows."""
    loud: list[float] = sorted(level for level in levels if level > LOUD_FLOOR_DBFS)
    speech: float = loud[len(loud) // 2] if loud else LOUD_FLOOR_DBFS
    return speech - SILENCE_BELOW_SPEECH_DB


def silences(levels: list[float]) -> list[Span]:
    """Return the silences of at least MIN_GAP_MS plus the ones that open and close the recording."""
    threshold: float = silence_threshold(levels)
    gaps: list[Span] = []
    quiet_from: int | None = 0
    for k, level in enumerate(levels):
        if level <= threshold:
            quiet_from = k if quiet_from is None else quiet_from
            continue
        if quiet_from is not None and (quiet_from == 0 or (k - quiet_from) * WINDOW_MS >= MIN_GAP_MS):
            gaps.append(Span(quiet_from * WINDOW_MS, k * WINDOW_MS))
        quiet_from = None
    end: int = len(levels) * WINDOW_MS
    gaps.append(Span(end if quiet_from is None else quiet_from * WINDOW_MS, end))
    return gaps


# ── Snapping ─────────────────────────────────────────────────────────────────


def boundary_points(spans: list[Span]) -> list[float]:
    """Return the timed start of the first line, the middle of every pause between lines and the end of the last."""
    middles: list[float] = [(a.end_ms + b.start_ms) / 2 for a, b in itertools.pairwise(spans)]
    return [spans[0].start_ms, *middles, spans[-1].end_ms]


def gap_distance(gap: Span, ms: float) -> float:
    return max(gap.start_ms - ms, ms - gap.end_ms, 0.0)


def closest_distance(gaps: list[Span], starts: list[float], ms: float) -> float:
    k: int = bisect.bisect_right(starts, ms)
    return min(gap_distance(gaps[j], ms) for j in (k - 1, k) if 0 <= j < len(gaps))


def estimate_delay(points: list[float], gaps: list[Span]) -> float:
    """Find how far the audio lags the character timings by putting the most line boundaries into silences."""
    starts: list[float] = [g.start_ms for g in gaps]
    low: float
    high: float
    step: float
    low, high, step = DELAY_SEARCH_MS
    delays: list[float] = [low + step * k for k in range(round((high - low) / step) + 1)]
    return min(
        delays,
        key=lambda d: (sum(min(closest_distance(gaps, starts, p + d), SNAP_TOLERANCE_MS) for p in points), abs(d)),
    )


def pick_silence(gaps: list[Span], starts: list[float], ms: float, after_ms: float) -> Span | None:
    """Return the silence nearest to ms within SNAP_TOLERANCE_MS that starts after after_ms."""
    best: Span | None = None
    for gap in gaps[max(0, bisect.bisect_left(starts, ms - SNAP_TOLERANCE_MS) - 1) :]:
        if gap.start_ms > ms + SNAP_TOLERANCE_MS:
            break
        distance: float = gap_distance(gap, ms)
        if gap.start_ms > after_ms and distance <= SNAP_TOLERANCE_MS:
            best = gap if best is None or distance < gap_distance(best, ms) else best
    return best


def quietest_dip(levels: list[float], ms: float, after_ms: float) -> Span | None:
    """Return the quietest DIP_MS stretch within DIP_SEARCH_MS of ms that starts after after_ms."""
    size: int = DIP_MS // WINDOW_MS
    first: int = max(0, math.floor(max(ms - DIP_SEARCH_MS, after_ms) / WINDOW_MS) + 1)
    last: int = min(len(levels) - size, math.floor((ms + DIP_SEARCH_MS) / WINDOW_MS))
    if first > last:
        return None
    k: int = min(range(first, last + 1), key=lambda j: (sum(levels[j : j + size]), abs(j * WINDOW_MS - ms)))
    return Span(k * WINDOW_MS, (k + size) * WINDOW_MS)


def find_silences(points: list[float], gaps: list[Span], delay: float) -> list[Span | None]:
    """Find the silence at each delayed line boundary, in order, or None where the reader did not pause."""
    starts: list[float] = [g.start_ms for g in gaps]
    found: list[Span | None] = []
    after: float = -math.inf
    for point in points:
        silence: Span | None = pick_silence(gaps, starts, point + delay, after)
        found.append(silence)
        after = silence.end_ms if silence else after
    return found


def place_in_run(point: float, lines: list[Span], silences_at: list[Span | None], k: int, delay: float) -> float:
    """Estimate where boundary k of two lines read without a pause lies in the audio.

    Character timings drift by a few hundred milliseconds around pauses, more than the length of a short word, so the
    boundary keeps its relative place between the silences that open and close its run of continuous speech.
    """
    opening: int | None = next((j for j in range(k - 1, -1, -1) if silences_at[j]), None)
    closing: int | None = next((j for j in range(k + 1, len(silences_at)) if silences_at[j]), None)
    if opening is None or closing is None:
        return point + delay
    opened: Span | None = silences_at[opening]
    closed: Span | None = silences_at[closing]
    timed_from: float = lines[opening].start_ms
    timed_to: float = lines[closing - 1].end_ms
    if opened is None or closed is None or timed_to <= timed_from:
        return point + delay
    return opened.end_ms + (point - timed_from) * (closed.start_ms - opened.end_ms) / (timed_to - timed_from)


def find_boundaries(
    points: list[float], lines: list[Span], levels: list[float], gaps: list[Span], delay: float
) -> list[Boundary]:
    """Find each line boundary in the audio, in order: a silence, else the quietest dip, else the timing."""
    silences_at: list[Span | None] = find_silences(points, gaps, delay)
    boundaries: list[Boundary] = []
    after: float = -math.inf
    for k, (point, silence) in enumerate(zip(points, silences_at, strict=True)):
        boundary: Boundary
        if silence:
            boundary = Boundary(silence, "silence")
        else:
            ms: float = place_in_run(point, lines, silences_at, k, delay)
            dip: Span | None = quietest_dip(levels, ms, after)
            boundary = Boundary(dip, "dip") if dip else Boundary(Span(max(ms, after), max(ms, after)), "timing")
        boundaries.append(boundary)
        after = boundary.span.end_ms
    return boundaries


def pad_in_gaps(speech: Span, before: Span, after: Span, before_ms: float, after_ms: float) -> Span:
    """Widen the speech by the padding, but never past the middle of the boundaries around it."""
    start: float = max(speech.start_ms - before_ms, (before.start_ms + before.end_ms) / 2)
    end: float = min(speech.end_ms + after_ms, (after.start_ms + after.end_ms) / 2)
    return Span(min(start, speech.start_ms), max(end, speech.end_ms))


def snap_lines(
    spans: list[Span | None], levels: list[float], before_ms: float, after_ms: float
) -> list[Placement | None]:
    """Place every found line between the boundaries around its speech; without any speech, at its timings."""
    found: list[Span] = [s for s in spans if s is not None]
    gaps: list[Span] = silences(levels)
    if not found or gaps[0].end_ms >= len(levels) * WINDOW_MS:
        return place_lines(spans, before_ms, after_ms, len(levels) * WINDOW_MS)
    points: list[float] = boundary_points(found)
    boundaries: list[Boundary] = find_boundaries(points, found, levels, gaps, estimate_delay(points, gaps))
    pairs: Iterator[tuple[Boundary, Boundary]] = itertools.pairwise(boundaries)
    placements: list[Placement | None] = []
    for span in spans:
        if span is None:
            placements.append(None)
            continue
        before: Boundary
        after: Boundary
        before, after = next(pairs)
        speech: Span = Span(before.span.end_ms, after.span.start_ms)
        clip: Span = pad_in_gaps(speech, before.span, after.span, before_ms, after_ms)
        placements.append(Placement(clip, speech, before.kind, after.kind))
    return placements


def place_lines(spans: list[Span | None], before_ms: float, after_ms: float, total_ms: float) -> list[Placement | None]:
    """Place every found line at its padded character timings."""
    padded: list[Span | None] = pad_spans(spans, before_ms, after_ms, total_ms)
    return [Placement(p, s, "timing", "timing") if s and p else None for s, p in zip(spans, padded, strict=True)]


# ── Cutting ──────────────────────────────────────────────────────────────────


def seconds(ms: float) -> float:
    return round(ms / 1000, 3)


def snap_shift(kind: str, ms: float) -> float | None:
    return seconds(ms) if kind != "timing" else None


def clip_entry(
    cue: Cue, name: str, timed: Span | None, placed: Placement | None, audio: Span | None
) -> dict[str, object]:
    return {
        "index": cue.number,
        "srt_start": srt_time(cue.start_ms),
        "srt_end": srt_time(cue.end_ms),
        "text": cue.text,
        "file": f"{name}.mp3" if audio else None,
        "audio_start_s": seconds(audio.start_ms) if audio else None,
        "audio_end_s": seconds(audio.end_ms) if audio else None,
        "duration_s": seconds(audio.end_ms - audio.start_ms) if audio else None,
        "matched": audio is not None,
        "snapped": placed is not None and placed.snapped,
        "start_snap": placed.start_kind if placed else None,
        "end_snap": placed.end_kind if placed else None,
        "speech_start_s": seconds(placed.speech.start_ms) if placed else None,
        "speech_end_s": seconds(placed.speech.end_ms) if placed else None,
        "shift_start_s": snap_shift(placed.start_kind, placed.speech.start_ms - timed.start_ms)
        if placed and timed
        else None,
        "shift_end_s": snap_shift(placed.end_kind, placed.speech.end_ms - timed.end_ms) if placed and timed else None,
    }


def report_snap(cue: Cue, placed: Placement) -> None:
    """Tell where a line boundary had no silence to snap to."""
    weak: list[str] = [
        f"{edge} {kind}" for edge, kind in (("start", placed.start_kind), ("end", placed.end_kind)) if kind != "silence"
    ]
    if weak:
        print(f"Line {cue.number} cut without silence ({', '.join(weak)}): {cue.text}")


def cut(
    align_path: Path,
    srt_path: Path,
    out_dir: Path,
    before_ms: float,
    after_ms: float,
    *,
    snap: bool,
) -> list[Placement | None]:
    """Write one clip and text file per subtitle line plus manifest.json; return where every line was placed."""
    stem: str = align_path.name.removesuffix(".align.jsonl")
    data: bytes = align_path.with_name(f"{stem}.mp3").read_bytes()
    frames: list[Frame] = frame_table(data)
    if not frames:
        raise SystemExit(f"No MP3 audio in {stem}.mp3")
    cues: list[Cue] = parse_srt(srt_path)
    spans: list[Span | None] = locate_lines(cues, align_path)
    if snap:
        placements: list[Placement | None] = snap_lines(
            spans, envelope(decode_recording(data, frames)), before_ms, after_ms
        )
    else:
        placements = place_lines(spans, before_ms, after_ms, frames[-1].end_ms)
    width: int = max(3, len(str(max((c.number for c in cues), default=0))))

    out_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    for cue, timed, placed in zip(cues, spans, placements, strict=True):
        name: str = f"{cue.number:0{width}d}"
        (out_dir / f"{name}.txt").write_text(cue.text + "\n", encoding="utf-8")
        audio: Span | None = None
        if placed is None:
            print(f"Line {cue.number} not found in the recording: {cue.text}")
        else:
            clip: bytes
            clip, audio = cut_frames(data, frames, placed.clip)
            (out_dir / f"{name}.mp3").write_bytes(clip)
            if snap:
                report_snap(cue, placed)
        entries.append(clip_entry(cue, name, timed, placed, audio))

    manifest: dict[str, object] = {"recording": f"{stem}.mp3", "subtitles": srt_path.name, "clips": entries}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return placements


# ── Verification ─────────────────────────────────────────────────────────────


def rms_dbfs(samples: Sequence[int]) -> float:
    if not samples:
        return MIN_DBFS
    rms: float = math.sqrt(math.sumprod(samples, samples) / len(samples))
    return max(MIN_DBFS, 20 * math.log10(rms / FULL_SCALE)) if rms else MIN_DBFS


def edge_levels(samples: Sequence[int]) -> tuple[float, float, float]:
    """Return the level of the first EDGE_MS, the middle half and the last EDGE_MS of a clip."""
    edge: int = int(SAMPLE_RATE * EDGE_MS / 1000)
    quarter: int = len(samples) // 4
    return rms_dbfs(samples[:edge]), rms_dbfs(samples[quarter : len(samples) - quarter]), rms_dbfs(samples[-edge:])


def edge_state(edge_db: float, middle_db: float) -> str:
    """Classify a clip edge as cut speech, noise such as a breath or a fading word, or silence."""
    if edge_db > middle_db - SPEECH_DROP_DB:
        return "cut"
    return "noisy" if edge_db > SILENCE_DBFS else ""


def verify(clips_dir: Path) -> int:
    """Print the edge and middle levels of every clip and return how many start or end at speech level."""
    manifest: Any = json.loads((clips_dir / "manifest.json").read_text(encoding="utf-8"))
    cut_count: int = 0
    noisy_count: int = 0
    print(f"{'clip':>8} {'sec':>6} {'head dB':>8} {'mid dB':>8} {'tail dB':>8}  verdict")
    for entry in manifest["clips"]:
        if not entry["matched"]:
            print(f"{entry['index']:>8} {'-':>6} {'-':>8} {'-':>8} {'-':>8}  not found")
            continue
        head: float
        middle: float
        tail: float
        head, middle, tail = edge_levels(decode_mono((clips_dir / entry["file"]).read_bytes(), SAMPLE_RATE))
        states: dict[str, str] = {"start": edge_state(head, middle), "end": edge_state(tail, middle)}
        cut_count += "cut" in states.values()
        noisy_count += "cut" not in states.values() and "noisy" in states.values()
        verdict: str = ", ".join(f"{state} {edge}" for edge, state in states.items() if state) or "ok"
        print(f"{entry['index']:>8} {entry['duration_s']:>6.2f} {head:>8.1f} {middle:>8.1f} {tail:>8.1f}  {verdict}")
    print(f"{len(manifest['clips'])} clips: {cut_count} probably cut a word, {noisy_count} only start or end noisy")
    return cut_count


# ── CLI ──────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Cut an ElevenReader recording into one clip per subtitle line."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prep: argparse.ArgumentParser = commands.add_parser(
        "prepare", help="turn an .srt file into a document with one paragraph per line"
    )
    prep.add_argument("srt", type=Path)
    prep.add_argument("--out", type=Path, help="output .txt (default: workspace/input/<stem>.txt)")

    cutting: argparse.ArgumentParser = commands.add_parser(
        "cut", help="cut the recording into one clip per subtitle line"
    )
    cutting.add_argument("align", type=Path, help="<name>.align.jsonl next to <name>.mp3")
    cutting.add_argument("srt", type=Path)
    cutting.add_argument("--pad-before-ms", type=float, default=DEFAULT_PAD_BEFORE_MS)
    cutting.add_argument("--pad-after-ms", type=float, default=DEFAULT_PAD_AFTER_MS)
    cutting.add_argument("--out-dir", type=Path, help="output directory (default: <name>_clips next to the MP3)")
    cutting.add_argument("--no-snap", action="store_true", help="cut at the character timings without decoding")

    check: argparse.ArgumentParser = commands.add_parser(
        "verify", help="report clips that start or end at speech level"
    )
    check.add_argument("clips_dir", type=Path)
    return parser.parse_args()


def require(*paths: Path) -> None:
    missing: list[str] = [str(p) for p in paths if not p.exists()]
    if missing:
        raise SystemExit(f"File not found: {', '.join(missing)}")


def main() -> int:
    args: argparse.Namespace = parse_args()
    if args.command == "prepare":
        require(args.srt)
        out: Path = args.out or INPUT_DIR / f"{args.srt.stem}.txt"
        print(f"{prepare(args.srt, out)} lines written to {out}")
        return 0
    if args.command == "cut":
        stem: str = args.align.name.removesuffix(".align.jsonl")
        require(args.align, args.align.with_name(f"{stem}.mp3"), args.srt)
        out_dir: Path = args.out_dir or args.align.with_name(f"{stem}_clips")
        placed: list[Placement] = [
            p
            for p in cut(
                args.align,
                args.srt,
                out_dir,
                args.pad_before_ms,
                args.pad_after_ms,
                snap=not args.no_snap,
            )
            if p
        ]
        kinds: list[str] = [k for p in placed for k in (p.start_kind, p.end_kind)]
        print(f"{len(placed)} lines cut to {out_dir}")
        if not args.no_snap:
            print(
                f"Line edges: {kinds.count('silence')} at a silence, {kinds.count('dip')} at a dip, "
                f"{kinds.count('timing')} at the timings"
            )
        return 0
    require(args.clips_dir / "manifest.json")
    return 1 if verify(args.clips_dir) else 0


if __name__ == "__main__":
    raise SystemExit(main())
