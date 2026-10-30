"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis

from nadjet_api import __version__
from nadjet_api.auth.routes import router as auth_router
from nadjet_api.cameras.internal import router as camera_internal_router
from nadjet_api.cameras.routes import router as cameras_router
from nadjet_api.cameras.routes import system_router as system_cameras_router
from nadjet_api.config import Settings, get_settings
from nadjet_api.db import create_engine, create_session_factory
from nadjet_api.dispatch.routes import router as dispatch_router
from nadjet_api.evaluation.routes import router as evaluation_router
from nadjet_api.geo.resources import router as map_resources_router
from nadjet_api.geo.tiles import router as tiles_router
from nadjet_api.health import Probe, database_probe, redis_probe, run_probes
from nadjet_api.incidents import internal
from nadjet_api.incidents import routes as incident_routes
from nadjet_api.incidents.signing import ChainSigner
from nadjet_api.incidents.store import LocalEvidenceStore
from nadjet_api.notifications.channels import build_channels
from nadjet_api.notifications.routes import router as notifications_router
from nadjet_api.routing.router import OsrmRouter, Router
from nadjet_api.routing.routes import router as routing_router
from nadjet_api.system.routes import router as system_ai_router
from nadjet_api.tryit import service as try_service
from nadjet_api.tryit.internal import router as try_internal_router
from nadjet_api.tryit.routes import purge_loop
from nadjet_api.tryit.routes import router as try_router


class HealthResponse(BaseModel):
    status: str
    version: str


class DependencyStatus(BaseModel):
    ok: bool
    detail: str


class ReadinessResponse(BaseModel):
    status: str
    dependencies: dict[str, DependencyStatus]


def create_app(
    settings: Settings | None = None,
    probes: dict[str, Probe] | None = None,
    road_router: Router | None = None,
) -> FastAPI:
    """Build the app. Tests pass ``probes`` / ``road_router`` to avoid real infrastructure."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if probes is not None:
            app.state.probes = probes
            app.state.router = road_router
            yield
            return
        http = httpx.AsyncClient(timeout=settings.routing_timeout_s)
        app.state.router = road_router or OsrmRouter(http, settings.osrm_url)
        engine = create_engine(settings)
        redis: Redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        app.state.session_factory = create_session_factory(engine)
        app.state.redis = redis
        app.state.probes = {"database": database_probe(engine), "redis": redis_probe(redis)}
        app.state.channels = build_channels(settings, http)
        stop_purge = asyncio.Event()
        purger = asyncio.create_task(
            purge_loop(app.state, settings.try_purge_interval_s, stop_purge)
        )
        # Notification jobs are enqueued after each dispatch (the worker runs them, TD-08).
        app.state.arq = await create_pool(RedisSettings.from_dsn(str(settings.redis_url)))
        try:
            yield
        finally:
            stop_purge.set()
            await purger
            await app.state.arq.aclose()
            await http.aclose()
            await redis.aclose()
            await engine.dispose()

    app = FastAPI(title="Nadjet API", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.signer = ChainSigner(settings.signing_seed)
    app.state.store = LocalEvidenceStore(settings.evidence_dir)
    app.state.try_store = try_service.SandboxStore(settings.try_dir)
    app.include_router(auth_router)
    app.include_router(cameras_router)
    app.include_router(system_cameras_router)
    app.include_router(system_ai_router)
    app.include_router(camera_internal_router)
    # Before the incident routes: `/incidents/{id}.cap.xml` must win over `/incidents/{id}`.
    app.include_router(notifications_router)
    app.include_router(incident_routes.router)
    app.include_router(dispatch_router)
    app.include_router(internal.router)
    app.include_router(routing_router)
    app.include_router(evaluation_router)
    app.include_router(map_resources_router)
    app.include_router(try_router)
    app.include_router(try_internal_router)
    app.include_router(tiles_router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def health() -> HealthResponse:
        """Liveness: the process is running."""
        return HealthResponse(status="ok", version=__version__)

    @app.get(
        "/ready",
        tags=["system"],
        responses={503: {"model": ReadinessResponse, "description": "A dependency is down"}},
    )
    async def ready(request: Request) -> ReadinessResponse:
        """Readiness: every dependency answers."""
        results = await run_probes(request.app.state.probes, settings.readiness_timeout_s)
        body = ReadinessResponse(
            status="ok" if all(r.ok for r in results) else "degraded",
            dependencies={r.name: DependencyStatus(ok=r.ok, detail=r.detail) for r in results},
        )
        if body.status != "ok":
            return JSONResponse(status_code=503, content=body.model_dump())  # type: ignore[return-value]
        return body

    return app
