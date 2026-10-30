"""``nadjet-api seed-demo``: everything the demo needs except incidents (PRD FR-VIS-020).

One idempotent call composes the existing seeders: users per role (with their demo phones),
simulated units and facilities, and the camera registry. It never writes incidents,
detections or notifications: those must come from the live pipeline.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role
from nadjet_api.auth.seed import SeedUser, seed_users
from nadjet_api.cameras.seed import seed_cameras
from nadjet_api.geo.seed import CapabilitySeed, FacilitySeed, UnitSeed, seed_geo
from nadjet_api.incidents.models import Incident
from nadjet_shared.catalogue import Catalogue


@dataclass(frozen=True)
class DemoSeedReport:
    users_created: int
    users_existing: int
    cameras: int
    facilities: int
    capabilities: int
    units: int
    incidents: int
    responders_without_phone: list[str]

    def lines(self) -> list[str]:
        out = [
            f"seed-demo: users {self.users_created} created, {self.users_existing} existing",
            f"seed-demo: {self.cameras} camera(s), {self.facilities} facilities "
            f"({self.capabilities} capabilities), {self.units} units",
            f"seed-demo: {self.incidents} incident(s) in the database (never created here)",
        ]
        if self.responders_without_phone:
            names = ", ".join(self.responders_without_phone)
            out.append(f"seed-demo: WARNING no phone for responder(s): {names} (no SMS demo)")
        return out


async def seed_demo(
    session: AsyncSession,
    *,
    users: list[SeedUser],
    catalogue: Catalogue,
    facilities: list[FacilitySeed],
    capabilities: list[CapabilitySeed],
    units: list[UnitSeed],
) -> DemoSeedReport:
    created, existing = await seed_users(session, users)
    cameras = await seed_cameras(session, catalogue)
    f_count, c_count, u_count = await seed_geo(session, facilities, capabilities, units)
    incidents = await session.scalar(select(func.count()).select_from(Incident)) or 0
    phones = {
        row.username: row.phone
        for row in await session.scalars(select(User).where(User.role == Role.RESPONDER.value))
    }
    return DemoSeedReport(
        users_created=created,
        users_existing=existing,
        cameras=cameras,
        facilities=f_count,
        capabilities=c_count,
        units=u_count,
        incidents=incidents,
        responders_without_phone=sorted(name for name, phone in phones.items() if not phone),
    )
