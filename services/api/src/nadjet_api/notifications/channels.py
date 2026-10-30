"""Notification channels behind one interface (FR-NTF-001/003, NFR-MAINT-002, TD-13/14)."""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from pywebpush import WebPushException, webpush

from nadjet_api.config import Settings

SMS, PUSH, TELEGRAM = "sms", "push", "telegram"
HTTP_TIMEOUT_S = 10.0


class DeliveryError(Exception):
    """A send failed; ``permanent`` means retrying cannot help (e.g. a dead push endpoint)."""

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


@dataclass(frozen=True)
class DeliveryRequest:
    incident_id: uuid.UUID | None  # None for replies to inbound SMS
    recipient: str
    text: str
    ref: str  # id the provider echoes back in delivery reports
    meta: dict[str, Any] = field(default_factory=dict)


class NotificationChannel(Protocol):
    name: str
    #: True when the provider reports delivery later (webhook); False when accepted == delivered.
    reports_delivery: bool

    async def send(self, request: DeliveryRequest) -> None: ...


class SmsGatewayChannel:
    """capcom6 SMS Gateway for Android, private-server mode (REST ``/3rdparty/v1/messages``)."""

    name = SMS
    reports_delivery = True

    def __init__(self, client: httpx.AsyncClient, base_url: str, user: str, password: str) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/api/3rdparty/v1/messages"
        self._auth = httpx.BasicAuth(user, password)

    async def send(self, request: DeliveryRequest) -> None:
        body = {
            "id": request.ref,
            "textMessage": {"text": request.text},
            "phoneNumbers": [request.recipient],
            "withDeliveryReport": True,
        }
        try:
            response = await self._client.post(
                self._url, json=body, auth=self._auth, timeout=HTTP_TIMEOUT_S
            )
        except httpx.HTTPError as exc:  # gateway or phone offline (E-07): retried by the caller
            raise DeliveryError(f"gateway unreachable: {exc!r}") from exc
        if response.status_code >= 400:
            raise DeliveryError(f"gateway answered {response.status_code}")


class WebPushChannel:
    """Web Push with VAPID (``pywebpush``). The recipient is the subscription endpoint."""

    name = PUSH
    reports_delivery = False

    def __init__(self, private_key: str, subject: str) -> None:
        self._key = private_key
        self._claims = {"sub": subject}

    async def send(self, request: DeliveryRequest) -> None:
        subscription = {
            "endpoint": request.recipient,
            "keys": {"p256dh": request.meta["p256dh"], "auth": request.meta["auth"]},
        }
        data = json.dumps(
            {
                "incident_id": str(request.incident_id) if request.incident_id else None,
                "text": request.text,
            }
        )
        try:
            # pywebpush is blocking (requests): keep it off the event loop.
            await asyncio.to_thread(
                webpush,
                subscription,
                data,
                vapid_private_key=self._key,
                vapid_claims=dict(self._claims),
                ttl=3600,
                timeout=HTTP_TIMEOUT_S,
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            raise DeliveryError(f"push failed: {exc}", permanent=status in (404, 410)) from exc


class TelegramChannel:
    """Optional Telegram Bot API channel. The recipient is a chat id."""

    name = TELEGRAM
    reports_delivery = False

    def __init__(self, client: httpx.AsyncClient, token: str) -> None:
        self._client = client
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"

    async def send(self, request: DeliveryRequest) -> None:
        try:
            response = await self._client.post(
                self._url,
                json={"chat_id": request.recipient, "text": request.text},
                timeout=HTTP_TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            raise DeliveryError("telegram unreachable") from exc
        if response.status_code >= 400:
            raise DeliveryError(
                f"telegram answered {response.status_code}",
                permanent=response.status_code in (400, 403),
            )


def build_channels(settings: Settings, client: httpx.AsyncClient) -> dict[str, NotificationChannel]:
    """Channels enabled by configuration; a missing channel is simply not available."""
    channels: dict[str, NotificationChannel] = {}
    if settings.sms_gateway_url and settings.sms_gateway_password:
        channels[SMS] = SmsGatewayChannel(
            client,
            settings.sms_gateway_url,
            settings.sms_gateway_user,
            settings.sms_gateway_password.get_secret_value(),
        )
    if settings.vapid_private_key:
        channels[PUSH] = WebPushChannel(
            settings.vapid_private_key.get_secret_value(), settings.vapid_subject
        )
    if settings.telegram_bot_token:
        channels[TELEGRAM] = TelegramChannel(client, settings.telegram_bot_token.get_secret_value())
    return channels
