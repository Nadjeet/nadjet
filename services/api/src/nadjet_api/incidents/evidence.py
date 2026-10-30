"""Store an uploaded evidence file and record it on its incident (FR-SEC-003)."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.incidents import service
from nadjet_api.incidents.models import Evidence
from nadjet_api.incidents.service import Change
from nadjet_api.incidents.signing import ChainSigner
from nadjet_api.incidents.store import CHUNK, EvidenceStore


async def upload_chunks(file: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await file.read(CHUNK):
        yield chunk


async def save_evidence(
    session: AsyncSession,
    signer: ChainSigner,
    store: EvidenceStore,
    incident_id: uuid.UUID,
    kind: str,
    chunks: AsyncIterator[bytes],
    extension: str,
    content_type: str,
    *,
    max_bytes: int,
    start_ts: datetime | None = None,
    end_ts: datetime | None = None,
) -> tuple[Evidence, Change]:
    """Write ``chunks`` under the evidence root; SHA-256 is computed server-side.

    Raises ``EvidenceTooLargeError`` above ``max_bytes``. The caller commits.
    """
    evidence_id = uuid.uuid4()
    path = f"{incident_id}/{evidence_id}{extension}"
    stored = await store.save(path, chunks, max_bytes=max_bytes)
    evidence = Evidence(
        id=evidence_id,
        incident_id=incident_id,
        kind=kind,
        path=path,
        content_type=content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    change = await service.add_evidence(session, signer, incident_id, evidence)
    return evidence, change
