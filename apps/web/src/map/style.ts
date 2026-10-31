import { layers, namedFlavor, type Flavor } from "@protomaps/basemaps";
import type { StyleSpecification } from "maplibre-gl";

export type MapLang = "ar" | "fr" | "en";

/** Same-origin PMTiles archive served by the API with Range requests (`make map-data`). */
export const TILES_URL = "/api/tiles/algeria.pmtiles";

const OSM_ATTRIBUTION =
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/**
 * Figma map look (dashboard "Live Routes", app "Incidents Map"): light grey land, white roads
 * with a soft grey casing, pale green parks and a light blue sea, so the blue routes and the red
 * incident pins carry the colour. Built on the protomaps "light" flavor.
 */
const LIGHT = namedFlavor("light");

export const NADJET_FLAVOR: Flavor = {
  ...LIGHT,
  background: "#eef1f3",
  earth: "#f2f4f5",
  park_a: "#d9efdf",
  park_b: "#cfe9d6",
  wood_a: "#dcefe0",
  wood_b: "#d2ead8",
  scrub_a: "#e3f1e5",
  scrub_b: "#dcedde",
  landcover: LIGHT.landcover
    ? { ...LIGHT.landcover, grassland: "#e2f1e4", forest: "#d6ecdb", urban_area: "#eceff2" }
    : undefined,
  water: "#bfe3fb",
  buildings: "#e4e8ec",
  hospital: "#eaf3ff",
  school: "#eef0f5",
  industrial: "#eceff2",
  sand: "#f1efe6",
  beach: "#f3efe2",
  aerodrome: "#e9edf1",
  pedestrian: "#f5f7f8",
  other: "#ffffff",
  minor_a: "#ffffff",
  minor_b: "#ffffff",
  minor_service: "#ffffff",
  link: "#ffffff",
  major: "#ffffff",
  highway: "#ffffff",
  minor_casing: "#dfe4e8",
  minor_service_casing: "#dfe4e8",
  link_casing: "#d5dbe1",
  major_casing_early: "#d5dbe1",
  major_casing_late: "#d5dbe1",
  highway_casing_early: "#cbd3db",
  highway_casing_late: "#cbd3db",
  railway: "#c9d0d7",
  boundaries: "#9aa8b8",
  roads_label_minor: "#64748b",
  roads_label_major: "#475569",
  city_label: "#334155",
  subplace_label: "#64748b",
  state_label: "#94a3b8",
  country_label: "#64748b",
  ocean_label: "#3a86c8",
};

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
    layers: layers("protomaps", NADJET_FLAVOR, { lang }),
  };
}
