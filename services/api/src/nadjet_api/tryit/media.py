"""Cheap server-side checks of an upload before anything is analysed (PRD E-12)."""

import struct
from pathlib import Path

EBML_MAGIC = b"\x1a\x45\xdf\xa3"  # WebM / Matroska
ISO_BMFF_BRAND_OFFSET = 4


def sniff(head: bytes) -> str | None:
    """``mp4`` (ISO BMFF: MP4, MOV), ``webm`` or ``None`` when the bytes are not a video."""
    if head[ISO_BMFF_BRAND_OFFSET : ISO_BMFF_BRAND_OFFSET + 4] == b"ftyp":
        return "mp4"
    if head[:4] == EBML_MAGIC:
        return "webm"
    return None


def _boxes(handle, start: int, end: int):  # type: ignore[no-untyped-def]
    pos = start
    while pos + 8 <= end:
        handle.seek(pos)
        header = handle.read(8)
        if len(header) < 8:
            return
        size, kind = struct.unpack(">I4s", header)
        header_len = 8
        if size == 1:
            size = struct.unpack(">Q", handle.read(8))[0]
            header_len = 16
        elif size == 0:
            size = end - pos
        if size < header_len:
            return
        yield kind, pos + header_len, pos + size
        pos += size


def mp4_duration_s(path: Path) -> float | None:
    """Duration from the ``moov/mvhd`` header of an ISO BMFF file; ``None`` if unreadable."""
    try:
        with path.open("rb") as handle:
            end = path.stat().st_size
            for kind, body, box_end in _boxes(handle, 0, end):
                if kind != b"moov":
                    continue
                for inner, inner_body, _ in _boxes(handle, body, box_end):
                    if inner != b"mvhd":
                        continue
                    handle.seek(inner_body)
                    version = handle.read(1)[0]
                    handle.read(3)
                    if version == 1:
                        handle.read(16)
                        timescale, duration = struct.unpack(">IQ", handle.read(12))
                    else:
                        handle.read(8)
                        timescale, duration = struct.unpack(">II", handle.read(8))
                    return duration / timescale if timescale else None
    except (OSError, struct.error, IndexError):
        return None
    return None
