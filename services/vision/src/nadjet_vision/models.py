"""Pinned model weights: ``models.lock.yaml`` loader, checksum check and download (TD-25)."""

import hashlib
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

PERMISSIVE_LICENCES = frozenset({"Apache-2.0", "MIT", "BSD-3-Clause", "BSD-2-Clause"})


class ModelWeightError(RuntimeError):
    pass


class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: str
    default: bool = False
    package: str | None = None
    source: str
    filename: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    revision: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{40}$", description="Git revision of a served model"
    )
    served_by: str | None = Field(default=None, description="e.g. vllm: not downloaded here")
    licence: str
    notes: str | None = None

    @model_validator(mode="after")
    def _pinned(self) -> "ModelEntry":
        if self.served_by is None and (self.filename is None or self.sha256 is None):
            raise ValueError(f"{self.id}: a downloaded weight needs filename and sha256")
        if self.served_by is not None and self.revision is None:
            raise ValueError(f"{self.id}: a served model needs a pinned revision")
        return self


def load_lock(path: Path) -> dict[str, ModelEntry]:
    raw = yaml.safe_load(path.read_text())
    entries = [ModelEntry.model_validate(item) for item in raw["models"]]
    return {entry.id: entry for entry in entries}


def licence_violations(entries: dict[str, ModelEntry]) -> list[str]:
    """Ids of default-enabled models whose licence is not on the permissive list."""
    return [e.id for e in entries.values() if e.default and e.licence not in PERMISSIVE_LICENCES]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def verify_weights(path: Path, entry: ModelEntry) -> None:
    actual = sha256_file(path)
    if entry.sha256 is None or actual != entry.sha256:
        raise ModelWeightError(
            f"{entry.id}: checksum mismatch for {path} (expected {entry.sha256}, got {actual})"
        )


def ensure_weights(
    entry: ModelEntry, directory: Path, transport: httpx.BaseTransport | None = None
) -> Path:
    """Return the verified weight file, downloading it from the pinned source if missing."""
    if entry.filename is None or entry.sha256 is None:
        raise ModelWeightError(f"{entry.id}: served by {entry.served_by}, nothing to download")
    target = directory / entry.filename
    if not target.exists():
        directory.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        with (
            httpx.Client(transport=transport, timeout=60.0, follow_redirects=True) as client,
            client.stream("GET", entry.source) as response,
        ):
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
        try:
            verify_weights(partial, entry)
        except ModelWeightError:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(target)
        return target
    verify_weights(target, entry)
    return target
