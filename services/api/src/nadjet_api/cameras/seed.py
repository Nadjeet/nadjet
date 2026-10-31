"""Sync the ``cameras`` table from the catalogue (``nadjet-api seed-cameras``)."""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.cameras.models import Camera
from nadjet_shared.catalogue import Catalogue


async def seed_cameras(session: AsyncSession, catalogue: Catalogue) -> int:
    """Upsert every catalogue camera; ``status`` is kept. Returns the number written."""
    # ponytail: never deletes; incidents will reference cameras, so retire them by hand
    for cam in catalogue.cameras:
        values = {
            "id": cam.id,
            "name": cam.name,
            "stream_path": cam.id,
            "lat": cam.geo.lat,
            "lon": cam.geo.lon,
            "road": cam.road,
            "pk_km": cam.pk_km,
            "heading_deg": cam.heading_deg,
            "wilaya": cam.wilaya,
            "zones": cam.zones.model_dump(mode="json") if cam.zones else None,
            "simulated": True,
        }
        update = {k: v for k, v in values.items() if k != "id"} | {"updated_at": func.now()}
        stmt = insert(Camera).values(**values)
        await session.execute(stmt.on_conflict_do_update(index_elements=[Camera.id], set_=update))
    await session.commit()
    return len(catalogue.cameras)
