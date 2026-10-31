import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeftIcon, ExternalLinkIcon, NavigationIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { AiSourceTag } from "@/components/incident/ai-source-tag";
import { AiStatusBadge } from "@/components/incident/ai-status";
import { EvidencePanel } from "@/components/incident/evidence-panel";
import { stepsFromEvents, type TimelineStatus } from "@/components/incident/lifecycle";
import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { StatusTimeline } from "@/components/incident/status-timeline";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLabel } from "@/lib/format";
import { locationText } from "@/lib/incident-format";
import { ApiError, useDispatches, useIncident, type IncidentDetail } from "@/lib/incident-queries";
import { geoUri, osmUrl } from "@/lib/sms-codes";
import { formatTime } from "@/lib/format";
import { RouteMap } from "@/pages/ops/incident/route-map";

import { OfflineBanner } from "./app-controls";
import { PendingActions } from "./pending-actions";
import { StatusActions } from "./status-actions";
import { TriageForm } from "./triage-form";

/** Figma app section: a plain heading over a white card. */
function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-body-xl font-medium text-ink">{title}</h2>
      <div className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-4 shadow-card">
        {children}
      </div>
    </section>
  );
}

/** Scene and the hospital route, drawn from the active hospital dispatch (FR-DSP-004). */
function MissionMap({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const dispatches = useDispatches(incident.id, true);
  const hospital = dispatches.data?.find((d) => d.kind === "hospital");
  if (incident.lat === null || incident.lon === null) return null;
  return (
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
      className="h-72 overflow-hidden rounded-xl border border-border"
    />
  );
}

/** Where to go, with links that open the phone's map app or OpenStreetMap (no Google). */
function MapLinks({ lat, lon, name }: { lat: number; lon: number; name: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-2">
      <Button asChild size="sm">
        <a href={geoUri(lat, lon, name)}>
          <NavigationIcon aria-hidden />
          {t("respond.detail.openMap")}
        </a>
      </Button>
      <Button asChild size="sm" variant="outline">
        <a href={osmUrl(lat, lon)} target="_blank" rel="noopener noreferrer">
          <ExternalLinkIcon aria-hidden />
          {t("respond.detail.openOsm")}
        </a>
      </Button>
    </div>
  );
}

function Hospital({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const dispatches = useDispatches(incident.id, true);
  const hospital = dispatches.data?.find((d) => d.kind === "hospital");
  if (dispatches.isPending) return <Skeleton className="h-10 w-full" />;
  if (!hospital) return <p className="text-ink-muted">{t("respond.detail.noHospital")}</p>;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-body-md font-medium">{hospital.name}</p>
      <p className="text-body-sm text-ink-muted">
        {t("ops.dispatch.eta", { minutes: Math.max(1, Math.round(hospital.eta_s / 60)) })} ·{" "}
        {t("ops.dispatch.distance", { km: (hospital.distance_m / 1000).toFixed(1) })}
      </p>
      <MapLinks lat={hospital.lat} lon={hospital.lon} name={hospital.name} />
    </div>
  );
}

/** What the AI wrote about the video, with its source and an explicit uncertain mark. */
function AiDescription({ incident }: { incident: IncidentDetail }) {
  const { t, i18n } = useTranslation();
  const verifier = incident.verifier_result;
  const text = i18n.language === "ar" ? verifier.description_ar : verifier.description_fr;
  if (!verifier.available || !text) {
    return <p className="text-ink-muted">{t("respond.detail.noAi")}</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <AiStatusBadge aiStatus={incident.ai_status} verifier={verifier} />
        {verifier.model ? <AiSourceTag source={{ kind: "model", id: verifier.model }} /> : null}
      </div>
      <p className="text-body-md">{text}</p>
      <p className="text-body-xs text-ink-muted">{t("respond.detail.aiNote")}</p>
    </div>
  );
}

/**
 * Figma "mission" screen: back + "Mission details" header, a summary card with the next
 * status action, the mission progress stepper, the map with the hospital route, the AI
 * description, the incident visual and the triage form (FR-RSP-001..004).
 */
export function RespondDetail() {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  const { incidentId } = useParams({ strict: false });
  const query = useIncident(incidentId ?? "");
  const header = (title: string) => (
    <div className="flex items-center gap-3">
      <Button asChild variant="neutral" size="icon" className="rounded-full">
        <Link to="/respond" aria-label={t("respond.detail.back")}>
          <ArrowLeftIcon aria-hidden className="rtl:rotate-180" />
        </Link>
      </Button>
      <div className="flex min-w-0 flex-1 flex-col leading-tight">
        <span className="text-body-xs font-medium tracking-[0.5px] text-ink-muted uppercase">
          {t("respond.detail.missionLabel")}
        </span>
        <h1 className="truncate text-body-xl font-semibold text-ink">{title}</h1>
      </div>
    </div>
  );

  if (query.isPending) return <Skeleton className="h-64 w-full" />;
  if (query.isError || !query.data) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="flex flex-col gap-3">
        {header(t("respond.detail.missionLabel"))}
        <OfflineBanner />
        <p role="alert">{missing ? t("respond.detail.notFound") : t("respond.list.loadError")}</p>
      </div>
    );
  }
  const incident = query.data;
  const place = locationText(incident);
  const steps = stepsFromEvents(incident.events);
  const current = (steps.at(-1)?.status ?? "dispatched") as TimelineStatus;
  return (
    <div className="flex flex-col gap-6">
      {header(t("respond.detail.mission", { code: incident.short_code }))}
      <OfflineBanner />

      <section className="flex flex-col gap-3 rounded-2xl border-2 border-brand-200 bg-card p-4 shadow-card">
        <div className="flex flex-wrap items-center gap-2">
          <PriorityBadge level={incident.priority as PriorityLevel} compact />
          <span className="text-body-md font-semibold text-ink">
            {label(`ops.type.${incident.type}`, incident.type)}
          </span>
          <Badge variant="secondary">{t(`status.${incident.status}`)}</Badge>
          <span className="ms-auto text-body-xs text-primary">
            {formatTime(incident.event_time, i18n.language)}
          </span>
        </div>
        <p className="text-body-sm text-ink-muted">{place}</p>
        {incident.trapped_reported ? (
          <Badge variant="destructive">{t("respond.detail.trapped")}</Badge>
        ) : null}
        {incident.people_reported !== null ? (
          <p className="text-body-sm text-ink-body">
            {t("respond.detail.people", { count: incident.people_reported })}
          </p>
        ) : null}
        <StatusActions incident={incident} />
        <PendingActions incidentId={incident.id} />
      </section>

      <Card title={t("respond.detail.progress")}>
        <StatusTimeline steps={steps} current={current} from="dispatched" />
      </Card>
      <Card title={t("respond.detail.map")}>
        <MissionMap incident={incident} />
        <p className="text-body-sm text-ink-body">{place}</p>
        {incident.lat !== null && incident.lon !== null ? (
          <MapLinks lat={incident.lat} lon={incident.lon} name={incident.short_code} />
        ) : null}
      </Card>
      <Card title={t("respond.detail.hospital")}>
        <Hospital incident={incident} />
      </Card>
      <Card title={t("respond.detail.ai")}>
        <AiDescription incident={incident} />
      </Card>
      <Card title={t("respond.detail.visual")}>
        <EvidencePanel incident={incident} />
      </Card>
      <TriageForm incident={incident} />
    </div>
  );
}
