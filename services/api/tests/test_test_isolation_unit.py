"""Tests never touch the developer's database, Redis or `.env` (root conftest.py, TD-50)."""

from nadjet_api.config import Settings
from nadjet_vision.config import VisionSettings


def test_settings_point_at_the_test_database_and_redis_db_not_the_dev_ones() -> None:
    settings = Settings()
    assert str(settings.database_url).rsplit("/", 1)[1].endswith("_test")
    assert str(settings.redis_url).endswith("/15")


def test_settings_do_not_read_the_developer_env_file() -> None:
    assert Settings.model_config.get("env_file") is None
    assert VisionSettings.model_config.get("env_file") is None
