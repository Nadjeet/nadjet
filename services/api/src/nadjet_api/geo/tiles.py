"""Serve the self-hosted Algeria PMTiles archive with HTTP Range support (FR-MAP-001).

Never proxies a public tile server (docs/11 §2). Build the file with ``make map-data``.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(tags=["map"])


@router.get("/tiles/algeria.pmtiles", response_class=FileResponse)
async def algeria_tiles(request: Request) -> FileResponse:
    """The PMTiles archive; clients read it with Range requests."""
    path = request.app.state.settings.map_tiles_path
    if not path.is_file():
        raise HTTPException(404, "Basemap not built: run `make map-data`")
    return FileResponse(path, media_type="application/octet-stream")
