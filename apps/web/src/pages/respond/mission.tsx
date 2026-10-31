import { Link } from "@tanstack/react-router";
import { ArrowLeftIcon, ExternalLinkIcon, NavigationIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { stepsFromEvents, type TimelineStatus } from "@/components/incident/lifecycle";
import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { StatusTimeline } from "@/components/incident/status-timeline";
import { buttonVariants } from "@/components/ui/button";
import { formatTime, useLabel } from "@/lib/format";
import { locationText } from "@/lib/incident-format";
import { useDispatches, type Incident, type IncidentDetail } from "@/lib/incident-queries";
import { geoUri, osmUrl } from "@/lib/sms-codes";
import { cn } from "@/lib/utils";
import { glassButton } from "@/layouts/phone-shell";
import { RouteMap } from "@/pages/ops/incident/route-map";

import { StatusActions } from "./status-actions";

/** Figma "MISSION DETAILS" header: glass back button, small label and title. */
export function MissionHeader({ title, back = true }: { title: string; back?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3">
      {back ? (
        <Link to="/respond" className={glassButton} aria-label={t("respond.detail.back")}>
          <ArrowLeftIcon aria-hidden className="size-6 rtl:rotate-180" />
        </Link>
      ) : null}
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-body-xs leading-5 font-medium text-ink-muted uppercase">
          {t("respond.detail.missionLabel")}
        </span>
        <h1 className="truncate text-body-md leading-6 font-medium text-[#081021]">{title}</h1>
      </div>
    </div>
  );
}

/** Figma section heading of the app ("Incidents Map", "Incident Visual"): 20 px semibold. */
export function SectionTitle({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="text-body-xl leading-7 font-semibold text-[#1a1c1c]">
      {children}
    </h2>
  );
}

/**
 * Figma mission card (app "mission" and "progress", node 74:4997): white, blue border, 12 px
 * radius; priority chip, type and vehicles, time in blue, location, then the next status as
 * the gradient button.
 */
export function MissionCard({
  incident,
  actions = true,
  className,
}: {
  incident: IncidentDetail | Incident;
  actions?: boolean;
  className?: string;
}) {
  const { i18n, t } = useTranslation();
  const label = useLabel();
  const vehicles = incident.ai_signals.vehicle_count;
  const type = label(`ops.type.${incident.type}`, incident.type);
  return (
    <section
      className={cn(
        "flex flex-col gap-3 rounded-xl border-2 border-brand-200 bg-white p-4 shadow-soft",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        {incident.priority === 1 ? (
          <span className="rounded-md bg-danger px-1 py-0.5 text-[0.625rem] leading-[0.9rem] text-white">
            {t("priority.p1")}
          </span>
        ) : (
          <PriorityBadge level={incident.priority as PriorityLevel} compact />
        )}
        <span className="truncate text-body-sm font-medium text-ink">
          {type}
          {vehicles ? ` · ${t("ops.signals.vehicles", { count: vehicles })}` : ""}
        </span>
        <span className="ms-auto shrink-0 text-body-xs text-brand-500">
          {formatTime(incident.event_time, i18n.language)}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        <p className="text-body-sm text-ink">
          <bdi dir="ltr">#{incident.short_code}</bdi> · {t(`status.${incident.status}`)}
        </p>
        <p className="text-body-xs text-ink-muted">{locationText(incident)}</p>
      </div>
      {actions && "events" in incident ? <StatusActions incident={incident} /> : null}
    </section>
  );
}

/** Steps of the mission from the signed event chain, and the current one. */
function missionSteps(incident: IncidentDetail) {
  const steps = stepsFromEvents(incident.events);
  const current = (steps.at(-1)?.status ?? "dispatched") as TimelineStatus;
  return { steps, current };
}

/** Figma "Mission Progress" card: the signed status steps with green checks (FR-RSP-002). */
export function MissionProgress({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const { steps, current } = missionSteps(incident);
  return (
    <section aria-labelledby="mission-progress" className="flex flex-col gap-3">
      <SectionTitle id="mission-progress">{t("respond.detail.progressTitle")}</SectionTitle>
      <div className="rounded-xl border border-line bg-white p-4 shadow-soft">
        <StatusTimeline steps={steps} current={current} from="dispatched" />
      </div>
    </section>
  );
}

/**
 * Figma "Incidents Map" card (blue 0.8 px border, 10 px radius): the scene, the hospital route
 * and the receiving hospital card, from the active hospital dispatch (FR-DSP-004).
 */
export function MissionMap({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const dispatches = useDispatches(incident.id, true);
  const hospital = dispatches.data?.find((d) => d.kind === "hospital");
  if (incident.lat === null || incident.lon === null) return null;
  return (
    <section aria-labelledby="mission-map" className="flex flex-col gap-3">
      <SectionTitle id="mission-map">{t("respond.detail.map")}</SectionTitle>
      <RouteMap
        scene={{ lat: incident.lat, lon: incident.lon }}
        routes={
          hospital
            ? [
                {
                  id: hospital.id,
                  kind: "hospital",
                  label: t("ops.dispatch.hospitalRoute", { name: hospital.name }),
                  geometry: hospital.route_geojson,
                },
              ]
            : []
        }
        camera={incident.camera_id ? { label: incident.camera_id, status: "unknown" } : undefined}
        hospital={
          hospital
            ? {
                name: hospital.name,
                detail: t("ops.dispatch.eta", {
                  minutes: Math.max(1, Math.round(hospital.eta_s / 60)),
                }),
                ready: true,
              }
            : undefined
        }
        className="h-[17rem] overflow-hidden rounded-[10px] border-[0.8px] border-brand-500"
      />
      <div className="flex flex-wrap gap-2">
        <a
          href={geoUri(incident.lat, incident.lon, incident.short_code)}
          className={cn(buttonVariants({ variant: "outline", size: "xs" }))}
        >
          <NavigationIcon aria-hidden />
          {t("respond.detail.openMap")}
        </a>
        <a
          href={osmUrl(incident.lat, incident.lon)}
          target="_blank"
          rel="noopener noreferrer"
          className={cn(buttonVariants({ variant: "secondary", size: "xs" }))}
        >
          <ExternalLinkIcon aria-hidden />
          {t("respond.detail.openOsm")}
        </a>
      </div>
    </section>
  );
}

/** Empty state of the Progress and Triage tabs when no mission is assigned. */
export function NoMission() {
  const { t } = useTranslation();
  return (
    <p className="rounded-xl border border-dashed border-brand-200 bg-white p-6 text-center text-body-sm text-ink-muted">
      {t("respond.noActive")}
    </p>
  );
}
