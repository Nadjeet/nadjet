import type { Map as MapLibreMap } from "maplibre-gl";
import { MinusIcon, NavigationIcon, PlusIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

/**
 * Figma "Map Zoom & Recenter Controls": a white 12 px card with three 28 px buttons (zoom in,
 * zoom out, recenter on the scene). Placed at the inline end so it follows RTL.
 */
export function MapControls({
  map,
  onRecenter,
  className,
}: {
  map: MapLibreMap | null;
  onRecenter: () => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const button =
    "grid size-7 place-items-center rounded-md text-ink transition-colors hover:bg-surface-strong focus-visible:shadow-focus disabled:opacity-40";
  return (
    <div
      className={cn(
        "absolute end-1.5 top-1.5 z-10 flex flex-col gap-1 rounded-lg border border-line bg-white p-[5px]",
        className,
      )}
    >
      <button
        type="button"
        className={button}
        disabled={!map}
        onClick={() => map?.zoomIn()}
        aria-label={t("map.zoomIn")}
        title={t("map.zoomIn")}
      >
        <PlusIcon aria-hidden className="size-3.5" />
      </button>
      <button
        type="button"
        className={button}
        disabled={!map}
        onClick={() => map?.zoomOut()}
        aria-label={t("map.zoomOut")}
        title={t("map.zoomOut")}
      >
        <MinusIcon aria-hidden className="size-3.5" />
      </button>
      <button
        type="button"
        className={button}
        disabled={!map}
        onClick={onRecenter}
        aria-label={t("map.recenter")}
        title={t("map.recenter")}
      >
        <NavigationIcon aria-hidden className="size-3.5 text-brand-500" />
      </button>
    </div>
  );
}

/** Figma camera marker: a white frosted chip with a status dot and the camera id. */
export function CameraChip({
  label,
  status,
  className,
}: {
  label: string;
  status: "online" | "degraded" | "offline" | "unknown";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-[rgb(226_232_240/0.8)] bg-white/95 px-[11px] py-[5px] text-body-xs whitespace-nowrap text-brand-900 shadow-[0_1px_2px_rgb(0_0_0/0.05)] backdrop-blur-md",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-2 rounded-full",
          status === "online"
            ? "bg-danger-strong"
            : status === "degraded"
              ? "bg-warning"
              : "bg-ink-subtle",
        )}
      />
      <bdi dir="ltr">{label}</bdi>
    </span>
  );
}

/** Figma hospital card on the map: brand-100 icon tile, name and the readiness line in green. */
export function HospitalCard({
  name,
  detail,
  ready,
  className,
}: {
  name: string;
  detail: string;
  ready: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "absolute start-4 bottom-4 z-10 flex max-w-[20rem] items-center gap-2.5 rounded-lg border border-brand-indigo bg-white/95 p-[11px] shadow-[0_4px_6px_-1px_rgb(0_0_0/0.1),0_2px_4px_-2px_rgb(0_0_0/0.1)] backdrop-blur-md",
        className,
      )}
    >
      <span
        aria-hidden
        className="grid size-8 shrink-0 place-items-center rounded-md bg-brand-100 text-white"
      >
        <svg
          viewBox="0 0 24 24"
          className="size-[18px]"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 11v4M10 13h4M16 6V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
          <rect width="20" height="14" x="2" y="6" rx="2" />
        </svg>
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-body-xs font-medium text-ink">{name}</span>
        <span
          className={cn(
            "truncate text-body-xs font-light",
            ready ? "text-success-text" : "text-danger-strong",
          )}
        >
          {detail}
        </span>
      </span>
    </div>
  );
}
