import { layers, namedFlavor, type Flavor } from "@protomaps/basemaps";
import type { StyleSpecification } from "maplibre-gl";

export type MapLang = "ar" | "fr" | "en";

/** Same-origin PMTiles archive served by the API with Range requests (`make map-data`). */
export const TILES_URL = "/api/tiles/algeria.pmtiles";

const OSM_ATTRIBUTION =
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/**
 * Figma map (dashboard "Live Routes", app "Incidents Map", TD-55): flat grey land `#f0f0f0`,
 * white streets with no casing, parks `#b4e7c7`, water `#85d5eb`, small dark street names and
 * no points of interest, so the blue route and the red pins are what the eye finds first.
 */
const LIGHT = namedFlavor("light");
const LAND = "#f0f0f0";
const ROAD = "#ffffff";
const PARK = "#b4e7c7";
const WATER = "#85d5eb";

export const NADJET_FLAVOR: Flavor = {
  ...LIGHT,
  background: LAND,
  earth: LAND,
  park_a: PARK,
  park_b: PARK,
  wood_a: PARK,
  wood_b: PARK,
  scrub_a: "#cdeed8",
  scrub_b: "#cdeed8",
  zoo: PARK,
  landcover: LIGHT.landcover
    ? {
        ...LIGHT.landcover,
        grassland: "#d6f0de",
        forest: PARK,
        scrub: "#cdeed8",
        farmland: LAND,
        urban_area: LAND,
        barren: LAND,
      }
    : undefined,
  water: WATER,
  buildings: "#e6e6e6",
  hospital: LAND,
  school: LAND,
  industrial: LAND,
  military: LAND,
  sand: "#efece2",
  beach: "#efece2",
  aerodrome: "#e8e8e8",
  pedestrian: LAND,
  pier: ROAD,
  other: ROAD,
  minor_a: ROAD,
  minor_b: ROAD,
  minor_service: ROAD,
  link: ROAD,
  major: ROAD,
  highway: ROAD,
  minor_casing: LAND,
  minor_service_casing: LAND,
  link_casing: LAND,
  major_casing_early: LAND,
  major_casing_late: LAND,
  highway_casing_early: "#e3e3e3",
  highway_casing_late: "#e3e3e3",
  tunnel_other: ROAD,
  tunnel_minor: ROAD,
  tunnel_link: ROAD,
  tunnel_major: ROAD,
  tunnel_highway: ROAD,
  bridges_other: ROAD,
  bridges_minor: ROAD,
  bridges_link: ROAD,
  bridges_major: ROAD,
  bridges_highway: ROAD,
  railway: "#d4d4d4",
  boundaries: "#b8b8b8",
  roads_label_minor: "#1f2937",
  roads_label_minor_halo: ROAD,
  roads_label_major: "#111827",
  roads_label_major_halo: ROAD,
  city_label: "#111827",
  city_label_halo: LAND,
  subplace_label: "#475569",
  subplace_label_halo: LAND,
  state_label: "#94a3b8",
  country_label: "#64748b",
  ocean_label: "#2f7f99",
};

/** Layers the Figma map leaves out: points of interest, shields, one-way arrows, addresses. */
const HIDDEN = new Set(["pois", "roads_shields", "roads_oneway", "address_label"]);

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
    layers: layers("protomaps", NADJET_FLAVOR, { lang }).filter((layer) => !HIDDEN.has(layer.id)),
  };
}
