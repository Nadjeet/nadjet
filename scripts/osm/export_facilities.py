#!/usr/bin/env python3
"""One-off export of hospitals, fire stations, gendarmerie and police from OpenStreetMap.

Run by a developer, never at runtime (Overpass usage policy, docs/11 §2). Writes
data/seed/facilities.csv (ODbL, see data/seed/README.md). Stdlib only.

    python3 scripts/osm/export_facilities.py
"""

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "nadjet-seed-export/1.0 (https://github.com/Nadjeet/nadjet; one-off developer export)"
WILAYAS = {"DZ-16": "Alger", "DZ-35": "Boumerdès", "DZ-10": "Bouira", "DZ-15": "Tizi Ouzou"}
OUT = Path(__file__).resolve().parents[2] / "data" / "seed" / "facilities.csv"


def query(iso: str) -> str:
    return f"""[out:json][timeout:90];
area["ISO3166-2"="{iso}"]->.a;
nwr["amenity"~"^(hospital|fire_station|police)$"](area.a);
out center tags;"""


def kind_of(tags: dict[str, str]) -> str:
    amenity = tags["amenity"]
    if amenity == "hospital":
        return "hospital"
    if amenity == "fire_station":
        return "civil_protection"
    text = f"{tags.get('name', '')} {tags.get('operator', '')}".lower()
    return "gendarmerie" if "gendarm" in text or "درك" in text else "police"


def fetch(iso: str) -> list[dict[str, str]]:
    request = urllib.request.Request(
        ENDPOINT,
        data=urllib.parse.urlencode({"data": query(iso)}).encode(),
        headers={"User-Agent": USER_AGENT},
    )
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
                elements = json.load(response)["elements"]
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503, 504) or attempt == 4:
                raise
            print(f"{iso}: HTTP {exc.code}, retrying in {30 * attempt}s", file=sys.stderr)
            time.sleep(30 * attempt)
    rows = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:fr") or tags.get("name:ar")
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not (name and lat and lon):
            continue
        rows.append(
            {
                "id": f"osm-{el['type']}-{el['id']}",
                "kind": kind_of(tags),
                "name": name,
                "lat": f"{lat:.6f}",
                "lon": f"{lon:.6f}",
                "wilaya": WILAYAS[iso],
                "contact_sms": "",
                "simulated": "true",  # contacts are never real (PRD A-02)
            }
        )
    return rows


def main() -> int:
    rows: list[dict[str, str]] = []
    for iso in WILAYAS:
        rows += fetch(iso)
        time.sleep(10)  # be polite to the public Overpass instance
    rows.sort(key=lambda r: (r["wilaya"], r["kind"], r["id"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} facilities to {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
