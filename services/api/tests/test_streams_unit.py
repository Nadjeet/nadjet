"""Unit: MediaMTX auth decisions and stream tokens (FR-SEC-007)."""

from datetime import timedelta

import pytest

from nadjet_api.auth.security import InvalidTokenError, encode_token
from nadjet_api.config import Settings
from nadjet_api.streams.auth import MediaMtxAuthRequest, authorize
from nadjet_api.streams.tokens import decode_stream_token, encode_stream_token

INGEST = "unit-ingest-token"


def settings(**kw: object) -> Settings:
    return Settings(env="test", ingest_token=INGEST, **kw)  # type: ignore[arg-type]


def req(**kw: object) -> MediaMtxAuthRequest:
    return MediaMtxAuthRequest(**{"action": "read", "path": "cam-a1", **kw})  # type: ignore[arg-type]


def mint(s: Settings, action: str = "read", **kw: object) -> str:
    return encode_stream_token("u1", action, key=s.jwt_key, ttl=timedelta(minutes=5), **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("action", ["publish", "read", "api", "metrics"])
def test_service_user_allowed(action: str) -> None:
    assert authorize(req(action=action, user="nadjet-worker", password=INGEST), settings())


def test_service_user_wrong_password_rejected() -> None:
    assert not authorize(req(user="nadjet-worker", password="nope"), settings())


def test_anonymous_read_and_publish_rejected() -> None:
    s = settings()
    assert not authorize(req(), s)
    assert not authorize(req(action="publish"), s)


def test_service_user_rejected_when_ingest_token_unset() -> None:
    s = Settings(env="test")
    assert not authorize(req(user="nadjet-worker", password=""), s)


def test_read_token_via_bearer_password_and_query() -> None:
    s = settings()
    t = mint(s)
    assert authorize(req(token=t), s)
    assert authorize(req(password=t), s)
    assert authorize(req(query=f"token={t}"), s)


def test_read_token_cannot_publish_or_use_api() -> None:
    s = settings()
    t = mint(s)
    assert not authorize(req(action="publish", token=t), s)
    assert not authorize(req(action="api", token=t), s)


def test_publish_token_limited_to_its_path() -> None:
    s = settings()
    t = mint(s, "publish", path="try-abc")
    assert authorize(req(action="publish", path="try-abc", token=t), s)
    assert not authorize(req(action="publish", path="cam-a1", token=t), s)
    assert not authorize(req(action="read", path="try-abc", token=t), s)


def test_expired_and_forged_tokens_rejected() -> None:
    s = settings()
    old = encode_stream_token("u", "read", key=s.jwt_key, ttl=timedelta(seconds=-5))
    forged = encode_stream_token("u", "read", key="x" * 40, ttl=timedelta(minutes=5))
    assert not authorize(req(token=old), s)
    assert not authorize(req(token=forged), s)


def test_access_token_is_not_a_stream_token_and_vice_versa() -> None:
    s = settings()
    import uuid

    access = encode_token(uuid.uuid4(), "operator", key=s.jwt_key, ttl=timedelta(minutes=5))
    assert not authorize(req(token=access), s)
    with pytest.raises(InvalidTokenError):
        decode_stream_token(access, key=s.jwt_key)
