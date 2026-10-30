import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap, Marker } from "maplibre-gl";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import type { Point } from "@/lib/sms-report";
import { BaseMap } from "@/map/BaseMap";
import type { MapLang } from "@/map/style";

/** Tap the map to place the crash when the phone cannot give its position (E-11). */
export default function LocationPicker({ onPick }: { onPick: (point: Point) => void }) {
  const { i18n } = useTranslation();
  const onLoad = useCallback(
    (map: MapLibreMap) => {
      let marker: Marker | null = null;
      map.getCanvas().style.cursor = "crosshair";
      map.on("click", (event) => {
        marker ??= new maplibregl.Marker().setLngLat(event.lngLat).addTo(map);
        marker.setLngLat(event.lngLat);
        onPick({ lat: event.lngLat.lat, lon: event.lngLat.lng });
      });
    },
    [onPick],
  );
  return (
    <BaseMap
      lang={i18n.language as MapLang}
      onLoad={onLoad}
      className="h-72 overflow-hidden rounded-lg border"
    />
  );
}
