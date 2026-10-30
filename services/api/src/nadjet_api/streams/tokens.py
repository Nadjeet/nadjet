"""Short-lived stream tokens (HS256, audience ``nadjet-stream``).

The audience keeps them apart from access tokens: neither type decodes as the other.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt

from nadjet_api.auth.security import ALGORITHM, InvalidTokenError

AUDIENCE = "nadjet-stream"
StreamAction = Literal["read", "publish"]


@dataclass(frozen=True)
class StreamClaims:
    subject: str
    action: StreamAction
    path: str | None  # None = any path


def encode_stream_token(
    subject: str,
    action: StreamAction,
    *,
    key: str,
    ttl: timedelta,
    path: str | None = None,
    now: datetime | None = None,
) -> str:
    """Mint a token. ``path`` limits it to one MediaMTX path (try-it sessions, #18)."""
    issued = now or datetime.now(UTC)
    payload = {
        "sub": subject,
        "aud": AUDIENCE,
        "act": action,
        "iat": issued,
        "exp": issued + ttl,
        "jti": uuid.uuid4().hex,
    }
    if path is not None:
        payload["path"] = path
    return jwt.encode(payload, key, algorithm=ALGORITHM)


def decode_stream_token(token: str, *, key: str) -> StreamClaims:
    try:
        p = jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            options={"require": ["sub", "act", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("invalid stream token") from exc
    if p["act"] not in ("read", "publish"):
        raise InvalidTokenError("invalid stream token action")
    return StreamClaims(subject=str(p["sub"]), action=p["act"], path=p.get("path"))
