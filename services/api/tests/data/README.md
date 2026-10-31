# Routing test extract

`boumerdes.osm.pbf` is a 2.6 MB crop of the Geofabrik Algeria extract (bbox
`3.15,36.55,3.95,36.95`: Boudouaou, Boumerdès, Thenia, Bordj Menaïel, Issers). CI builds an OSRM
graph from it in a temporary directory (`.github/workflows/ci.yml`) so the routing integration tests run against real
roads without the 290 MB national file.

Data © OpenStreetMap contributors, available under the
[ODbL](https://www.openstreetmap.org/copyright). Highways only, no relations (turn
restrictions), which is fine for ranking tests.

Rebuild it after downloading the national extract with `make routing-data`:

```bash
uv run --no-project --with osmium python scripts/osm/crop_extract.py \
  data/map/algeria-latest.osm.pbf services/api/tests/data/boumerdes.osm.pbf 3.15 36.55 3.95 36.95
```
