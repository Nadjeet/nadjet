"""Keep every test run away from the developer's `.env`, database and Redis.

Integration tests used the dev database (`nadjet`) and Redis db 0, so `make test` filled the
operator console with test incidents, users and cameras, and dispatch alerted hundreds of test
responders. Tests now use their own database (`<dev name>_test`, created and migrated here on
first use) and Redis db 15, and never read `.env` (TD-50).
"""

import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from nadjet_api.config import Settings
from nadjet_vision.config import VisionSettings

ROOT = Path(__file__).resolve().parent
DEV_DATABASE_URL = os.environ.get(
    "NADJET_DATABASE_URL", "postgresql+asyncpg://nadjet:nadjet@localhost:55432/nadjet"
)
TEST_REDIS_DB = 15

# Before any settings object exists: tests see the code defaults plus what they pass explicitly.
for settings_class in (Settings, VisionSettings):
    settings_class.model_config["env_file"] = None

_dev_url = make_url(DEV_DATABASE_URL)
if not (_dev_url.database or "").endswith("_test"):
    os.environ["NADJET_DATABASE_URL"] = _dev_url.set(
        database=f"{_dev_url.database}_test"
    ).render_as_string(hide_password=False)
_redis = os.environ.get("NADJET_REDIS_URL", "redis://localhost:56379/0").rsplit("/", 1)[0]
os.environ["NADJET_REDIS_URL"] = f"{_redis}/{TEST_REDIS_DB}"


async def _create_database(maintenance_url: str, name: str) -> None:
    import asyncpg

    url = make_url(maintenance_url).set(drivername="postgresql")
    conn = await asyncpg.connect(url.render_as_string(hide_password=False))
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


def _prepare_test_database() -> None:
    """Create the test database if needed and migrate it to head (fails when infra is down)."""
    from alembic import command
    from alembic.config import Config

    test_name = make_url(os.environ["NADJET_DATABASE_URL"]).database or ""
    asyncio.run(_create_database(DEV_DATABASE_URL, test_name))
    # No ini file: its logging config would disable the loggers that tests check with caplog.
    config = Config()
    config.set_main_option("script_location", str(ROOT / "services/api/src/nadjet_api/migrations"))
    command.upgrade(config, "head")


@pytest.hookimpl(trylast=True)  # after `-m` deselection: unit-only runs need no infrastructure
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if any(item.get_closest_marker("integration") for item in items):
        _prepare_test_database()
