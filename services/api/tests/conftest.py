"""Shared fixtures for the API integration tests (real PostGIS and Redis from `make infra`)."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.models import User
from nadjet_api.auth.security import hash_password
from nadjet_api.config import Settings
from nadjet_api.main import create_app

PASSWORD = "integration-pass-1"
INGEST_TOKEN = "test-ingest-token"

MakeUser = Callable[..., Awaitable[User]]


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        env="test",
        ingest_token=INGEST_TOKEN,  # type: ignore[arg-type]
        evidence_dir=tmp_path / "evidence",
        **overrides,  # type: ignore[arg-type]
    )


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = create_app(make_settings(tmp_path))
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def session(app: FastAPI) -> AsyncIterator[AsyncSession]:
    async with app.state.session_factory() as s:
        yield s


@pytest.fixture
def make_user() -> MakeUser:
    async def factory(
        session: AsyncSession, *, role: str = "operator", active: bool = True, **extra: str
    ) -> User:
        user = User(
            username=f"it-{uuid.uuid4().hex[:12]}",
            display_name="IT",
            password_hash=hash_password(PASSWORD),
            role=role,
            active=active,
            **extra,
        )
        session.add(user)
        await session.commit()
        return user

    return factory
