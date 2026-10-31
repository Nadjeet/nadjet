"""Unit tests: hashing, tokens, role/scope table, settings, require_roles (FR-SEC-001/002)."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nadjet_api.audit.service import GENESIS_HASH, canonical_json, chain_hash
from nadjet_api.auth.deps import current_user, require_roles
from nadjet_api.auth.roles import Agency, Role, Scope, scope_for
from nadjet_api.auth.security import (
    InvalidTokenError,
    decode_token,
    encode_token,
    hash_password,
    verify_password,
)
from nadjet_api.config import DEV_JWT_SECRET, DEV_SIGNING_SEED, Settings
from nadjet_api.main import create_app

KEY = "k" * 40


def test_password_hash_verifies_and_rejects_wrong_password() -> None:
    hashed = hash_password("s3cret-pass")
    assert hashed.startswith("$argon2id$")
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("other", hashed)
    assert not verify_password("s3cret-pass", "not-a-hash")


def test_token_round_trip() -> None:
    uid = uuid.uuid4()
    token = encode_token(uid, "operator", key=KEY, ttl=timedelta(minutes=5))
    claims = decode_token(token, key=KEY)
    assert (claims.user_id, claims.role) == (uid, "operator")


def test_expired_token_rejected() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    token = encode_token(uuid.uuid4(), "admin", key=KEY, ttl=timedelta(minutes=1), now=past)
    with pytest.raises(InvalidTokenError):
        decode_token(token, key=KEY)


def test_forged_or_garbage_token_rejected() -> None:
    token = encode_token(uuid.uuid4(), "admin", key="x" * 40, ttl=timedelta(minutes=1))
    with pytest.raises(InvalidTokenError):
        decode_token(token, key=KEY)
    with pytest.raises(InvalidTokenError):
        decode_token("garbage", key=KEY)


def u(role: str, agency: str | None = None, facility: str | None = None) -> Any:
    return SimpleNamespace(role=role, agency=agency, facility_id=facility)


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        (u("operator"), Scope(unrestricted=True)),
        (u("supervisor"), Scope(unrestricted=True)),
        (u("auditor"), Scope(unrestricted=True)),
        (u("admin"), Scope(unrestricted=True)),
        (u("responder", "samu"), Scope(agency=Agency.SAMU)),
        (u("responder", "police"), Scope(agency=Agency.POLICE)),
        (u("hospital", None, "h-1"), Scope(facility_id="h-1")),
    ],
)
def test_scope_for_each_role(user: Any, expected: Scope) -> None:
    assert scope_for(user) == expected


@pytest.mark.parametrize(
    "user",
    [u("responder"), u("hospital"), u("operator", "samu"), u("admin", None, "h"), u("bogus")],
)
def test_scope_for_rejects_invalid_binding(user: Any) -> None:
    with pytest.raises(ValueError):
        scope_for(user)


def test_require_roles_returns_403_for_wrong_role_and_200_for_allowed() -> None:
    app = FastAPI()
    current = {"user": u("responder", "samu")}
    app.dependency_overrides[current_user] = lambda: current["user"]

    @app.get("/ops")
    async def ops(user: Any = Depends(require_roles(Role.OPERATOR, Role.SUPERVISOR))) -> dict:  # noqa: B008
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/ops").status_code == 403
        current["user"] = u("supervisor")
        assert client.get("/ops").status_code == 200


def test_production_requires_strong_jwt_secret() -> None:
    for secret in (None, "short", DEV_JWT_SECRET):
        with pytest.raises(ValidationError):
            Settings(env="production", jwt_secret=secret)  # type: ignore[arg-type]
    for seed in (None, "abc", DEV_SIGNING_SEED):
        with pytest.raises(ValidationError):
            Settings(env="production", jwt_secret="p" * 40, signing_key=seed)  # type: ignore[arg-type]
    ok = Settings(env="production", jwt_secret="p" * 40, signing_key="ab" * 32)  # type: ignore[arg-type]
    assert ok.jwt_key == "p" * 40
    assert Settings(env="development").jwt_key == DEV_JWT_SECRET


def test_audit_hash_is_deterministic_and_chained() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    fields: dict[str, Any] = {
        "actor_id": None,
        "action": "x",
        "target_type": None,
        "target_id": None,
        "ip": None,
        "at": at,
        "details": {"b": 1, "a": 2},
    }
    first = canonical_json(**fields)
    assert first == canonical_json(**{**fields, "details": {"a": 2, "b": 1}})
    h1 = chain_hash(GENESIS_HASH, first)
    assert len(h1) == 64
    assert chain_hash(h1, first) != h1


def test_internal_endpoints_are_disabled_without_an_ingest_token() -> None:
    # _env_file=None: a developer's or CI's .env (copied from .env.example) sets a token.
    settings = Settings(env="test", _env_file=None)  # type: ignore[call-arg]
    with TestClient(create_app(settings, probes={})) as client:
        response = client.post("/internal/candidates", json={}, headers={"Idempotency-Key": "k"})
    assert response.status_code == 503
