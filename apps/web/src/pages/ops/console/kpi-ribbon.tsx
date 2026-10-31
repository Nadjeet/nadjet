import { ArrowUpRightIcon, type LucideIcon } from "lucide-react";
import {
  AmbulanceIcon,
  GaugeIcon,
  HospitalIcon,
  SirenIcon,
  TriangleAlertIcon,
  CpuIcon,
  MapPinIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import type { Incident, MapResources } from "@/lib/incident-queries";
import { cn } from "@/lib/utils";

/** Median of a list (null when empty): no value is ever invented. */
function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
}

function KpiCard({
  title,
  value,
  hint,
  icon: Icon,
  hintIcon: HintIcon,
  badge,
}: {
  title: string;
  value: string;
  hint: string;
  icon: LucideIcon;
  hintIcon: LucideIcon;
  badge?: number;
}) {
  return (
    <div className="flex min-h-36 flex-col justify-between gap-3 rounded-2xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <p className="text-body-sm text-primary">{title}</p>
        <span
          aria-hidden
          className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-400 text-white"
        >
          <Icon className="size-4" />
        </span>
      </div>
      <p className="relative w-fit text-display-sm font-semibold tracking-tight text-brand-500">
        {value}
        {badge ? (
          <span className="absolute start-full top-0 ms-1 grid h-4 min-w-4 place-items-center rounded-full bg-danger px-1 text-[0.625rem] font-semibold text-white">
            {badge}
          </span>
        ) : null}
      </p>
      <p className="flex items-center gap-1.5 truncate text-body-xs text-ink-muted">
        <HintIcon aria-hidden className="size-3.5 shrink-0 text-brand-300" />
        <span className="truncate">{hint}</span>
      </p>
    </div>
  );
}

/**
 * Figma "Top Bento KPI Ribbon": four live figures computed from the data the console already
 * holds (open incidents, their detection delay, units and hospital readiness). Nothing is
 * estimated: a missing figure shows a dash.
 */
export function KpiRibbon({
  open,
  resources,
  className,
}: {
  open: Incident[] | undefined;
  resources: MapResources | undefined;
  className?: string;
}) {
  const { t } = useTranslation();
  const none = t("ops.console.kpi.none");
  const awaiting = (open ?? []).filter((incident) => incident.status === "candidate").length;
  const delays = (open ?? [])
    .map((i) => (Date.parse(i.created_at) - Date.parse(i.event_time)) / 1000)
    .filter((seconds) => Number.isFinite(seconds) && seconds >= 0);
  const detection = median(delays);
  const units = resources?.units ?? [];
  const available = units.filter((unit) => unit.status === "available").length;
  const hospitals = (resources?.facilities ?? []).filter((f) => f.kind === "hospital");
  const ready = hospitals.filter((f) => f.ready_state === "ready").length;

  return (
    <section
      aria-label={t("ops.console.title")}
      className={cn("grid gap-4 sm:grid-cols-2 xl:grid-cols-4 xl:gap-6", className)}
    >
      <KpiCard
        title={t("ops.console.kpi.active")}
        value={open ? String(open.length) : none}
        badge={awaiting || undefined}
        hint={t("ops.console.kpi.activeHint", { count: awaiting })}
        icon={SirenIcon}
        hintIcon={TriangleAlertIcon}
      />
      <KpiCard
        title={t("ops.console.kpi.detection")}
        value={detection === null ? none : `${detection.toFixed(1)} s`}
        hint={t("ops.console.kpi.detectionHint")}
        icon={GaugeIcon}
        hintIcon={CpuIcon}
      />
      <KpiCard
        title={t("ops.console.kpi.units")}
        value={resources ? t("ops.console.kpi.unitsValue", { count: available }) : none}
        hint={t("ops.console.kpi.unitsHint", { total: units.length })}
        icon={AmbulanceIcon}
        hintIcon={MapPinIcon}
      />
      <KpiCard
        title={t("ops.console.kpi.hospitals")}
        value={resources ? t("ops.console.kpi.hospitalsValue", { count: ready }) : none}
        hint={t("ops.console.kpi.hospitalsHint", { total: hospitals.length })}
        icon={HospitalIcon}
        hintIcon={ArrowUpRightIcon}
      />
    </section>
  );
}
