import type { GeoJSONSource, Map as MapLibreMap, SymbolLayerSpecification } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";

import { BaseMap } from "@/map/BaseMap";
import type { MapLang } from "@/map/style";

import type { Camera, Incident, MapResources } from "@/lib/incident-queries";

export type PickedPoint = { lat: number; lon: number };

type Props = {
  incidents: Incident[];
  cameras: Camera[];
  resources: MapResources | undefined;
  selectedId?: string;
  pickMode: boolean;
  picked: PickedPoint | null;
  onSelectIncident: (id: string) => void;
  onPick: (point: PickedPoint) => void;
  className?: string;
};

type Collection = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: "Point"; coordinates: number[] };
    properties: Record<string, unknown>;
  }[];
};
const EMPTY: Collection = { type: "FeatureCollection", features: [] };
const FONT = ["Noto Sans Regular"];
const SOURCES = ["cameras", "facilities", "units", "incidents", "picked"] as const;

function point(lon: number, lat: number, properties: Record<string, unknown>) {
  return {
    type: "Feature" as const,
    geometry: { type: "Point" as const, coordinates: [lon, lat] },
    properties,
  };
}

/** Add the operator layers; safe to call again after a style swap (language change). */
function installLayers(map: MapLibreMap) {
  if (map.getSource("incidents")) return;
  for (const name of SOURCES) map.addSource(name, { type: "geojson", data: EMPTY });
  const label = (field: string): SymbolLayerSpecification["layout"] => ({
    "text-field": ["get", field],
    "text-font": FONT,
    "text-size": 11,
    "text-offset": [0, 1.2],
    "text-anchor": "top",
    "text-optional": true,
  });

  const halo = { "text-color": "#0f172a", "text-halo-color": "#ffffff", "text-halo-width": 1.5 };
  map.addLayer({
    id: "facilities",
    type: "circle",
    source: "facilities",
    paint: {
      "circle-radius": 5,
      "circle-color": "#1d4ed8",
      "circle-stroke-color": "#fff",
      "circle-stroke-width": 1.5,
    },
  });
  map.addLayer({
    id: "facilities-label",
    type: "symbol",
    source: "facilities",
    minzoom: 10,
    layout: label("label"),
    paint: halo,
  });
  map.addLayer({
    id: "units",
    type: "circle",
    source: "units",
    paint: {
      "circle-radius": 4,
      "circle-color": "#0f766e",
      "circle-stroke-color": "#fff",
      "circle-stroke-width": 1,
    },
  });
  map.addLayer({
    id: "units-label",
    type: "symbol",
    source: "units",
    minzoom: 11,
    layout: label("label"),
    paint: halo,
  });
  map.addLayer({
    id: "cameras",
    type: "circle",
    source: "cameras",
    paint: {
      "circle-radius": 6,
      "circle-color": [
        "match",
        ["get", "status"],
        "online",
        "#15803d",
        "degraded",
        "#b45309",
        "offline",
        "#b91c1c",
        "#64748b",
      ],
      "circle-stroke-color": "#fff",
      "circle-stroke-width": 2,
    },
  });
  map.addLayer({
    id: "cameras-label",
    type: "symbol",
    source: "cameras",
    minzoom: 9,
    layout: label("label"),
    paint: halo,
  });
  map.addLayer({
    id: "incidents",
    type: "circle",
    source: "incidents",
    paint: {
      "circle-radius": ["case", ["get", "selected"], 13, 10],
      "circle-color": [
        "match",
        ["get", "priority"],
        1,
        "#b91c1c",
        2,
        "#c2410c",
        3,
        "#92400e",
        "#475569",
      ],
      "circle-stroke-color": ["case", ["get", "selected"], "#0f172a", "#ffffff"],
      "circle-stroke-width": 3,
    },
  });
  map.addLayer({
    id: "incidents-label",
    type: "symbol",
    source: "incidents",
    layout: {
      "text-field": ["get", "label"],
      "text-font": FONT,
      "text-size": 12,
      "text-offset": [0, -1.4],
      "text-anchor": "bottom",
      "text-allow-overlap": true,
    },
    paint: { ...halo, "text-halo-width": 2 },
  });
  map.addLayer({
    id: "picked",
    type: "circle",
    source: "picked",
    paint: {
      "circle-radius": 9,
      "circle-color": "#ffffff",
      "circle-stroke-color": "#007dfe",
      "circle-stroke-width": 4,
    },
  });
}

function setData(map: MapLibreMap, name: (typeof SOURCES)[number], data: Collection) {
  (map.getSource(name) as GeoJSONSource | undefined)?.setData(data);
}

/**
 * Operator map: cameras (status in the label), incidents (priority in the label), facilities
 * and units (simulated ones say so in the label) — FR-MAP-001. A click on an incident opens it;
 * in pick mode a click places the point of a manual incident (FR-INC-007).
 */
export function OpsMap({
  incidents,
  cameras,
  resources,
  selectedId,
  pickMode,
  picked,
  onSelectIncident,
  onPick,
  className,
}: Props) {
  const { t, i18n } = useTranslation();
  const mapRef = useRef<MapLibreMap | null>(null);
  const live = useRef({ pickMode, onSelectIncident, onPick });
  useEffect(() => {
    live.current = { pickMode, onSelectIncident, onPick };
  }, [pickMode, onSelectIncident, onPick]);

  const collections = useMemo(() => {
    const simulated = ` (${t("simulated.label")})`;
    const mapped: Record<(typeof SOURCES)[number], Collection> = {
      cameras: {
        type: "FeatureCollection",
        features: cameras.map((c) =>
          point(c.lon, c.lat, {
            status: c.status,
            label: `${c.name} · ${t(`ops.cameraStatus.${c.status}`)}${c.simulated ? simulated : ""}`,
          }),
        ),
      },
      facilities: {
        type: "FeatureCollection",
        features: (resources?.facilities ?? []).map((f) =>
          point(f.lon, f.lat, { label: `${f.name}${f.simulated ? simulated : ""}` }),
        ),
      },
      units: {
        type: "FeatureCollection",
        features: (resources?.units ?? []).map((u) =>
          point(u.lon, u.lat, { label: `${u.callsign}${u.simulated ? simulated : ""}` }),
        ),
      },
      incidents: {
        type: "FeatureCollection",
        features: incidents.flatMap((i) =>
          i.lat === null || i.lon === null
            ? []
            : [
                point(i.lon, i.lat, {
                  id: i.id,
                  priority: i.priority,
                  selected: i.id === selectedId,
                  label: `P${i.priority} ${i.short_code}`,
                }),
              ],
        ),
      },
      picked: {
        type: "FeatureCollection",
        features: picked ? [point(picked.lon, picked.lat, {})] : [],
      },
    };
    return mapped;
  }, [incidents, cameras, resources, selectedId, picked, t]);

  const latest = useRef(collections);
  useEffect(() => {
    latest.current = collections;
    const map = mapRef.current;
    if (map?.getSource("incidents")) {
      for (const name of SOURCES) setData(map, name, collections[name]);
    }
  }, [collections]);

  useEffect(() => {
    const canvas = mapRef.current?.getCanvas();
    if (canvas) canvas.style.cursor = pickMode ? "crosshair" : "";
  }, [pickMode]);

  const onLoad = useCallback((map: MapLibreMap) => {
    mapRef.current = map;
    const install = () => {
      installLayers(map);
      for (const name of SOURCES) setData(map, name, latest.current[name]);
    };
    install();
    map.on("style.load", install);
    map.on("mouseenter", "incidents", () => {
      if (!live.current.pickMode) map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "incidents", () => {
      map.getCanvas().style.cursor = live.current.pickMode ? "crosshair" : "";
    });
    map.on("click", (event) => {
      if (live.current.pickMode) {
        live.current.onPick({ lat: event.lngLat.lat, lon: event.lngLat.lng });
        return;
      }
      const hit = map.queryRenderedFeatures(event.point, { layers: ["incidents"] })[0];
      const id = hit?.properties?.id as string | undefined;
      if (id) live.current.onSelectIncident(id);
    });
  }, []);

  return <BaseMap lang={i18n.language as MapLang} onLoad={onLoad} className={className} />;
}
