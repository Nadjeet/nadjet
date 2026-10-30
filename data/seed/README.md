# Seed data

| File | Content | Source |
|---|---|---|
| `facilities.csv` | Hospitals, Civil Protection, Gendarmerie and police locations for Alger, Boumerdès, Bouira, Tizi Ouzou | One-off Overpass export: `python3 scripts/osm/export_facilities.py` |
| `capabilities.csv` | Simulated capabilities (`trauma`, `emergency`) and Ready/Divert state per facility | Hand-written, **simulated** (PRD A-02) |
| `units.csv` | 10 demo units around Boumerdès, placed at real station locations | Hand-written, **simulated** |
| `users.example.yaml` | Dev users, one per role | See `docs/ONBOARDING.md` |

Import with `make seed-geo` (idempotent). Contacts and capabilities are never real: every row
carries `simulated = true` and the UI must label it as simulated.

## Attribution

`facilities.csv` contains data © OpenStreetMap contributors, available under the
[Open Database Licence (ODbL)](https://www.openstreetmap.org/copyright). Re-exporting is a
developer action; the API never calls Overpass at runtime.
