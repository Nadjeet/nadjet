import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { MapControls } from "./map-controls";
import { basemapStyle, type MapLang } from "./style";

// The package only exports its ESM source, so reference the built plugin file by path.
const rtlTextPluginUrl = new URL(
  "../../node_modules/@mapbox/mapbox-gl-rtl-text/dist/mapbox-gl-rtl-text.js",
  import.meta.url,
).href;

// maplibre-gl 6 ships an ES-module worker; bundle it so Vite can serve it in dev and build.
maplibregl.setWorkerUrl(workerUrl);

// Register the pmtiles:// protocol and the self-hosted Arabic shaping plugin once per page.
maplibregl.addProtocol("pmtiles", new Protocol().tile);
if (maplibregl.getRTLTextPluginStatus() === "unavailable") {
  void maplibregl.setRTLTextPlugin(rtlTextPluginUrl, true);
}

/** Boumerdès / Algiers demo area (PRD Q-09). */
const DEMO_CENTER: [number, number] = [3.47, 36.76];

type BaseMapProps = {
  lang: MapLang;
  center?: [number, number];
  zoom?: number;
  className?: string;
  /** Called once the style is loaded so callers can add their own layers. */
  onLoad?: (map: MapLibreMap) => void;
  /** Where the recenter button goes (default: the initial view). */
  onRecenter?: (map: MapLibreMap) => void;
  /** Opens or closes the large map (expand button in the controls). */
  onExpand?: () => void;
  expanded?: boolean;
  /** Figma overlays drawn over the map (camera chip, hospital card). */
  children?: ReactNode;
};

/** Offline vector basemap of Algeria with the OpenStreetMap attribution (FR-MAP-001). */
export function BaseMap({
  lang,
  center = DEMO_CENTER,
  zoom = 9,
  className,
  onLoad,
  onRecenter,
  onExpand,
  expanded,
  children,
}: BaseMapProps) {
  const { t } = useTranslation();
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const onLoadRef = useRef(onLoad);
  const [failed, setFailed] = useState(false);
  const [instance, setInstance] = useState<MapLibreMap | null>(null);
  const initial = useRef({ center, zoom });

  useEffect(() => {
    onLoadRef.current = onLoad;
  }, [onLoad]);

  // Create the map once; the initial view and language are read at mount time.
  useEffect(() => {
    if (!container.current) return;
    const instance = new maplibregl.Map({
      container: container.current,
      style: basemapStyle(lang),
      center,
      zoom,
      attributionControl: { compact: false },
    });
    instance.on("load", () => {
      setInstance(instance);
      onLoadRef.current?.(instance);
    });
    instance.on("error", (event) => {
      if ((event as { sourceId?: string }).sourceId === "protomaps") setFailed(true);
    });
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Switching language swaps the label layers without recreating the map.
  const styledLang = useRef(lang);
  useEffect(() => {
    if (styledLang.current === lang) return; // the map was created with this language
    styledLang.current = lang;
    map.current?.setStyle(basemapStyle(lang));
  }, [lang]);

  return (
    <div className={`relative ${className ?? ""}`}>
      {/* maplibre's CSS makes the container `position: relative`, so size it instead of inset-0 */}
      <div ref={container} className="h-full w-full" />
      <MapControls
        map={instance}
        onExpand={onExpand}
        expanded={expanded}
        onRecenter={() => {
          if (!instance) return;
          if (onRecenter) onRecenter(instance);
          else instance.easeTo({ center: initial.current.center, zoom: initial.current.zoom });
        }}
      />
      {children}
      {failed && (
        <p
          role="alert"
          className="absolute start-3 top-3 rounded bg-amber-100 px-3 py-2 text-sm text-amber-900"
        >
          {t("map.unavailable")}
        </p>
      )}
    </div>
  );
}
