"""Password hashing (Argon2id) and JWT access tokens (HS256)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
# Verified against when the username is unknown, so response time does not reveal it.
DUMMY_HASH = _hasher.hash("nadjet-dummy-password")

ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    """The token is malformed, forged or expired."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    role: str
    expires_at: datetime


def encode_token(
    user_id: uuid.UUID, role: str, *, key: str, ttl: timedelta, now: datetime | None = None
) -> str:
    issued = now or datetime.now(UTC)
    payload = {"sub": str(user_id), "role": role, "iat": issued, "exp": issued + ttl}
    return jwt.encode(payload, key, algorithm=ALGORITHM)


def decode_token(token: str, *, key: str) -> TokenClaims:
    try:
        payload = jwt.decode(
            token, key, algorithms=[ALGORITHM], options={"require": ["sub", "role", "exp"]}
        )
        return TokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            role=str(payload["role"]),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError("invalid token") from exc
