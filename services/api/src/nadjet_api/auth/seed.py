"""Seed one dev/demo user per role from a YAML file (idempotent)."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, SecretStr, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Agency, Role, validate_role_binding
from nadjet_api.auth.security import hash_password


class SeedUser(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str
    password: SecretStr = Field(min_length=8)
    role: Role
    agency: Agency | None = None
    facility_id: str | None = None
    phone: str | None = None

    @model_validator(mode="after")
    def _binding(self) -> "SeedUser":
        validate_role_binding(self.role, self.agency, self.facility_id)
        return self


class SeedFile(BaseModel):
    users: list[SeedUser]


def load_seed_file(path: Path) -> list[SeedUser]:
    return SeedFile.model_validate(yaml.safe_load(path.read_text())).users


async def seed_users(session: AsyncSession, users: list[SeedUser]) -> tuple[int, int]:
    """Create missing users; existing usernames are left untouched. Returns (created, skipped)."""
    created = skipped = 0
    for seed in users:
        if await session.scalar(select(User.id).where(User.username == seed.username)):
            skipped += 1
            continue
        session.add(
            User(
                username=seed.username,
                display_name=seed.display_name,
                password_hash=hash_password(seed.password.get_secret_value()),
                role=seed.role.value,
                agency=seed.agency.value if seed.agency else None,
                facility_id=seed.facility_id,
                phone=seed.phone,
            )
        )
        created += 1
    await session.commit()
    return created, skipped
