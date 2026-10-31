"""Integration: GET /evaluation/latest with real auth (supervisor and admin only)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.main import create_app
from nadjet_shared.evaluation import AblationRow, EvaluationResults

from .conftest import MakeUser, make_settings
from .test_integration_incidents import login

pytestmark = pytest.mark.integration


def results_file(directory: Path, sha: str, day: int) -> EvaluationResults:
    results = EvaluationResults(
        generated_at=datetime(2026, 10, day, tzinfo=UTC), git_sha=sha, dirty=False, seed=0,
        bootstrap_samples=10, window_before_s=2, window_after_s=10, models={"detector": "d"},
        clips=[], camera_hours=0.25, meets_camera_hour_target=False,
        ablation=[AblationRow(name="boxes", description="d", not_run_reason="TQ-06 open")],
        limitations=["only 0.25 camera-hours"],
    )  # fmt: skip
    (directory / f"2026-10-{day}-{sha}.json").write_text(results.model_dump_json())
    return results


@pytest.fixture
async def empty_app(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, Path]]:
    directory = tmp_path / "results"
    directory.mkdir()
    app = create_app(make_settings(tmp_path, evaluation_dir=directory))
    async with app.router.lifespan_context(app):
        yield app, directory


async def test_supervisor_reads_the_latest_results(
    empty_app: tuple[FastAPI, Path], make_user: MakeUser
) -> None:
    app, directory = empty_app
    results_file(directory, "old1234", 20)
    newest = results_file(directory, "new5678", 30)
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client,
        app.state.session_factory() as session,
    ):
        supervisor = await login(client, await make_user(session, role="supervisor"))
        response = await client.get("/evaluation/latest", headers=supervisor)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["git_sha"] == "new5678"
    assert EvaluationResults.model_validate(body) == newest
    assert body["ablation"][0]["not_run_reason"] == "TQ-06 open"  # what was not run is served


async def test_admin_can_read_but_operator_and_anonymous_cannot(
    empty_app: tuple[FastAPI, Path], make_user: MakeUser
) -> None:
    app, directory = empty_app
    results_file(directory, "abc1234", 30)
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client,
        app.state.session_factory() as session,
    ):
        admin = await login(client, await make_user(session, role="admin"))
        operator = await login(client, await make_user(session, role="operator"))
        assert (await client.get("/evaluation/latest", headers=admin)).status_code == 200
        assert (await client.get("/evaluation/latest", headers=operator)).status_code == 403
        assert (await client.get("/evaluation/latest")).status_code == 401


async def test_no_results_yet_is_a_404_not_an_empty_success(
    empty_app: tuple[FastAPI, Path], make_user: MakeUser
) -> None:
    app, _ = empty_app
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client,
        app.state.session_factory() as session,
    ):
        supervisor = await login(client, await make_user(session, role="supervisor"))
        response = await client.get("/evaluation/latest", headers=supervisor)
    assert response.status_code == 404
    assert "No evaluation results" in response.text


async def test_the_endpoint_is_in_the_openapi_contract(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert "/evaluation/latest" in schema["paths"]
    assert "EvaluationResults" in schema["components"]["schemas"]
