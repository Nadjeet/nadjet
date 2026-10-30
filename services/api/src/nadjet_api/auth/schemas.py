"""Request and response models of the auth API."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from nadjet_api.auth.roles import Agency, Role


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: Role
    agency: Agency | None
    facility_id: str | None
    phone: str | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int = Field(description="Token lifetime in seconds")
    user: UserOut
