from __future__ import annotations

from typing import Final

import pytest

from edp.utils.mp3_frames import (
    FrameHeader,
    audio_offset,
    cut_before_ms,
    frames_duration_ms,
    iter_frames,
    parse_frame_header,
    splice_times,
    to_decoded,
)

_MPEG1_FRAME_MS: Final[float] = 1152 * 1000 / 44_100
_MPEG1_FRAME_BYTES: Final[int] = 417
_BROKEN_FRAME_BYTES: Final[int] = 462


_HEADER_FIELDS: Final[dict[str, int]] = {
    "version": 3,
    "layer": 1,
    "bitrate_index": 9,
    "rate_index": 0,
    "padding": 0,
    "mode": 3,
}


def _header(**overrides: int) -> bytes:
    fields: dict[str, int] = _HEADER_FIELDS | overrides
    value: int = (
        (0x7FF << 21)
        | (fields["version"] << 19)
        | (fields["layer"] << 17)
        | (1 << 16)
        | (fields["bitrate_index"] << 12)
        | (fields["rate_index"] << 10)
        | (fields["padding"] << 9)
        | (fields["mode"] << 6)
    )
    return value.to_bytes(4, byteorder="big")


def _frame(size: int = _MPEG1_FRAME_BYTES, **fields: int) -> bytes:
    return _header(**fields) + bytes(size - 4)


def _id3(payload: bytes, *, footer: bool = False) -> bytes:
    size: int = len(payload)
    syncsafe: bytes = bytes(((size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F))
    flags: int = 0x10 if footer else 0
    return b"ID3\x04\x00" + bytes((flags,)) + syncsafe + payload + (bytes(10) if footer else b"")


def _stream(count: int) -> bytes:
    return _frame() * count


def _broken_frame() -> bytes:
    return _frame(_BROKEN_FRAME_BYTES)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("fields", "size", "sample_rate", "samples", "channels"),
    [
        ({}, 417, 44_100, 1152, 1),
        ({"padding": 1}, 418, 44_100, 1152, 1),
        ({"rate_index": 1, "mode": 0}, 384, 48_000, 1152, 2),
        ({"version": 2, "bitrate_index": 8}, 208, 22_050, 576, 1),
        ({"version": 0, "bitrate_index": 8}, 417, 11_025, 576, 1),
    ],
)
def test_parse_frame_header_mpeg_versions_reads_geometry(
    fields: dict[str, int],
    size: int,
    sample_rate: int,
    samples: int,
    channels: int,
) -> None:
    header: FrameHeader | None = parse_frame_header(b"\x00" + _header(**fields), 1)

    assert header == FrameHeader(
        offset=1,
        size=size,
        sample_rate=sample_rate,
        channels=channels,
        samples=samples,
        version=fields.get("version", 3),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "data",
    [
        b"\xff\xfb\x90",
        b"\x00\x00\x00\x00",
        _header(version=1),
        _header(layer=3),
        _header(bitrate_index=0),
        _header(bitrate_index=15),
        _header(rate_index=3),
    ],
)
def test_parse_frame_header_foreign_bytes_returns_none(data: bytes) -> None:
    assert parse_frame_header(data, 0) is None


@pytest.mark.unit
def test_parse_frame_header_offset_outside_data_returns_none() -> None:
    assert parse_frame_header(_header(), -1) is None
    assert parse_frame_header(_header(), 1) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("version", "rate_index", "duration_ms"),
    [(3, 0, 1152 * 1000 / 44_100), (3, 1, 24.0), (2, 1, 24.0), (2, 2, 36.0), (0, 2, 72.0)],
)
def test_frame_header_duration_ms_mpeg_versions_counts_samples(
    version: int, rate_index: int, duration_ms: float
) -> None:
    header: FrameHeader | None = parse_frame_header(_header(version=version, rate_index=rate_index, bitrate_index=8), 0)

    assert header is not None
    assert header.duration_ms == pytest.approx(duration_ms)


@pytest.mark.unit
def test_audio_offset_id3v2_tag_with_footer_skips_tag_and_footer() -> None:
    assert audio_offset(_id3(b"title", footer=True) + _stream(1)) == 10 + 5 + 10


@pytest.mark.unit
def test_audio_offset_without_tag_returns_zero() -> None:
    assert audio_offset(_stream(1)) == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("data", "message"),
    [(b"ID3\x04\x00", "truncated"), (b"ID3\x04\x00\x00\x80\x00\x00\x00", "invalid ID3v2 size")],
)
def test_audio_offset_broken_id3v2_tag_raises_value_error(data: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        audio_offset(data)


@pytest.mark.unit
def test_iter_frames_id3v2_and_foreign_bytes_yields_only_frames() -> None:
    tag: bytes = _id3(b"provider")
    data: bytes = tag + b"\xff\xfb\x00junk" + _stream(3)

    offsets: list[int] = [frame.offset for frame in iter_frames(data)]

    start: int = len(tag) + 7
    assert offsets == [start, start + _MPEG1_FRAME_BYTES, start + 2 * _MPEG1_FRAME_BYTES]


@pytest.mark.unit
def test_iter_frames_header_without_valid_successor_skips_it() -> None:
    data: bytes = _broken_frame() + _stream(2)

    offsets: list[int] = [frame.offset for frame in iter_frames(data)]

    assert offsets == [_BROKEN_FRAME_BYTES, _BROKEN_FRAME_BYTES + _MPEG1_FRAME_BYTES]


@pytest.mark.unit
def test_frames_duration_ms_clean_stream_sums_frames() -> None:
    assert frames_duration_ms(_id3(b"tag") + _stream(10)) == pytest.approx(10 * _MPEG1_FRAME_MS)


@pytest.mark.unit
def test_frames_duration_ms_broken_frame_counts_one_frame() -> None:
    data: bytes = _stream(5) + _broken_frame() + _stream(5)

    assert frames_duration_ms(data) == pytest.approx(11 * _MPEG1_FRAME_MS)


@pytest.mark.unit
@pytest.mark.parametrize(("overshoot_ms", "dropped_frames"), [(-0.4, 3), (0.4, 3), (0.6, 4)])
def test_cut_before_ms_near_frame_boundary_absorbs_half_millisecond(overshoot_ms: float, dropped_frames: int) -> None:
    data: bytes = _id3(b"tag") + _stream(10)

    rest, dropped = cut_before_ms(data, 3 * _MPEG1_FRAME_MS + overshoot_ms)

    assert rest == _stream(10 - dropped_frames)
    assert dropped == pytest.approx(dropped_frames * _MPEG1_FRAME_MS)


@pytest.mark.unit
def test_cut_before_ms_zero_keeps_all_frames() -> None:
    rest, dropped = cut_before_ms(_id3(b"tag") + _stream(3), 0.0)

    assert rest == _stream(3)
    assert dropped == 0.0


@pytest.mark.unit
def test_cut_before_ms_past_end_returns_empty_data() -> None:
    rest, dropped = cut_before_ms(_stream(3), 1_000.0)

    assert rest == b""
    assert dropped == pytest.approx(3 * _MPEG1_FRAME_MS)


@pytest.mark.unit
def test_cut_before_ms_broken_frame_counts_as_server_time() -> None:
    data: bytes = _stream(2) + _broken_frame() + _stream(2)

    rest, dropped = cut_before_ms(data, 3 * _MPEG1_FRAME_MS)

    assert rest == _stream(2)
    assert dropped == pytest.approx(3 * _MPEG1_FRAME_MS)


@pytest.mark.unit
def test_splice_times_broken_frames_returns_decoded_times() -> None:
    data: bytes = _stream(5) + _broken_frame() + _stream(3) + _broken_frame() + _stream(2)

    assert splice_times(data) == pytest.approx((5 * _MPEG1_FRAME_MS, 8 * _MPEG1_FRAME_MS))


@pytest.mark.unit
def test_splice_times_clean_stream_returns_empty() -> None:
    assert splice_times(_id3(b"tag") + _stream(4)) == ()


@pytest.mark.unit
@pytest.mark.parametrize("foreign", [b"junk" * 11, _id3(b"tag")], ids=["junk", "id3"])
def test_frames_duration_ms_foreign_bytes_before_first_frame_counts_no_frame(foreign: bytes) -> None:
    data: bytes = _id3(b"tag") + foreign + _stream(4)

    assert frames_duration_ms(data) == pytest.approx(4 * _MPEG1_FRAME_MS)
    assert splice_times(data) == ()


@pytest.mark.unit
def test_frames_duration_ms_frame_before_foreign_bytes_at_start_counts_dropped_frame() -> None:
    data: bytes = _id3(b"tag") + _frame() + _id3(b"tag") + _stream(4)

    assert frames_duration_ms(data) == pytest.approx(5 * _MPEG1_FRAME_MS)
    assert splice_times(data) == (0.0,)


@pytest.mark.unit
@pytest.mark.parametrize("foreign", [b"junk" * 11, _id3(b"tag")], ids=["junk", "id3"])
def test_frames_duration_ms_foreign_bytes_after_last_frame_keeps_last_frame(foreign: bytes) -> None:
    data: bytes = _id3(b"tag") + _stream(4) + foreign

    assert frames_duration_ms(data) == pytest.approx(4 * _MPEG1_FRAME_MS)
    assert splice_times(data) == ()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("server_ms", "decoded_ms"),
    [
        (100.0, 100.0),
        (200.0, 200.0),
        (250.0, 250.0 - _MPEG1_FRAME_MS),
        (400.0, 400.0 - 2 * _MPEG1_FRAME_MS),
    ],
)
def test_to_decoded_server_time_subtracts_earlier_splices(server_ms: float, decoded_ms: float) -> None:
    assert to_decoded(server_ms, (200.0, 300.0), _MPEG1_FRAME_MS) == pytest.approx(decoded_ms)


@pytest.mark.unit
def test_to_decoded_without_splices_returns_server_time() -> None:
    assert to_decoded(1234.5, (), _MPEG1_FRAME_MS) == 1234.5
