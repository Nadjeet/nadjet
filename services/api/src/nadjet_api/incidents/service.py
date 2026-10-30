"""Incident persistence and business operations (FR-INC-001..008, FR-SEC-003).

Every function works in the caller's transaction and never commits; callers commit and then
publish the returned ``Change`` objects to clients (see ``events.py``).
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit.service import GENESIS_HASH, chain_hash
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Scope
from nadjet_api.incidents.lifecycle import (
    CLOSED_STATUSES,
    IllegalTransitionError,
    IncidentStatus,
    RejectReason,
    check_transition,
)
from nadjet_api.incidents.merge import (
    MERGE_RADIUS_M,
    best_ai_status,
    best_verifier,
    merge_signals,
    should_merge,
)
from nadjet_api.incidents.models import Casualty, Evidence, Incident, IncidentEvent
from nadjet_api.incidents.priority import PriorityResult, TriageTag, compute_priority
from nadjet_api.incidents.shortcodes import pick_short_code
from nadjet_api.incidents.signing import ChainSigner
from nadjet_api.incidents.store import EvidenceNotFoundError, EvidenceStore, sha256_of
from nadjet_shared.events import (
    AiStatus,
    CandidateSource,
    IncidentCandidate,
    TriggerType,
    VerifierResult,
    Witness,
)

_CREATE_LOCK_KEY = 7_204_002
OPEN_STATUS_VALUES = [s.value for s in IncidentStatus if s not in CLOSED_STATUSES]
CLOSED_STATUS_VALUES = [s.value for s in CLOSED_STATUSES]

CREATED = "incident.created"
UPDATED = "incident.updated"
STATUS_CHANGED = "incident.status_changed"


class NotFoundError(Exception):
    """The incident does not exist or is outside the caller's scope."""


@dataclass(frozen=True)
class Change:
    """A committed change to announce to connected clients (ids only, FR-MAP-002)."""

    type: str
    incident_id: uuid.UUID
    version: int
    agencies: tuple[str, ...]
    facilities: tuple[str, ...]


def _change(kind: str, incident: Incident) -> Change:
    return Change(
        kind,
        incident.id,
        incident.version,
        tuple(incident.assigned_agencies),
        tuple(incident.assigned_facilities),
    )


@dataclass(frozen=True)
class IngestResult:
    incident: Incident
    created: bool
    duplicate: bool
    changes: list[Change]


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- event chain


def canonical_event(
    *, incident_id: uuid.UUID, kind: str, actor_id: uuid.UUID | None, payload: Any, ts: datetime
) -> str:
    row = {
        "incident_id": str(incident_id),
        "kind": kind,
        "actor_id": str(actor_id) if actor_id else None,
        "payload": payload,
        "ts": ts.astimezone(UTC).isoformat(),
    }
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


async def append_event(
    session: AsyncSession,
    signer: ChainSigner,
    incident: Incident,
    kind: str,
    actor: User | None,
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> IncidentEvent:
    """Append a hash-chained, signed event. The incident row must be locked by the caller."""
    prev = await session.scalar(
        select(IncidentEvent.hash)
        .where(IncidentEvent.incident_id == incident.id)
        .order_by(IncidentEvent.id.desc())
        .limit(1)
    )
    prev_hash = prev or GENESIS_HASH
    ts = _now()
    actor_id = actor.id if actor else None
    digest = chain_hash(
        prev_hash,
        canonical_event(
            incident_id=incident.id, kind=kind, actor_id=actor_id, payload=payload, ts=ts
        ),
    )
    event = IncidentEvent(
        incident_id=incident.id,
        kind=kind,
        actor_id=actor_id,
        payload=payload,
        ts=ts,
        idempotency_key=idempotency_key,
        prev_hash=prev_hash,
        hash=digest,
        signature=signer.sign(digest),
    )
    session.add(event)
    await session.flush()
    return event


# ---------------------------------------------------------------- priority


def _result_columns(result: PriorityResult) -> dict[str, Any]:
    return {
        "priority": result.priority,
        "priority_reasons": [
            {"rule": r.rule, "level": r.level, "detail": r.detail, "source": r.source}
            for r in result.reasons
        ],
        "to_assess": result.to_assess,
        "mass_casualty": result.mass_casualty,
        "needs_extrication": result.needs_extrication,
        "quality_flags": result.flags,
    }


async def _triage_tags(session: AsyncSession, incident_id: uuid.UUID) -> list[TriageTag]:
    rows = await session.scalars(
        select(Casualty.triage_tag).where(Casualty.incident_id == incident_id)
    )
    return [TriageTag(r) for r in rows]


async def recompute_priority(session: AsyncSession, incident: Incident) -> tuple[int, int]:
    """Recompute priority from stored signals, witness answers and triage; returns (old, new)."""
    old = incident.priority
    result = compute_priority(
        incident.ai_signals,
        VerifierResult.model_validate(incident.verifier_result),
        AiStatus(incident.ai_status) if incident.ai_status else None,
        Witness(people_reported=incident.people_reported, trapped=incident.trapped_reported),
        await _triage_tags(session, incident.id),
    )
    for name, value in _result_columns(result).items():
        setattr(incident, name, value)
    return old, incident.priority


# ---------------------------------------------------------------- ingestion


def incident_type(trigger: TriggerType, ai_status: AiStatus | None = None) -> str:
    """``collision`` only once the AI status is ``confirmed``; until then ``possible_incident``
    (PRD FR-VIS-007: the AI or a rule alone never makes a collision)."""
    fixed = {
        TriggerType.STALLED_VEHICLE: "stalled_vehicle",
        TriggerType.PEDESTRIAN_ON_ROAD: "pedestrian_on_road",
    }.get(trigger)
    if fixed:
        return fixed
    return "collision" if ai_status is AiStatus.CONFIRMED else "possible_incident"


async def _find_mergeable(session: AsyncSession, candidate: IncidentCandidate) -> uuid.UUID | None:
    rows = await session.execute(
        text(
            """
            SELECT id, last_event_time,
                   ST_Distance(geom::geography, p.g) AS distance_m
            FROM incidents,
                 (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS g) AS p
            WHERE status = ANY(:open) AND ST_DWithin(geom::geography, p.g, :radius)
            ORDER BY distance_m
            LIMIT 20
            """
        ),
        {
            "lon": candidate.location.lon,
            "lat": candidate.location.lat,
            "open": OPEN_STATUS_VALUES,
            "radius": MERGE_RADIUS_M,
        },
    )
    for incident_id, last_event_time, distance_m in rows:
        if should_merge(last_event_time, candidate.event_time, distance_m):
            return uuid.UUID(str(incident_id))
    return None


async def ingest_candidate(
    session: AsyncSession, signer: ChainSigner, candidate: IncidentCandidate, key: str
) -> IngestResult:
    """Create an incident from a candidate, or merge it into a nearby open one (FR-INC-001/002).

    Idempotent on ``key``: a redelivered candidate returns the incident it already produced.
    """
    existing = await session.scalar(
        select(Incident)
        .join(IncidentEvent, IncidentEvent.incident_id == Incident.id)
        .where(IncidentEvent.idempotency_key == key)
    )
    if existing:
        return IngestResult(existing, created=False, duplicate=True, changes=[])

    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CREATE_LOCK_KEY})
    target_id = await _find_mergeable(session, candidate)
    payload = {"candidate": candidate.model_dump(mode="json")}
    if target_id:
        incident = await _lock(session, target_id)
        incident.report_count += 1
        incident.last_event_time = max(incident.last_event_time, candidate.event_time)
        incident.ai_signals = merge_signals(incident.ai_signals, candidate.signals)
        incident.verifier_result = best_verifier(
            VerifierResult.model_validate(incident.verifier_result), candidate.verifier
        ).model_dump(mode="json")
        if incident.ai_status:
            incident.ai_status = best_ai_status(
                AiStatus(incident.ai_status), candidate.ai_status
            ).value
            if incident.ai_status == AiStatus.CONFIRMED and incident.type == "possible_incident":
                incident.type = "collision"
        if candidate.witness:
            incident.trapped_reported = incident.trapped_reported or candidate.witness.trapped
            known = incident.people_reported
            reported = candidate.witness.people_reported
            if reported is not None:
                incident.people_reported = max(known or 0, reported)
        old, new = await recompute_priority(session, incident)
        payload["priority"] = {"from": old, "to": new}
        incident.version += 1
        await append_event(
            session, signer, incident, "merged_candidate", None, payload, idempotency_key=key
        )
        return IngestResult(incident, False, False, [_change(UPDATED, incident)])

    incident = await _new_incident(session, signer, candidate, payload, key)
    return IngestResult(incident, True, False, [_change(CREATED, incident)])


async def _new_incident(
    session: AsyncSession,
    signer: ChainSigner,
    candidate: IncidentCandidate,
    payload: dict[str, Any],
    key: str | None,
    *,
    actor: User | None = None,
    status: IncidentStatus = IncidentStatus.CANDIDATE,
    ai_applicable: bool = True,
) -> Incident:
    incident_id = uuid.uuid4()
    taken = set(
        await session.scalars(
            select(Incident.short_code).where(Incident.status.in_(OPEN_STATUS_VALUES))
        )
    )
    ai_status = candidate.ai_status if ai_applicable else None
    result = compute_priority(
        candidate.signals, candidate.verifier, ai_status, candidate.witness, None
    )
    loc = candidate.location
    witness = candidate.witness
    incident = Incident(
        id=incident_id,
        short_code=pick_short_code(incident_id, taken),
        type=incident_type(candidate.trigger, ai_status),
        status=status.value,
        lat=loc.lat,
        lon=loc.lon,
        road=loc.road,
        pk_km=loc.pk_km,
        wilaya=loc.wilaya,
        source=candidate.source.value,
        camera_id=candidate.camera_id,
        event_time=candidate.event_time,
        last_event_time=candidate.event_time,
        detected_at=candidate.detected_at,
        ai_status=ai_status.value if ai_status else None,
        ai_signals=candidate.signals,
        verifier_result=candidate.verifier.model_dump(mode="json"),
        people_reported=witness.people_reported if witness else None,
        trapped_reported=bool(witness and witness.trapped),
        report_count=1,
        version=1,
        **_result_columns(result),
    )
    session.add(incident)
    await session.flush()
    await append_event(session, signer, incident, "created", actor, payload, idempotency_key=key)
    return incident


async def create_manual(
    session: AsyncSession,
    signer: ChainSigner,
    actor: User,
    candidate: IncidentCandidate,
    notes: str | None = None,
) -> IngestResult:
    """Operator-created incident from a phone call: already verified (FR-INC-007)."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CREATE_LOCK_KEY})
    payload: dict[str, Any] = {"candidate": candidate.model_dump(mode="json")}
    if notes:
        payload["notes"] = notes
    incident = await _new_incident(
        session,
        signer,
        candidate,
        payload,
        None,
        actor=actor,
        status=IncidentStatus.VERIFIED,
        ai_applicable=False,
    )
    return IngestResult(incident, True, False, [_change(CREATED, incident)])


async def create_callback_incident(
    session: AsyncSession,
    signer: ChainSigner,
    *,
    location_text: str,
    phone: str,
    event_time: datetime,
    key: str,
) -> IngestResult:
    """Unverified citizen SMS report with no coordinates, flagged for operator call-back.

    It has no position, so it is never merged (FR-NTF-005). Idempotent on ``key``.
    """
    existing = await session.scalar(
        select(Incident)
        .join(IncidentEvent, IncidentEvent.incident_id == Incident.id)
        .where(IncidentEvent.idempotency_key == key)
    )
    if existing:
        return IngestResult(existing, created=False, duplicate=True, changes=[])
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CREATE_LOCK_KEY})
    incident_id = uuid.uuid4()
    taken = set(
        await session.scalars(
            select(Incident.short_code).where(Incident.status.in_(OPEN_STATUS_VALUES))
        )
    )
    verifier = VerifierResult(available=False)
    result = compute_priority({}, verifier, AiStatus.INSUFFICIENT_EVIDENCE, None, None)
    columns = _result_columns(result)
    columns["quality_flags"] = [*columns["quality_flags"], "callback_needed"]
    incident = Incident(
        id=incident_id,
        short_code=pick_short_code(incident_id, taken),
        type="crash",
        status=IncidentStatus.CANDIDATE.value,
        lat=None,
        lon=None,
        location_text=location_text,
        source=CandidateSource.CITIZEN.value,
        event_time=event_time,
        last_event_time=event_time,
        detected_at=event_time,
        ai_status=AiStatus.INSUFFICIENT_EVIDENCE.value,
        ai_signals={},
        verifier_result=verifier.model_dump(mode="json"),
        trapped_reported=False,
        report_count=1,
        version=1,
        **columns,
    )
    session.add(incident)
    await session.flush()
    payload = {"sms": {"phone": phone, "location_text": location_text}}
    await append_event(session, signer, incident, "created", None, payload, idempotency_key=key)
    return IngestResult(incident, True, False, [_change(CREATED, incident)])


# ---------------------------------------------------------------- lifecycle


async def _lock(session: AsyncSession, incident_id: uuid.UUID) -> Incident:
    incident = await session.scalar(
        select(Incident)
        .where(Incident.id == incident_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if incident is None:
        raise NotFoundError(str(incident_id))
    return incident


def visible_clause(scope: Scope) -> Any:
    """SQL condition limiting incidents to ``scope`` (FR-SEC-002); ``None`` means no limit."""
    if scope.unrestricted:
        return None
    if scope.agency:
        return Incident.assigned_agencies.contains([scope.agency.value])
    return Incident.assigned_facilities.contains([scope.facility_id])


def can_see(incident: Incident, scope: Scope) -> bool:
    if scope.unrestricted:
        return True
    if scope.agency:
        return scope.agency.value in incident.assigned_agencies
    return scope.facility_id in incident.assigned_facilities


async def get_visible(
    session: AsyncSession, incident_id: uuid.UUID, scope: Scope, *, lock: bool = False
) -> Incident:
    incident = await (_lock(session, incident_id) if lock else session.get(Incident, incident_id))
    if incident is None or not can_see(incident, scope):
        raise NotFoundError(str(incident_id))
    return incident


async def transition(
    session: AsyncSession,
    signer: ChainSigner,
    incident_id: uuid.UUID,
    target: IncidentStatus,
    actor: User,
    scope: Scope,
    *,
    reason: RejectReason | None = None,
) -> Change:
    """Move an incident along the lifecycle; ``IllegalTransitionError`` for illegal moves."""
    incident = await get_visible(session, incident_id, scope, lock=True)
    current = IncidentStatus(incident.status)
    check_transition(current, target)
    incident.status = target.value
    if reason:
        incident.reject_reason = reason.value
    incident.version += 1
    payload: dict[str, Any] = {"from": current.value, "to": target.value}
    if reason:
        payload["reason"] = reason.value
    await append_event(session, signer, incident, "status_changed", actor, payload)
    return _change(STATUS_CHANGED, incident)


class MergeError(Exception):
    """The merge target is the incident itself or is no longer open."""


async def merge_into(
    session: AsyncSession,
    signer: ChainSigner,
    incident_id: uuid.UUID,
    target_id: uuid.UUID,
    actor: User,
    scope: Scope,
) -> list[Change]:
    """Operator merges a candidate into another open incident (FR-INC-002, E-14).

    The candidate becomes ``merged``; the target keeps one report more per source report and
    recomputes its priority from the combined signals.
    """
    if incident_id == target_id:
        raise MergeError("cannot merge an incident into itself")
    # Lock in id order so two opposite merges cannot deadlock.
    first, second = sorted((incident_id, target_id), key=str)
    await get_visible(session, first, scope, lock=True)
    await get_visible(session, second, scope, lock=True)
    source = await get_visible(session, incident_id, scope)
    target = await get_visible(session, target_id, scope)
    current = IncidentStatus(source.status)
    check_transition(current, IncidentStatus.MERGED)
    if IncidentStatus(target.status) in CLOSED_STATUSES:
        raise MergeError(f"cannot merge into a {target.status} incident")

    source.status = IncidentStatus.MERGED.value
    source.merged_into = target.id
    source.version += 1
    await append_event(
        session,
        signer,
        source,
        "status_changed",
        actor,
        {"from": current.value, "to": IncidentStatus.MERGED.value, "into": str(target.id)},
    )

    target.report_count += source.report_count
    target.last_event_time = max(target.last_event_time, source.last_event_time)
    target.ai_signals = merge_signals(target.ai_signals, source.ai_signals)
    target.verifier_result = best_verifier(
        VerifierResult.model_validate(target.verifier_result),
        VerifierResult.model_validate(source.verifier_result),
    ).model_dump(mode="json")
    if target.ai_status and source.ai_status:
        target.ai_status = best_ai_status(
            AiStatus(target.ai_status), AiStatus(source.ai_status)
        ).value
    target.trapped_reported = target.trapped_reported or source.trapped_reported
    if source.people_reported is not None:
        target.people_reported = max(target.people_reported or 0, source.people_reported)
    old, new = await recompute_priority(session, target)
    target.version += 1
    await append_event(
        session,
        signer,
        target,
        "incident_merged_in",
        actor,
        {"source": str(source.id), "priority": {"from": old, "to": new}},
    )
    return [_change(STATUS_CHANGED, source), _change(UPDATED, target)]


async def add_casualty(
    session: AsyncSession,
    signer: ChainSigner,
    incident_id: uuid.UUID,
    actor: User,
    scope: Scope,
    fields: dict[str, Any],
) -> tuple[Casualty, Change]:
    """Record a triage entry and recompute priority; triage overrides the AI (FR-INC-004)."""
    incident = await get_visible(session, incident_id, scope, lock=True)
    if IncidentStatus(incident.status) in CLOSED_STATUSES:
        raise IllegalTransitionError(IncidentStatus(incident.status), IncidentStatus.ON_SCENE)
    casualty = Casualty(incident_id=incident.id, reported_by=actor.id, at=_now(), **fields)
    session.add(casualty)
    await session.flush()
    old, new = await recompute_priority(session, incident)
    incident.version += 1
    await append_event(
        session,
        signer,
        incident,
        "casualty_added",
        actor,
        {
            "casualty_id": str(casualty.id),
            "triage_tag": casualty.triage_tag,
            "source": casualty.source,
            "priority": {"from": old, "to": new},
        },
    )
    return casualty, _change(UPDATED, incident)


async def add_evidence(
    session: AsyncSession,
    signer: ChainSigner,
    incident_id: uuid.UUID,
    evidence: Evidence,
) -> Change:
    incident = await _lock(session, incident_id)
    session.add(evidence)
    incident.version += 1
    await append_event(
        session,
        signer,
        incident,
        "evidence_added",
        None,
        {
            "evidence_id": str(evidence.id),
            "kind": evidence.kind,
            "path": evidence.path,
            "sha256": evidence.sha256,
            "size_bytes": evidence.size_bytes,
        },
    )
    return _change(UPDATED, incident)


# ---------------------------------------------------------------- queries


@dataclass(frozen=True)
class IncidentFilters:
    status: IncidentStatus | None = None
    priority: int | None = None
    source: CandidateSource | None = None
    wilaya: str | None = None
    to_assess: bool | None = None
    open_only: bool = False


def list_query(scope: Scope, filters: IncidentFilters) -> Select[Any]:
    query = select(Incident)
    clause = visible_clause(scope)
    conditions = [clause] if clause is not None else []
    if filters.status:
        conditions.append(Incident.status == filters.status.value)
    if filters.priority:
        conditions.append(Incident.priority == filters.priority)
    if filters.source:
        conditions.append(Incident.source == filters.source.value)
    if filters.wilaya:
        conditions.append(Incident.wilaya == filters.wilaya)
    if filters.to_assess is not None:
        conditions.append(Incident.to_assess == filters.to_assess)
    if filters.open_only:
        conditions.append(Incident.status.notin_(CLOSED_STATUS_VALUES))
    return query.where(*conditions)


async def list_incidents(
    session: AsyncSession, scope: Scope, filters: IncidentFilters, limit: int, offset: int
) -> tuple[list[Incident], int]:
    base = list_query(scope, filters)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(Incident.priority, Incident.detected_at.desc(), Incident.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all()), int(total or 0)


# ---------------------------------------------------------------- integrity


@dataclass(frozen=True)
class IntegrityFailure:
    kind: str  # "event" | "signature" | "file"
    ref: str
    detail: str


@dataclass(frozen=True)
class IntegrityReport:
    valid: bool
    events_checked: int
    files_checked: int
    failures: list[IntegrityFailure]


def check_event_chain(events: list[IncidentEvent], signer: ChainSigner) -> list[IntegrityFailure]:
    """Recompute the chain and verify the signed head; returns the failures found."""
    failures: list[IntegrityFailure] = []
    prev_hash = GENESIS_HASH
    for event in events:
        digest = chain_hash(
            prev_hash,
            canonical_event(
                incident_id=event.incident_id,
                kind=event.kind,
                actor_id=event.actor_id,
                payload=event.payload,
                ts=event.ts,
            ),
        )
        if event.prev_hash != prev_hash or event.hash != digest:
            failures.append(IntegrityFailure("event", str(event.id), "hash chain mismatch"))
            return failures
        prev_hash = event.hash
    if events and not signer.verify(events[-1].hash, events[-1].signature):
        failures.append(IntegrityFailure("signature", str(events[-1].id), "invalid head signature"))
    return failures


async def verify_integrity(
    session: AsyncSession, signer: ChainSigner, store: EvidenceStore, incident_id: uuid.UUID
) -> IntegrityReport:
    """Recompute file hashes and the event chain (FR-SEC-003, AC-SEC-003.1)."""
    events = list(
        await session.scalars(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.id)
            .execution_options(populate_existing=True)
        )
    )
    failures = check_event_chain(events, signer)
    files = list(
        await session.scalars(
            select(Evidence)
            .where(Evidence.incident_id == incident_id)
            .order_by(Evidence.created_at)
            .execution_options(populate_existing=True)
        )
    )
    # The evidence table is not append-only: trust the hash recorded in the signed chain.
    chained = {
        e.payload.get("evidence_id"): e.payload.get("sha256")
        for e in events
        if e.kind == "evidence_added"
    }
    for item in files:
        expected = chained.get(str(item.id))
        if expected is None or expected != item.sha256:
            failures.append(IntegrityFailure("file", item.path, "hash not in signed chain"))
            continue
        try:
            actual = await sha256_of(store, item.path)
        except EvidenceNotFoundError:
            failures.append(IntegrityFailure("file", item.path, "file missing"))
            continue
        if actual != expected:
            failures.append(IntegrityFailure("file", item.path, "sha256 mismatch"))
    present = {str(item.id) for item in files}
    for evidence_id in chained.keys() - present:
        failures.append(IntegrityFailure("file", str(evidence_id), "evidence record missing"))
    return IntegrityReport(not failures, len(events), len(files), failures)
