"""arq worker: delivers notifications and re-checks them with back-off (FR-NTF-004, TD-08)."""

import logging
import uuid
from datetime import timedelta
from typing import Any, ClassVar

import httpx
from arq.connections import ArqRedis, RedisSettings

from nadjet_api.config import Settings, get_settings
from nadjet_api.db import create_engine, create_session_factory
from nadjet_api.incidents.events import publish
from nadjet_api.incidents.signing import ChainSigner
from nadjet_api.notifications import service
from nadjet_api.notifications.channels import build_channels
from nadjet_api.notifications.models import Notification

JOB = "deliver_notification"
log = logging.getLogger(__name__)


async def enqueue(pool: ArqRedis, notification: Notification, *, delay_s: int = 0) -> None:
    """Schedule a delivery run, now or after ``delay_s``."""
    await pool.enqueue_job(
        JOB,
        str(notification.id),
        _defer_by=timedelta(seconds=delay_s),
    )


async def enqueue_all(pool: ArqRedis, notifications: list[Notification]) -> None:
    for notification in notifications:
        await enqueue(pool, notification)


async def deliver_notification(ctx: dict[str, Any], notification_id: str) -> None:
    settings: Settings = ctx["settings"]
    async with ctx["session_factory"]() as session:
        outcome = await service.process(
            session,
            ctx["channels"],
            ctx["signer"],
            uuid.UUID(notification_id),
            base_s=settings.notify_retry_base_s,
            max_retries=settings.notify_max_retries,
        )
        await session.commit()
    for change in outcome.changes:
        await publish(ctx["redis"], change)
    if outcome.retry_in_s is not None:
        await ctx["redis"].enqueue_job(
            JOB,
            notification_id,
            _defer_by=timedelta(seconds=outcome.retry_in_s),
        )


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    client = httpx.AsyncClient()
    ctx.update(
        settings=settings,
        engine=engine,
        http=client,
        session_factory=create_session_factory(engine),
        channels=build_channels(settings, client),
        signer=ChainSigner(settings.signing_seed),
    )
    log.info("notification worker ready, channels: %s", sorted(ctx["channels"]))


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["http"].aclose()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [deliver_notification]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
    max_tries = 1  # retries are ours (back-off + operator alert), not arq's
