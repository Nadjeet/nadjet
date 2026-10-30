import type { GeoJSONSource, LngLatBoundsLike, Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { BaseMap } from "@/map/BaseMap";
import type { MapLang } from "@/map/style";

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
  // Unit → scene is solid, scene → hospital is dashed; both carry a text label.
  map.addLayer({
    id: "routes-unit",
    type: "line",
    source: "routes",
    filter: ["==", ["get", "kind"], "unit"],
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#0053a9", "line-width": 5 },
  });
  map.addLayer({
    id: "routes-hospital",
    type: "line",
    source: "routes",
    filter: ["==", ["get", "kind"], "hospital"],
    layout: { "line-join": "round" },
    paint: { "line-color": "#b91c1c", "line-width": 5, "line-dasharray": [2, 1.5] },
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
  map.addLayer({
    id: "scene",
    type: "circle",
    source: "scene",
    paint: {
      "circle-radius": 9,
      "circle-color": "#ffffff",
      "circle-stroke-color": "#0f172a",
      "circle-stroke-width": 4,
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
      "text-offset": [0, 1.4],
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
export function RouteMap({ scene, routes, className }: Props) {
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
      (map.getSource("routes") as GeoJSONSource | undefined)?.setData(lines);
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
      install(map);
      latest.current(map);
    };
    ready();
    map.on("style.load", ready);
  }, []);

  return <BaseMap lang={i18n.language as MapLang} onLoad={onLoad} className={className} />;
}
