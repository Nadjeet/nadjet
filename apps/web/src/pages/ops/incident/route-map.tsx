import type { GeoJSONSource, LngLatBoundsLike, Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { BaseMap } from "@/map/BaseMap";
import type { MapLang } from "@/map/style";
import { addIcons } from "@/map/icons";
import { CameraChip, HospitalCard } from "@/map/map-controls";

export type RouteLine = {
  id: string;
  kind: "unit" | "hospital";
  /** Text drawn along the line: the route is never told by colour alone. */
  label: string;
  geometry: { type?: string; coordinates?: unknown } | null | undefined;
};

type Props = {
  scene: { lat: number; lon: number } | null;
  routes: RouteLine[];
  /** Figma hospital card in the bottom corner (name and readiness line). */
  hospital?: { name: string; detail: string; ready: boolean };
  /** Figma camera chip in the top corner. */
  camera?: { label: string; status: "online" | "degraded" | "offline" | "unknown" };
  className?: string;
};

type Lines = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: "LineString"; coordinates: number[][] };
    properties: Record<string, unknown>;
  }[];
};
type Points = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: "Point"; coordinates: number[] };
    properties: Record<string, unknown>;
  }[];
};

const FONT = ["Noto Sans Regular"];
const EMPTY = { type: "FeatureCollection", features: [] } as const;

function install(map: MapLibreMap) {
  if (map.getSource("routes")) return;
  map.addSource("routes", { type: "geojson", data: EMPTY });
  map.addSource("scene", { type: "geojson", data: EMPTY });
  map.addSource("starts", { type: "geojson", data: EMPTY });
  // Figma route: bright blue #13a9ff, 7.5 px, round joins. Unit → scene is solid,
  // scene → hospital is dashed (the kind is also written along the line).
  map.addLayer({
    id: "routes-unit",
    type: "line",
    source: "routes",
    filter: ["==", ["get", "kind"], "unit"],
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#13a9ff", "line-width": 7.5 },
  });
  map.addLayer({
    id: "routes-hospital",
    type: "line",
    source: "routes",
    filter: ["==", ["get", "kind"], "hospital"],
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#13a9ff", "line-width": 6, "line-dasharray": [1.2, 1.4] },
  });
  map.addLayer({
    id: "routes-label",
    type: "symbol",
    source: "routes",
    layout: {
      "symbol-placement": "line",
      "text-field": ["get", "label"],
      "text-font": FONT,
      "text-size": 12,
    },
    paint: { "text-color": "#0f172a", "text-halo-color": "#ffffff", "text-halo-width": 2 },
  });
  // Unit positions: the Figma navigation marker at the start of each unit route.
  map.addLayer({
    id: "starts",
    type: "symbol",
    source: "starts",
    layout: { "icon-image": "nadjet-unit", "icon-size": 0.8, "icon-allow-overlap": true },
  });
  // The scene: the Figma red drop pin.
  map.addLayer({
    id: "scene",
    type: "symbol",
    source: "scene",
    layout: {
      "icon-image": "nadjet-pin",
      "icon-anchor": "bottom",
      "icon-size": 1.25,
      "icon-allow-overlap": true,
    },
  });
  map.addLayer({
    id: "scene-label",
    type: "symbol",
    source: "scene",
    layout: {
      "text-field": ["get", "label"],
      "text-font": FONT,
      "text-size": 12,
      "text-offset": [0, 0.4],
      "text-anchor": "top",
    },
    paint: { "text-color": "#0f172a", "text-halo-color": "#ffffff", "text-halo-width": 2 },
  });
}

function coordinatesOf(route: RouteLine): number[][] | null {
  const line = route.geometry;
  if (line?.type !== "LineString" || !Array.isArray(line.coordinates)) return null;
  return line.coordinates as number[][];
}

/** The routes of the recommended or dispatched resources on the offline basemap (FR-DSP-004). */
export function RouteMap({ scene, routes, className, hospital, camera }: Props) {
  const { t, i18n } = useTranslation();
  const mapRef = useRef<MapLibreMap | null>(null);

  const apply = useCallback(
    (map: MapLibreMap) => {
      const lines: Lines = {
        type: "FeatureCollection",
        features: routes.flatMap((route) => {
          const coordinates = coordinatesOf(route);
          return coordinates
            ? [
                {
                  type: "Feature" as const,
                  geometry: { type: "LineString" as const, coordinates },
                  properties: { kind: route.kind, label: route.label },
                },
              ]
            : [];
        }),
      };
      const points: Points = {
        type: "FeatureCollection",
        features: scene
          ? [
              {
                type: "Feature",
                geometry: { type: "Point", coordinates: [scene.lon, scene.lat] },
                properties: { label: t("ops.dispatch.scene") },
              },
            ]
          : [],
      };
      const starts: Points = {
        type: "FeatureCollection",
        features: lines.features.flatMap((f) =>
          f.properties.kind === "unit" && f.geometry.coordinates[0]
            ? [
                {
                  type: "Feature" as const,
                  geometry: { type: "Point" as const, coordinates: f.geometry.coordinates[0] },
                  properties: {},
                },
              ]
            : [],
        ),
      };
      (map.getSource("routes") as GeoJSONSource | undefined)?.setData(lines);
      (map.getSource("starts") as GeoJSONSource | undefined)?.setData(starts);
      (map.getSource("scene") as GeoJSONSource | undefined)?.setData(points);
      const all = [
        ...lines.features.flatMap((f) => f.geometry.coordinates),
        ...points.features.map((f) => f.geometry.coordinates),
      ];
      if (all.length > 0) {
        const bounds: [number, number, number, number] = all.reduce<
          [number, number, number, number]
        >(
          (b, [lon = 0, lat = 0]) => [
            Math.min(b[0], lon),
            Math.min(b[1], lat),
            Math.max(b[2], lon),
            Math.max(b[3], lat),
          ],
          [180, 90, -180, -90],
        );
        map.fitBounds(
          [
            [bounds[0], bounds[1]],
            [bounds[2], bounds[3]],
          ] as LngLatBoundsLike,
          { padding: 48, maxZoom: 15, duration: 0 },
        );
      }
    },
    [routes, scene, t],
  );

  const latest = useRef(apply);
  useEffect(() => {
    latest.current = apply;
    const map = mapRef.current;
    if (map?.getSource("routes")) apply(map);
  }, [apply]);

  const onLoad = useCallback((map: MapLibreMap) => {
    mapRef.current = map;
    const ready = () => {
      void addIcons(map, ["pin", "unit"]).then(() => {
        install(map);
        latest.current(map);
      });
    };
    ready();
    map.on("style.load", ready);
  }, []);

  return (
    <BaseMap
      lang={i18n.language as MapLang}
      onLoad={onLoad}
      onRecenter={(map) => latest.current(map)}
      className={className}
    >
      {camera ? (
        <CameraChip
          label={camera.label}
          status={camera.status}
          className="absolute start-2 top-1.5 z-10"
        />
      ) : null}
      {hospital ? (
        <HospitalCard name={hospital.name} detail={hospital.detail} ready={hospital.ready} />
      ) : null}
    </BaseMap>
  );
}
