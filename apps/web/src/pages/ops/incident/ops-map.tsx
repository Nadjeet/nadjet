import { Marker } from "maplibre-gl";
import type { GeoJSONSource, Map as MapLibreMap, SymbolLayerSpecification } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { formatAge, useLabel } from "@/lib/format";
import { locationText } from "@/lib/incident-format";
import { BaseMap } from "@/map/BaseMap";
import { addIcons } from "@/map/icons";
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
  /** Opens or closes the large map (expand button in the map controls). */
  onExpand?: () => void;
  expanded?: boolean;
  className?: string;
};

type Hover = { id: string; x: number; y: number };

/**
 * Card shown over a hovered incident pin: priority, code, age, type, place and status, with the
 * hint that a click opens the incident page.
 */
function IncidentHoverCard({ incident, x, y }: { incident: Incident; x: number; y: number }) {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  return (
    <div
      role="tooltip"
      style={{ left: x, top: y }}
      className="pointer-events-none absolute z-20 flex w-64 -translate-x-1/2 -translate-y-[calc(100%+3.25rem)] flex-col gap-1.5 rounded-lg border-2 border-brand-indigo bg-white p-3 shadow-card"
    >
      <div className="flex items-center gap-1.5">
        {incident.priority === 1 ? (
          <span className="rounded-md bg-danger px-1 py-0.5 text-[0.625rem] leading-[0.9rem] text-white">
            {t("priority.p1")}
          </span>
        ) : (
          <PriorityBadge level={incident.priority as PriorityLevel} compact />
        )}
        <bdi dir="ltr" className="text-body-xs font-semibold text-ink">
          INC-{incident.short_code}
        </bdi>
        <span className="ms-auto text-body-xs whitespace-nowrap text-brand-500">
          {formatAge(incident.event_time, i18n.language)}
        </span>
      </div>
      <p className="text-body-xs text-ink">{label(`ops.type.${incident.type}`, incident.type)}</p>
      <p className="truncate text-[0.6875rem] text-ink-muted">{locationText(incident)}</p>
      <div className="flex items-center justify-between gap-2 border-t border-line pt-1.5">
        <span className="text-[0.6875rem] text-brand-900">{t(`status.${incident.status}`)}</span>
        <span className="text-[0.6875rem] font-medium text-brand-500">{t("map.openDetails")}</span>
      </div>
    </div>
  );
}

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
  const label = (field: string, offset: number): SymbolLayerSpecification["layout"] => ({
    "text-field": ["get", field],
    "text-font": FONT,
    "text-size": 11,
    "text-offset": [0, offset],
    "text-anchor": "top",
    "text-optional": true,
  });
  const halo = { "text-color": "#0f172a", "text-halo-color": "#ffffff", "text-halo-width": 1.5 };

  // Civil Protection, Gendarmerie and police posts: small blue dots (Figma map stays quiet).
  map.addLayer({
    id: "facilities",
    type: "circle",
    source: "facilities",
    filter: ["!=", ["get", "kind"], "hospital"],
    paint: {
      "circle-radius": 4,
      "circle-color": "#55a8fe",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1.5,
    },
  });
  // Hospitals: the Figma "briefcase-medical" tile.
  map.addLayer({
    id: "hospitals",
    type: "symbol",
    source: "facilities",
    filter: ["==", ["get", "kind"], "hospital"],
    layout: {
      "icon-image": "nadjet-hospital",
      "icon-size": ["interpolate", ["linear"], ["zoom"], 7, 0.5, 12, 0.85],
      "icon-allow-overlap": true,
    },
  });
  map.addLayer({
    id: "facilities-label",
    type: "symbol",
    source: "facilities",
    minzoom: 11,
    layout: label("label", 1.2),
    paint: halo,
  });
  // Units: the Figma blue navigation marker.
  map.addLayer({
    id: "units",
    type: "symbol",
    source: "units",
    layout: {
      "icon-image": "nadjet-unit",
      "icon-size": ["interpolate", ["linear"], ["zoom"], 7, 0.45, 12, 0.7],
      "icon-allow-overlap": true,
    },
  });
  map.addLayer({
    id: "units-label",
    type: "symbol",
    source: "units",
    minzoom: 11,
    layout: label("label", 1.4),
    paint: halo,
  });
  // Incidents: the Figma red drop pin, larger when selected, with "P1 7F3" above it.
  map.addLayer({
    id: "incidents",
    type: "symbol",
    source: "incidents",
    layout: {
      "icon-image": "nadjet-pin",
      "icon-anchor": "bottom",
      "icon-size": ["case", ["get", "selected"], 1.45, 1.1],
      "icon-allow-overlap": true,
      "symbol-sort-key": ["get", "priority"],
      "text-field": ["get", "label"],
      "text-font": FONT,
      "text-size": 12,
      "text-anchor": "bottom",
      "text-offset": [0, -2.9],
      "text-allow-overlap": true,
    },
    paint: { ...halo, "text-halo-width": 2 },
  });
  map.addLayer({
    id: "picked",
    type: "symbol",
    source: "picked",
    layout: { "icon-image": "nadjet-place", "icon-allow-overlap": true },
  });
}

/** Figma camera marker as a DOM chip: frosted white pill, status dot, camera id. */
function cameraChip(camera: Camera, title: string): HTMLElement {
  const chip = document.createElement("span");
  chip.className =
    "inline-flex items-center gap-1.5 rounded-md border border-[rgb(226_232_240/0.8)] bg-white/95 px-2 py-1 text-[0.6875rem] whitespace-nowrap text-brand-900 shadow-[0_1px_2px_rgb(0_0_0/0.05)] backdrop-blur-md";
  chip.title = title;
  const dot = document.createElement("span");
  dot.setAttribute("aria-hidden", "true");
  dot.className = `size-2 rounded-full ${
    camera.status === "online"
      ? "bg-danger-strong"
      : camera.status === "degraded"
        ? "bg-warning"
        : "bg-ink-subtle"
  }`;
  const name = document.createElement("bdi");
  name.dir = "ltr";
  name.textContent = camera.id;
  chip.append(dot, name);
  return chip;
}

function setData(map: MapLibreMap, name: (typeof SOURCES)[number], data: Collection) {
  (map.getSource(name) as GeoJSONSource | undefined)?.setData(data);
}

/**
 * Operator map: cameras (status in the label), incidents (priority in the label), facilities
 * and units (simulated ones say so in the label) — FR-MAP-001. Hovering an incident shows its
 * summary card and a click opens it;
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
  onExpand,
  expanded,
  className,
}: Props) {
  const { t, i18n } = useTranslation();
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [hover, setHover] = useState<Hover | null>(null);
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
          point(f.lon, f.lat, { kind: f.kind, label: `${f.name}${f.simulated ? simulated : ""}` }),
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

  // Cameras are DOM chips (the Figma marker cannot be drawn as a map symbol).
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const markers = cameras.map((camera) =>
      new Marker({
        element: cameraChip(camera, `${camera.name} · ${t(`ops.cameraStatus.${camera.status}`)}`),
        anchor: "bottom",
      })
        .setLngLat([camera.lon, camera.lat])
        .addTo(map),
    );
    return () => markers.forEach((marker) => marker.remove());
  }, [cameras, ready, t]);

  const onLoad = useCallback((map: MapLibreMap) => {
    mapRef.current = map;
    setReady(true);
    const install = () => {
      void addIcons(map, ["pin", "unit", "hospital", "place"]).then(() => {
        installLayers(map);
        for (const name of SOURCES) setData(map, name, latest.current[name]);
      });
    };
    install();
    map.on("style.load", install);
    map.on("mouseenter", "incidents", () => {
      if (!live.current.pickMode) map.getCanvas().style.cursor = "pointer";
    });
    map.on("mousemove", "incidents", (event) => {
      const id = event.features?.[0]?.properties?.id as string | undefined;
      if (!id || live.current.pickMode) return;
      setHover({ id, x: event.point.x, y: event.point.y });
    });
    map.on("mouseleave", "incidents", () => {
      map.getCanvas().style.cursor = live.current.pickMode ? "crosshair" : "";
      setHover(null);
    });
    map.on("movestart", () => setHover(null));
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

  const hovered = hover ? incidents.find((i) => i.id === hover.id) : undefined;
  return (
    <BaseMap
      lang={i18n.language as MapLang}
      onLoad={onLoad}
      onExpand={onExpand}
      expanded={expanded}
      className={className}
    >
      {hover && hovered ? <IncidentHoverCard incident={hovered} x={hover.x} y={hover.y} /> : null}
    </BaseMap>
  );
}
