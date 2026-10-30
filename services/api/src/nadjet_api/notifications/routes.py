"""Notification API: SMS gateway webhooks, web-push subscriptions, CAP export."""

import hashlib
import hmac
import logging
import time
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.deps import current_scope, current_user
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Scope
from nadjet_api.config import Settings
from nadjet_api.db import get_session
from nadjet_api.dispatch.service import make_proposer
from nadjet_api.incidents import service
from nadjet_api.incidents.deps import RedisDep, SignerDep, announce
from nadjet_api.notifications import inbound
from nadjet_api.notifications import service as notifications
from nadjet_api.notifications.cap import build_cap
from nadjet_api.notifications.channels import SMS, DeliveryRequest, NotificationChannel
from nadjet_api.notifications.grammar import SMS_MAX_CHARS, normalize_phone
from nadjet_api.notifications.models import PushSubscription

log = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RATE_WINDOW_S = 600
RATE_LIMIT = 30  # inbound SMS per phone per window; the gateway SIM is a shared, paid resource
DEDUPE_TTL_S = 3600


# ---------------------------------------------------------------- gateway webhooks


class WebhookPayload(BaseModel):
    """The ``payload`` of a capcom6 webhook; fields differ per event, all optional here."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message_id: str = Field(validation_alias=AliasChoices("messageId", "message_id"), default="")
    message: str | None = None
    sender: str | None = Field(
        default=None, validation_alias=AliasChoices("sender", "phoneNumber", "phone_number")
    )
    reason: str | None = None


class WebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event: str
    id: str | None = None
    payload: WebhookPayload = Field(default_factory=WebhookPayload)


class SmsAck(BaseModel):
    status: Literal["processed", "duplicate", "throttled", "ignored"]


def signature_valid(
    secret: str,
    body: bytes,
    signature: str | None,
    timestamp: str | None,
    now: float,
    tolerance: int,
) -> bool:
    """capcom6 scheme: hex HMAC-SHA256 over the raw body followed by ``X-Timestamp``."""
    if not signature or not timestamp or not timestamp.isdigit():
        return False
    if abs(now - int(timestamp)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), body + timestamp.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), signature.lower().encode())


async def verify_gateway(
    request: Request,
    x_signature: Annotated[str | None, Header()] = None,
    x_timestamp: Annotated[str | None, Header()] = None,
    token: Annotated[str | None, Query()] = None,
) -> None:
    """Accept only the SMS gateway: a valid HMAC signature, or the shared secret as ``?token=``.

    The token form covers private-server setups that do not sign webhooks (TQ-03).
    """
    settings: Settings = request.app.state.settings
    # `.env.example` ships `NADJET_SMS_WEBHOOK_SECRET=`: an empty secret is no secret at all.
    secret = settings.sms_webhook_secret.get_secret_value() if settings.sms_webhook_secret else ""
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SMS gateway is not configured")
    if token and hmac.compare_digest(token.encode(), secret.encode()):
        return
    body = await request.body()
    if not signature_valid(
        secret, body, x_signature, x_timestamp, time.time(), settings.sms_webhook_tolerance_s
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")


async def _reply(request: Request, phone: str, text: str) -> None:
    """Best effort: a lost reply must not make the gateway redeliver (and replay) the SMS."""
    channels: dict[str, NotificationChannel] = getattr(request.app.state, "channels", {})
    channel = channels.get(SMS)
    if channel is None:
        log.warning("no SMS channel configured, reply to %s dropped", phone)
        return
    try:
        await channel.send(DeliveryRequest(None, phone, text[:SMS_MAX_CHARS], str(uuid.uuid4())))
    except Exception:
        log.exception("reply to %s failed", phone)


@router.post(
    "/sms/inbound",
    dependencies=[Depends(verify_gateway)],
    responses={401: {"description": "Invalid webhook signature"}},
)
async def sms_inbound(
    envelope: WebhookEnvelope,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
) -> SmsAck:
    """``sms:received`` webhook: parse the SMS, apply it, answer the sender (FR-NTF-005)."""
    payload = envelope.payload
    if envelope.event != "sms:received" or not payload.sender or payload.message is None:
        return SmsAck(status="ignored")
    message_id = payload.message_id or envelope.id or ""
    dedupe_key = f"sms:in:{message_id}"
    if message_id and not await redis.set(dedupe_key, 1, nx=True, ex=DEDUPE_TTL_S):
        return SmsAck(status="duplicate")
    phone = normalize_phone(payload.sender)
    rate_key = f"sms:rate:{phone}"
    count = await redis.incr(rate_key)
    if count == 1:
        await redis.expire(rate_key, RATE_WINDOW_S)
    if count > RATE_LIMIT:
        return SmsAck(status="throttled")
    try:
        settings: Settings = request.app.state.settings
        propose = make_proposer(
            session, getattr(request.app.state, "router", None), settings.routing_urban_multiplier
        )
        result = await inbound.handle_sms(
            session, signer, payload.sender, payload.message, message_id, propose
        )
        await session.commit()
    except Exception:
        # Not applied: let the gateway's redelivery through instead of dropping the SMS.
        await redis.delete(dedupe_key)
        raise
    await announce(redis, result.changes)
    await _reply(request, phone, result.reply)
    return SmsAck(status="processed")


@router.post("/sms/status", dependencies=[Depends(verify_gateway)])
async def sms_status(envelope: WebhookEnvelope, session: SessionDep) -> SmsAck:
    """``sms:sent|delivered|failed`` webhooks: record the delivery status (FR-NTF-003)."""
    if envelope.event not in ("sms:sent", "sms:delivered", "sms:failed"):
        return SmsAck(status="ignored")
    known = await notifications.record_receipt(
        session, envelope.payload.message_id, envelope.event, envelope.payload.reason
    )
    await session.commit()
    return SmsAck(status="processed" if known else "ignored")


# ---------------------------------------------------------------- web push


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1)
    auth: str = Field(min_length=1)


class PushSubscriptionIn(BaseModel):
    """The browser's ``PushSubscription.toJSON()``."""

    model_config = ConfigDict(extra="ignore")

    endpoint: str = Field(min_length=1, max_length=2048, pattern=r"^https://")
    keys: PushKeys


class PushPublicKey(BaseModel):
    public_key: str


@router.get("/push/public-key", responses={503: {"description": "Web push is not configured"}})
async def push_public_key(request: Request) -> PushPublicKey:
    """The VAPID public key the browser needs to subscribe (``applicationServerKey``)."""
    settings: Settings = request.app.state.settings
    if not settings.vapid_public_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Web push is not configured")
    return PushPublicKey(public_key=settings.vapid_public_key)


@router.post("/push/subscriptions", status_code=status.HTTP_201_CREATED)
async def subscribe_push(
    body: PushSubscriptionIn,
    session: SessionDep,
    user: Annotated[User, Depends(current_user)],
) -> None:
    """Register the caller's browser for push alerts; re-posting an endpoint updates it."""
    stmt = insert(PushSubscription).values(
        user_id=user.id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[PushSubscription.endpoint],
            set_={"user_id": user.id, "p256dh": body.keys.p256dh, "auth": body.keys.auth},
        )
    )
    await session.commit()


# ---------------------------------------------------------------- CAP


@router.get(
    "/incidents/{incident_id}.cap.xml",
    response_class=Response,
    responses={200: {"content": {"application/cap+xml": {}}}, 404: {"description": "Not found"}},
)
async def incident_cap(
    incident_id: uuid.UUID,
    session: SessionDep,
    scope: Annotated[Scope, Depends(current_scope)],
) -> Response:
    """The incident as an OASIS CAP 1.2 alert, in Arabic and French (FR-INC-009)."""
    try:
        incident = await service.get_visible(session, incident_id, scope)
    except service.NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found") from None
    return Response(build_cap(incident), media_type="application/cap+xml")
