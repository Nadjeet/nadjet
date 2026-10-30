#!/usr/bin/env python3
"""Crop an OSM PBF to a bounding box (used once to build the committed routing test extract).

    uv run --with osmium python scripts/osm/crop_extract.py IN.osm.pbf OUT.osm.pbf W S E N

Keeps ways with at least one node inside the box, plus all their nodes (complete ways).
Relations (turn restrictions) are dropped: fine for a test graph, see services/api/tests/data.
"""

import sys

import osmium


def main(src: str, dst: str, west: float, south: float, east: float, north: float) -> None:
    kept_ways: set[int] = set()
    needed_nodes: set[int] = set()
    # Pass 1: find ways touching the box and the nodes they need.
    for obj in osmium.FileProcessor(src, osmium.osm.NODE | osmium.osm.WAY).with_locations():
        if (
            obj.is_way()
            and "highway" in obj.tags
            and any(
                n.location.valid() and west <= n.lon <= east and south <= n.lat <= north
                for n in obj.nodes
            )
        ):
            kept_ways.add(obj.id)
            needed_nodes.update(n.ref for n in obj.nodes)
    # Pass 2: write the needed nodes then the kept ways (nodes precede ways in the input).
    with osmium.SimpleWriter(dst) as writer:
        for obj in osmium.FileProcessor(src, osmium.osm.NODE | osmium.osm.WAY):
            if obj.is_node() and obj.id in needed_nodes:
                writer.add_node(obj)
            elif obj.is_way() and obj.id in kept_ways:
                writer.add_way(obj)
    print(f"kept {len(kept_ways)} ways, {len(needed_nodes)} nodes", file=sys.stderr)


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], *(float(x) for x in a[3:7]))
