"""Upload sniffing and MP4 duration (PRD E-12: reject before processing)."""

import struct
from pathlib import Path

from nadjet_api.tryit.media import mp4_duration_s, sniff


def box(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(body), kind) + body


def mvhd(seconds: float, timescale: int = 1000, version: int = 0) -> bytes:
    if version == 1:
        body = struct.pack(">B3xQQIQ", 1, 0, 0, timescale, round(seconds * timescale))
    else:
        body = struct.pack(">B3xIIII", 0, 0, 0, timescale, round(seconds * timescale))
    return box(b"mvhd", body + b"\0" * 80)


def mp4(seconds: float, *, version: int = 0, moov_last: bool = True) -> bytes:
    ftyp = box(b"ftyp", b"isom\0\0\2\0isom")
    mdat = box(b"mdat", b"\0" * 5000)
    moov = box(b"moov", mvhd(seconds, version=version))
    return ftyp + mdat + moov if moov_last else ftyp + moov + mdat


def test_sniff_recognises_mp4_mov_and_webm_only() -> None:
    assert sniff(mp4(1)[:16]) == "mp4"
    assert sniff(b"\0\0\0\x14ftypqt  " + b"\0" * 4) == "mp4"  # QuickTime
    assert sniff(b"\x1a\x45\xdf\xa3" + b"\0" * 12) == "webm"
    for fake in (b"%PDF-1.7 is not a video", b"MZ" + b"\0" * 14, b"GIF89a" + b"\0" * 10, b""):
        assert sniff(fake[:16].ljust(16, b"\0")) is None


def test_duration_is_read_from_the_movie_header_wherever_moov_is(tmp_path: Path) -> None:
    for moov_last in (True, False):
        path = tmp_path / f"a-{moov_last}.mp4"
        path.write_bytes(mp4(30.0, moov_last=moov_last))
        assert mp4_duration_s(path) == 30.0


def test_duration_supports_64_bit_headers_and_other_timescales(tmp_path: Path) -> None:
    path = tmp_path / "b.mp4"
    path.write_bytes(
        box(b"ftyp", b"isom\0\0\2\0") + box(b"moov", mvhd(12.5, timescale=90000, version=1))
    )
    assert mp4_duration_s(path) == 12.5


def test_unreadable_files_have_no_duration_instead_of_failing(tmp_path: Path) -> None:
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"\0\0\0\x08ftyp" + b"\xff" * 40)
    assert mp4_duration_s(junk) is None
    assert mp4_duration_s(tmp_path / "missing.mp4") is None
    truncated = tmp_path / "t.mp4"
    truncated.write_bytes(mp4(10)[:40])
    assert mp4_duration_s(truncated) is None
