import { layers, namedFlavor } from "@protomaps/basemaps";
import type { StyleSpecification } from "maplibre-gl";

export type MapLang = "ar" | "fr" | "en";

/** Same-origin PMTiles archive served by the API with Range requests (`make map-data`). */
export const TILES_URL = "/api/tiles/algeria.pmtiles";

const OSM_ATTRIBUTION =
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/**
 * Offline basemap style: vector tiles, glyphs and sprites all come from this origin
 * (fonts and sprites are fetched by `make map-data` into `public/map`), so no external
 * tile or font host is contacted (PRD FR-MAP-001, C-03).
 */
export function basemapStyle(lang: MapLang): StyleSpecification {
  return {
    version: 8,
    glyphs: "/map/fonts/{fontstack}/{range}.pbf",
    sprite: `${window.location.origin}/map/sprites/light`,
    sources: {
      protomaps: {
        type: "vector",
        url: `pmtiles://${window.location.origin}${TILES_URL}`,
        attribution: OSM_ATTRIBUTION,
      },
    },
    layers: layers("protomaps", namedFlavor("light"), { lang }),
  };
}
