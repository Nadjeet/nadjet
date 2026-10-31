import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  useDispatches,
  type Camera,
  type Incident,
  type MapResources,
} from "@/lib/incident-queries";
import { cn } from "@/lib/utils";

import { OpsMap, type PickedPoint } from "../incident/ops-map";
import { RouteMap, type RouteLine } from "../incident/route-map";

const DISPATCHED = new Set([
  "dispatched",
  "acknowledged",
  "en_route",
  "on_scene",
  "transporting",
  "at_hospital",
]);

/** Figma "Bottom Corridor Status Mini-Ribbon" tile: uppercase label over a short value. */
function Stat({ label, value, tone }: { label: string; value: string; tone?: "danger" | "ok" }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-lg border border-line bg-surface-soft px-3 py-2">
      <span className="text-[0.6875rem] tracking-[0.55px] text-ink-subtle uppercase">{label}</span>
      <span
        className={cn(
          "truncate text-body-xs",
          tone === "danger"
            ? "text-danger-strong"
            : tone === "ok"
              ? "text-success-text"
              : "text-ink",
        )}
      >
        {value}
      </span>
    </div>
  );
}

/**
 * Figma "Live Routes" bento (node 75:6512 and its ribbon): the selected incident's camera chip,
 * route and receiving hospital card, with an "All incidents" view for the full operational map
 * (FR-MAP-001), then three status tiles built from real data.
 */
export function LiveRoutes({
  incident,
  incidents,
  cameras,
  resources,
  pickMode,
  picked,
  onSelectIncident,
  onPick,
}: {
  incident: Incident | null;
  incidents: Incident[];
  cameras: Camera[];
  resources: MapResources | undefined;
  pickMode: boolean;
  picked: PickedPoint | null;
  onSelectIncident: (id: string) => void;
  onPick: (point: PickedPoint) => void;
}) {
  const { t } = useTranslation();
  const [view, setView] = useState<"route" | "all">("route");
  const dispatched = incident !== null && DISPATCHED.has(incident.status);
  const dispatches = useDispatches(incident?.id ?? "", dispatched);
  const rows = dispatched ? (dispatches.data ?? []) : [];
  const hospital = rows.find((row) => row.kind === "hospital");
  const unit = rows.find((row) => row.kind === "unit");
  const camera = cameras.find((c) => c.id === incident?.camera_id);
  const ready = hospital
    ? resources?.facilities.find((f) => f.id === hospital.resource_id)?.ready_state !== "divert"
    : true;
  const routes: RouteLine[] = rows.flatMap((row) =>
    row.route_geojson
      ? [
          {
            id: row.id,
            kind: row.kind === "hospital" ? ("hospital" as const) : ("unit" as const),
            label:
              row.kind === "hospital"
                ? t("ops.dispatch.hospitalRoute", { name: row.name })
                : t("ops.dispatch.unitRoute", { name: row.name }),
            geometry: row.route_geojson as RouteLine["geometry"],
          },
        ]
      : [],
  );
  const showAll = view === "all" || pickMode || !incident;

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h2 id="map-title" className="text-body-md font-medium text-ink">
          {t("ops.console.liveRoutes")}
        </h2>
        <div
          role="group"
          aria-label={t("ops.console.liveRoutes")}
          className="inline-flex rounded-md border border-line bg-white p-0.5 text-body-xs"
        >
          {(["route", "all"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={view === option}
              onClick={() => setView(option)}
              className={cn(
                "rounded-[5px] px-2 py-0.5 transition-colors focus-visible:shadow-focus",
                view === option ? "bg-surface-strong text-brand-500" : "text-ink-body",
              )}
            >
              {t(option === "route" ? "ops.console.viewRoute" : "ops.console.viewAll")}
            </button>
          ))}
        </div>
      </div>
      {showAll ? (
        <OpsMap
          className="min-h-[24rem] flex-1 overflow-hidden rounded-lg border border-surface-strong bg-surface-soft"
          incidents={incidents}
          cameras={cameras}
          resources={resources}
          selectedId={incident?.id}
          pickMode={pickMode}
          picked={picked}
          onSelectIncident={onSelectIncident}
          onPick={onPick}
        />
      ) : (
        <RouteMap
          key={incident.id}
          scene={
            incident.lat !== null && incident.lon !== null
              ? { lat: incident.lat, lon: incident.lon }
              : null
          }
          routes={routes}
          camera={camera ? { label: camera.id, status: camera.status } : undefined}
          hospital={
            hospital
              ? {
                  name: hospital.name,
                  detail: ready ? t("ops.console.accepting") : t("ops.console.diverting"),
                  ready,
                }
              : undefined
          }
          className="min-h-[24rem] flex-1 overflow-hidden rounded-lg border border-surface-strong bg-surface-soft"
        />
      )}
      <div className="grid grid-cols-3 gap-3">
        <Stat
          label={t("ops.console.statStatus")}
          value={incident ? t(`status.${incident.status}`) : t("ops.console.kpi.none")}
          tone={incident?.status === "candidate" ? "danger" : undefined}
        />
        <Stat
          label={t("ops.console.statUnit")}
          value={
            unit
              ? t("ops.console.minutes", { count: Math.max(1, Math.round(unit.eta_s / 60)) })
              : t("ops.console.notDispatched")
          }
        />
        <Stat
          label={t("ops.console.statHospital")}
          value={hospital ? hospital.name : t("ops.console.notDispatched")}
          tone={hospital ? (ready ? "ok" : "danger") : undefined}
        />
      </div>
    </div>
  );
}
