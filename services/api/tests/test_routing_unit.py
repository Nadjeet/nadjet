"""Unit: ranking rules, OSRM client and tile serving (FR-DSP-001, FR-DSP-002, FR-MAP-001)."""

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from nadjet_api.config import Settings
from nadjet_api.geo.seed import load_capabilities, load_facilities, load_units
from nadjet_api.main import create_app
from nadjet_api.routing.ranking import HospitalCandidate, apply_urban_multiplier, rank_hospitals
from nadjet_api.routing.router import Leg, OsrmRouter, Point, RouterUnavailableError

A, B = Point(36.76, 3.47), Point(36.77, 3.48)


def cand(id: str, *, capable: bool, ready: bool, eta: float) -> HospitalCandidate:
    return HospitalCandidate(id=id, capable=capable, ready=ready, eta_s=eta)


def test_capable_hospital_ranks_before_faster_incapable_one() -> None:
    ranked = rank_hospitals(
        [
            cand("eph", capable=False, ready=True, eta=60),
            cand("chu", capable=True, ready=True, eta=900),
        ]
    )
    assert [c.id for c in ranked] == ["chu", "eph"]


def test_divert_ranks_after_ready_even_when_closer() -> None:
    ranked = rank_hospitals(
        [
            cand("near", capable=True, ready=False, eta=60),
            cand("far", capable=True, ready=True, eta=600),
        ]
    )
    assert [c.id for c in ranked] == ["far", "near"]


def test_equal_capability_and_state_sorts_by_eta() -> None:
    ranked = rank_hospitals(
        [
            cand("b", capable=False, ready=True, eta=300),
            cand("a", capable=False, ready=True, eta=100),
        ]
    )
    assert [c.id for c in ranked] == ["a", "b"]


def test_urban_multiplier_scales_free_flow_time() -> None:
    assert apply_urban_multiplier(100.0, 1.3) == pytest.approx(130.0)


def osrm(handler: httpx.MockTransport) -> OsrmRouter:
    return OsrmRouter(httpx.AsyncClient(transport=handler), "http://osrm")


async def test_table_parses_matrix_and_unreachable_cells() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith(
            "/table/v1/driving/3.470000,36.760000;3.480000,36.770000"
        )
        return httpx.Response(
            200,
            json={"code": "Ok", "durations": [[10.0, None]], "distances": [[100.0, None]]},
        )

    legs = await osrm(httpx.MockTransport(handle)).table([A], [B, B])
    assert legs == [[Leg(10.0, 100.0), None]]


async def test_route_returns_geometry_and_none_for_no_route() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if "fail" in str(request.url.params.get("overview")):
            return httpx.Response(200, json={"code": "NoRoute"})
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "duration": 5,
                        "distance": 50,
                        "geometry": {"type": "LineString", "coordinates": [[3.47, 36.76]]},
                    }
                ],
            },
        )

    route = await osrm(httpx.MockTransport(handle)).route(A, B)
    assert route is not None
    assert route.duration_s == 5
    assert route.geometry["type"] == "LineString"


async def test_no_route_code_gives_none() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"code": "NoRoute"}))
    assert await osrm(transport).route(A, B) is None


async def test_unreachable_osrm_raises_router_unavailable() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(RouterUnavailableError):
        await osrm(httpx.MockTransport(handle)).table([A], [B])


async def test_osrm_server_error_raises_router_unavailable() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(RouterUnavailableError):
        await osrm(transport).route(A, B)


def test_tiles_404_until_built_then_serves_ranges(tmp_path: Path) -> None:
    missing = Settings(env="test", map_tiles_path=tmp_path / "none.pmtiles")
    with TestClient(create_app(missing, probes={})) as c:
        assert c.get("/tiles/algeria.pmtiles").status_code == 404

    tiles = tmp_path / "algeria.pmtiles"
    tiles.write_bytes(b"0123456789")
    with TestClient(create_app(Settings(env="test", map_tiles_path=tiles), probes={})) as c:
        response = c.get("/tiles/algeria.pmtiles", headers={"Range": "bytes=2-4"})
    assert response.status_code == 206
    assert response.content == b"234"


def test_seed_loaders_validate_rows(tmp_path: Path) -> None:
    (tmp_path / "f.csv").write_text(
        "id,kind,name,lat,lon,wilaya,contact_sms,simulated\n"
        "h1,hospital,CHU Test,36.7,3.1,Alger,,true\n"
    )
    (tmp_path / "c.csv").write_text("facility_id,capability,ready_state\nh1,trauma,divert\n")
    (tmp_path / "u.csv").write_text(
        "id,facility_id,agency,callsign,lat,lon,phone,simulated\nu1,h1,samu,SAMU-1,36.7,3.1,,true\n"
    )
    [facility] = load_facilities(tmp_path / "f.csv")
    [capability] = load_capabilities(tmp_path / "c.csv")
    [unit] = load_units(tmp_path / "u.csv")
    assert facility.contact_sms is None
    assert facility.simulated is True
    assert capability.ready_state == "divert"
    assert unit.agency.value == "samu"


def test_seed_loader_rejects_bad_kind(tmp_path: Path) -> None:
    (tmp_path / "f.csv").write_text("id,kind,name,lat,lon\nx,airport,X,1,1\n")
    with pytest.raises(ValueError):
        load_facilities(tmp_path / "f.csv")
