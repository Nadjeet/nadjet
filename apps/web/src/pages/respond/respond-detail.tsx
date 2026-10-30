import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeftIcon, ExternalLinkIcon, NavigationIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { AiSourceTag } from "@/components/incident/ai-source-tag";
import { AiStatusBadge } from "@/components/incident/ai-status";
import { EvidencePanel } from "@/components/incident/evidence-panel";
import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLabel } from "@/lib/format";
import { locationText } from "@/lib/incident-format";
import { ApiError, useDispatches, useIncident, type IncidentDetail } from "@/lib/incident-queries";
import { geoUri, osmUrl } from "@/lib/sms-codes";

import { OfflineBanner } from "./app-controls";
import { PendingActions } from "./pending-actions";
import { StatusActions } from "./status-actions";
import { TriageForm } from "./triage-form";

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-4">
      <h2 className="text-body-md font-bold">{title}</h2>
      {children}
    </section>
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
  if (!hospital) return <p className="text-muted-foreground">{t("respond.detail.noHospital")}</p>;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-body-md font-medium">{hospital.name}</p>
      <p className="text-body-sm text-muted-foreground">
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
    return <p className="text-muted-foreground">{t("respond.detail.noAi")}</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <AiStatusBadge aiStatus={incident.ai_status} verifier={verifier} />
        {verifier.model ? <AiSourceTag source={{ kind: "model", id: verifier.model }} /> : null}
      </div>
      <p className="text-body-md">{text}</p>
      <p className="text-body-xs text-muted-foreground">{t("respond.detail.aiNote")}</p>
    </div>
  );
}

/** One assigned incident: location, hospital, AI description, evidence, status and triage. */
export function RespondDetail() {
  const { t } = useTranslation();
  const label = useLabel();
  const { incidentId } = useParams({ strict: false });
  const query = useIncident(incidentId ?? "");
  const back = (
    <Button asChild variant="ghost" className="w-fit">
      <Link to="/respond">
        <ArrowLeftIcon aria-hidden className="rtl:rotate-180" />
        {t("respond.detail.back")}
      </Link>
    </Button>
  );

  if (query.isPending) return <Skeleton className="h-64 w-full" />;
  if (query.isError || !query.data) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="flex flex-col gap-3">
        {back}
        <OfflineBanner />
        <p role="alert">{missing ? t("respond.detail.notFound") : t("respond.list.loadError")}</p>
      </div>
    );
  }
  const incident = query.data;
  const place = locationText(incident);
  return (
    <div className="flex flex-col gap-4">
      {back}
      <OfflineBanner />
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-display-xs font-bold">
            <bdi dir="ltr" className="font-mono">
              {incident.short_code}
            </bdi>
          </h1>
          <PriorityBadge level={incident.priority as PriorityLevel} />
          <Badge variant="secondary">{t(`status.${incident.status}`)}</Badge>
        </div>
        <p className="text-body-md">
          {label(`ops.type.${incident.type}`, incident.type)} · {place}
        </p>
        {incident.trapped_reported ? (
          <Badge variant="outline">{t("respond.detail.trapped")}</Badge>
        ) : null}
        {incident.people_reported !== null ? (
          <p className="text-body-sm text-muted-foreground">
            {t("respond.detail.people", { count: incident.people_reported })}
          </p>
        ) : null}
      </header>

      <StatusActions incident={incident} />
      <PendingActions incidentId={incident.id} />

      <Card title={t("respond.detail.where")}>
        <p className="text-body-md">{place}</p>
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
      <Card title={t("respond.detail.evidence")}>
        <EvidencePanel incident={incident} />
      </Card>
      <TriageForm incident={incident} />
    </div>
  );
}
