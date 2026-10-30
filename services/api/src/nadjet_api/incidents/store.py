"""Evidence storage behind an interface (local volume now; replaceable, NFR-MAINT-002)."""

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anyio

CHUNK = 64 * 1024


class EvidenceTooLargeError(Exception):
    """The upload exceeded the configured size limit."""


class EvidenceNotFoundError(Exception):
    """The stored file does not exist."""


@dataclass(frozen=True)
class StoredFile:
    sha256: str
    size_bytes: int


class EvidenceStore(Protocol):
    async def save(self, path: str, chunks: AsyncIterator[bytes], *, max_bytes: int) -> StoredFile:
        """Store ``chunks`` at ``path``; SHA-256 is computed here, server-side."""
        ...

    def read(self, path: str) -> AsyncIterator[bytes]:
        """Stream the stored bytes; raises ``EvidenceNotFoundError`` when missing."""
        ...


class LocalEvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _resolve(self, path: str) -> Path:
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("path escapes the evidence root")
        return target

    async def save(self, path: str, chunks: AsyncIterator[bytes], *, max_bytes: int) -> StoredFile:
        target = anyio.Path(self._resolve(path))
        await target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        try:
            async with await target.open("wb") as handle:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise EvidenceTooLargeError
                    digest.update(chunk)
                    await handle.write(chunk)
        except BaseException:
            await target.unlink(missing_ok=True)
            raise
        return StoredFile(sha256=digest.hexdigest(), size_bytes=size)

    async def read(self, path: str) -> AsyncIterator[bytes]:
        target = anyio.Path(self._resolve(path))
        if not await target.is_file():
            raise EvidenceNotFoundError(path)
        async with await target.open("rb") as handle:
            while chunk := await handle.read(CHUNK):
                yield chunk


async def sha256_of(store: EvidenceStore, path: str) -> str:
    digest = hashlib.sha256()
    async for chunk in store.read(path):
        digest.update(chunk)
    return digest.hexdigest()
