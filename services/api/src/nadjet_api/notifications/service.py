"""Queueing, delivery, retries and receipts (FR-NTF-001/004/007, E-07).

Like the incident service, every function works in the caller's transaction and never commits.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.models import User
from nadjet_api.incidents.models import Incident
from nadjet_api.incidents.service import UPDATED, Change, _change, append_event
from nadjet_api.incidents.signing import ChainSigner
from nadjet_api.notifications.channels import (
    PUSH,
    SMS,
    DeliveryError,
    DeliveryRequest,
    NotificationChannel,
)
from nadjet_api.notifications.grammar import format_alert, normalize_phone
from nadjet_api.notifications.models import (
    DELIVERED,
    FAILED,
    QUEUED,
    SENT,
    Notification,
    PushSubscription,
)

KIND_ALERT = "alert"


# ---------------------------------------------------------------- retry policy (pure)


def retry_delay_s(attempts: int, base_s: int) -> int:
    """Wait before re-checking after ``attempts`` sends: ``base``, ``2*base``, ``4*base`` ..."""
    return int(base_s * 2 ** (attempts - 1))


def out_of_attempts(attempts: int, max_retries: int) -> bool:
    """The first send plus ``max_retries`` retries have all been used."""
    return attempts >= 1 + max_retries


# ---------------------------------------------------------------- queueing


async def queue_notification(
    session: AsyncSession,
    *,
    incident_id: uuid.UUID,
    kind: str,
    channel: str,
    recipient: str,
    text: str,
    meta: dict[str, Any] | None = None,
) -> Notification | None:
    """Record a notification; ``None`` when it was already queued (FR-NTF-007)."""
    row_id = await session.scalar(
        insert(Notification)
        .values(
            incident_id=incident_id,
            kind=kind,
            channel=channel,
            recipient=recipient,
            payload=text,
            meta=meta or {},
            status=QUEUED,
            attempts=0,
        )
        .on_conflict_do_nothing(constraint="uq_notif_once")
        .returning(Notification.id)
    )
    if row_id is None:
        return None
    return await session.get(Notification, row_id, populate_existing=True)


def alert_text(incident: Incident, vehicles: int | None = None) -> str:
    """The outbound SMS line (FR-NTF-002); position-less incidents are not alertable."""
    if incident.lat is None or incident.lon is None:
        raise ValueError("incident has no position yet (call-back pending)")
    return format_alert(
        kind="ACC",
        priority=incident.priority,
        lat=incident.lat,
        lon=incident.lon,
        road=incident.road,
        pk_km=incident.pk_km,
        vehicles=vehicles if vehicles is not None else _vehicles(incident),
        short_code=incident.short_code,
    )


def _vehicles(incident: Incident) -> int | None:
    count = incident.ai_signals.get("vehicle_count")
    return int(count) if count else None


async def queue_alerts(
    session: AsyncSession, incident: Incident, users: list[User], *, kind: str = KIND_ALERT
) -> list[Notification]:
    """SMS and push alerts for ``users`` (FR-NTF-001); duplicates are skipped.

    The caller commits, then enqueues the returned notifications (``jobs.enqueue_all``).
    """
    text = alert_text(incident)
    created: list[Notification] = []
    for user in users:
        if user.phone:
            sms = await queue_notification(
                session,
                incident_id=incident.id,
                kind=kind,
                channel=SMS,
                recipient=normalize_phone(user.phone),
                text=text,
            )
            if sms:
                created.append(sms)
        subscriptions = await session.scalars(
            select(PushSubscription).where(PushSubscription.user_id == user.id)
        )
        for sub in subscriptions:
            push = await queue_notification(
                session,
                incident_id=incident.id,
                kind=kind,
                channel=PUSH,
                recipient=sub.endpoint,
                text=text,
                meta={"p256dh": sub.p256dh, "auth": sub.auth},
            )
            if push:
                created.append(push)
    return created


# ---------------------------------------------------------------- delivery


@dataclass
class Outcome:
    """What the job runner does next: re-run after ``retry_in_s``, and announce ``changes``."""

    retry_in_s: int | None = None
    changes: list[Change] = field(default_factory=list)


async def process(
    session: AsyncSession,
    channels: dict[str, NotificationChannel],
    signer: ChainSigner,
    notification_id: uuid.UUID,
    *,
    base_s: int,
    max_retries: int,
) -> Outcome:
    """Send, or re-send when the previous send was not delivered in time (FR-NTF-004).

    Runs once right after queueing and again after each back-off delay.
    """
    n = await session.scalar(
        select(Notification)
        .where(Notification.id == notification_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if n is None or n.status in (DELIVERED, FAILED):
        return Outcome()
    if out_of_attempts(n.attempts, max_retries):
        return await _fail(session, signer, n, n.last_error or "not delivered in time")
    channel = channels.get(n.channel)
    if channel is None:
        return await _fail(session, signer, n, f"channel {n.channel} is not configured")

    n.attempts += 1
    n.provider_ref = str(uuid.uuid4())
    n.updated_at = datetime.now(UTC)
    request = DeliveryRequest(n.incident_id, n.recipient, n.payload, n.provider_ref, n.meta)
    try:
        await channel.send(request)
    except Exception as exc:  # e.g. requests errors from pywebpush: must still reach E-07
        n.last_error = str(exc)[:500]
        n.status = QUEUED
        if isinstance(exc, DeliveryError) and exc.permanent:
            return await _fail(session, signer, n, n.last_error, alert=False)
        return Outcome(retry_in_s=retry_delay_s(n.attempts, base_s))
    n.last_error = None
    if channel.reports_delivery:
        n.status = SENT  # the gateway confirms later; the delayed re-run checks
        return Outcome(retry_in_s=retry_delay_s(n.attempts, base_s))
    n.status = DELIVERED
    return Outcome()


async def _fail(
    session: AsyncSession,
    signer: ChainSigner,
    n: Notification,
    reason: str,
    *,
    alert: bool = True,
) -> Outcome:
    """Final failure: record it and warn the operators through the incident timeline (E-07)."""
    n.status = FAILED
    n.last_error = reason[:500]
    n.updated_at = datetime.now(UTC)
    if not alert:
        return Outcome()
    incident = await session.get(
        Incident, n.incident_id, with_for_update=True, populate_existing=True
    )
    if incident is None:
        return Outcome()
    incident.version += 1
    await append_event(
        session,
        signer,
        incident,
        "notification_failed",
        None,
        {"channel": n.channel, "kind": n.kind, "attempts": n.attempts, "reason": n.last_error},
    )
    return Outcome(changes=[_change(UPDATED, incident)])


async def record_receipt(
    session: AsyncSession, provider_ref: str, event: str, reason: str | None = None
) -> bool:
    """Apply a gateway delivery report; ``False`` when the reference is unknown."""
    n = await session.scalar(
        select(Notification)
        .where(Notification.provider_ref == provider_ref)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if n is None:
        return False
    if event == "sms:delivered" and n.status != FAILED:
        n.status = DELIVERED
    elif event == "sms:failed" and n.status == SENT:
        n.last_error = (reason or "gateway reported failure")[:500]
        n.status = QUEUED  # the delayed re-run retries it
    n.updated_at = datetime.now(UTC)
    return True
