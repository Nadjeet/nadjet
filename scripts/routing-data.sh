#!/usr/bin/env bash
# Prepare OSRM routing data (MLD) from the Geofabrik Algeria extract into the `osrmdata` volume.
# Download ~290 MB; osrm-extract peaks at ~1.3 GB RAM, needs ~3 GB disk, takes a few minutes.
set -euo pipefail
cd "$(dirname "$0")/.."

PBF="data/map/algeria-latest.osm.pbf"
mkdir -p data/map
if [ ! -f "$PBF" ]; then
  curl -fL --progress-bar -o "$PBF.part" "https://download.geofabrik.de/africa/algeria-latest.osm.pbf"
  mv "$PBF.part" "$PBF"
fi

prepare() {
  docker compose -f deploy/local/compose.yml --profile routing-prepare run --rm --no-deps \
    --entrypoint "$1" osrm-prepare "${@:2}"
}
prepare osrm-extract -p /opt/car.lua /data/algeria-latest.osm.pbf
prepare osrm-partition /data/algeria-latest.osrm
prepare osrm-customize /data/algeria-latest.osrm
echo "OSRM data ready. Start it with: make routing-up"
