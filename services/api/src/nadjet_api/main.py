"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis

from nadjet_api import __version__
from nadjet_api.auth.routes import router as auth_router
from nadjet_api.config import Settings, get_settings
from nadjet_api.db import create_engine, create_session_factory
from nadjet_api.health import Probe, database_probe, redis_probe, run_probes


class HealthResponse(BaseModel):
    status: str
    version: str


class DependencyStatus(BaseModel):
    ok: bool
    detail: str


class ReadinessResponse(BaseModel):
    status: str
    dependencies: dict[str, DependencyStatus]


def create_app(settings: Settings | None = None, probes: dict[str, Probe] | None = None) -> FastAPI:
    """Build the app. Tests pass ``probes`` to avoid real infrastructure."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if probes is not None:
            app.state.probes = probes
            yield
            return
        engine = create_engine(settings)
        redis: Redis = Redis.from_url(str(settings.redis_url))
        app.state.session_factory = create_session_factory(engine)
        app.state.redis = redis
        app.state.probes = {"database": database_probe(engine), "redis": redis_probe(redis)}
        try:
            yield
        finally:
            await redis.aclose()
            await engine.dispose()

    app = FastAPI(title="Nadjet API", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(auth_router)
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
