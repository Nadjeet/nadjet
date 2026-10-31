import { useParams } from "@tanstack/react-router";
import { BuildingIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AiSourceTag } from "@/components/incident/ai-source-tag";
import { AiStatusBadge } from "@/components/incident/ai-status";
import { EvidencePanel } from "@/components/incident/evidence-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, useDispatches, useIncident, type IncidentDetail } from "@/lib/incident-queries";

import { OfflineBanner } from "./app-controls";
import { MissionCard, MissionHeader, MissionMap, MissionProgress, SectionTitle } from "./mission";
import { PendingActions } from "./pending-actions";
import { TriageForm } from "./triage-form";

/** Receiving hospital, styled as the Figma hospital card (brand tile, blue border). */
function Hospital({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const dispatches = useDispatches(incident.id, true);
  const hospital = dispatches.data?.find((d) => d.kind === "hospital");
  return (
    <section aria-labelledby="mission-hospital" className="flex flex-col gap-3">
      <SectionTitle id="mission-hospital">{t("respond.detail.hospital")}</SectionTitle>
      {dispatches.isPending ? (
        <Skeleton className="h-16 w-full rounded-xl" />
      ) : hospital ? (
        <div className="flex items-center gap-3 rounded-xl border border-brand-indigo bg-white p-3 shadow-soft">
          <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand-100 text-brand-500">
            <BuildingIcon aria-hidden className="size-5" />
          </span>
          <div className="flex min-w-0 flex-col">
            <p className="truncate text-body-sm font-medium text-ink">{hospital.name}</p>
            <p className="text-body-xs text-success-text">
              {t("ops.dispatch.eta", { minutes: Math.max(1, Math.round(hospital.eta_s / 60)) })} ·{" "}
              {t("ops.dispatch.distance", { km: (hospital.distance_m / 1000).toFixed(1) })}
            </p>
          </div>
        </div>
      ) : (
        <p className="text-body-sm text-ink-muted">{t("respond.detail.noHospital")}</p>
      )}
    </section>
  );
}

/** What the AI wrote about the video, with its source and an explicit uncertain mark. */
function AiDescription({ incident }: { incident: IncidentDetail }) {
  const { t, i18n } = useTranslation();
  const verifier = incident.verifier_result;
  const text = i18n.language === "ar" ? verifier.description_ar : verifier.description_fr;
  return (
    <section aria-labelledby="mission-ai" className="flex flex-col gap-3">
      <SectionTitle id="mission-ai">{t("respond.detail.ai")}</SectionTitle>
      <div className="flex flex-col gap-2 rounded-xl border border-line bg-white p-4 shadow-soft">
        {verifier.available && text ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <AiStatusBadge aiStatus={incident.ai_status} verifier={verifier} />
              {verifier.model ? (
                <AiSourceTag source={{ kind: "model", id: verifier.model }} />
              ) : null}
            </div>
            <p className="text-body-sm text-ink-body">{text}</p>
            <p className="text-body-xs text-ink-muted">{t("respond.detail.aiNote")}</p>
          </>
        ) : (
          <p className="text-body-sm text-ink-muted">{t("respond.detail.noAi")}</p>
        )}
      </div>
    </section>
  );
}

/**
 * Figma "mission" screen (node 75:7914): glass back button and "Mission details", the mission
 * card with the next status as the gradient button and the SMS fallback, the progress stepper,
 * the map with the hospital route, the incident visual (Raw / Annotated), then the AI text, the
 * hospital and the triage form (FR-RSP-001..004).
 */
export function RespondDetail() {
  const { t } = useTranslation();
  const { incidentId } = useParams({ strict: false });
  const query = useIncident(incidentId ?? "");

  if (query.isPending) return <Skeleton className="h-64 w-full rounded-xl" />;
  if (query.isError || !query.data) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="flex flex-col gap-3">
        <MissionHeader title={t("respond.detail.missionLabel")} />
        <OfflineBanner />
        <p role="alert">{missing ? t("respond.detail.notFound") : t("respond.list.loadError")}</p>
      </div>
    );
  }
  const incident = query.data;
  return (
    <div className="flex flex-col gap-6">
      <MissionHeader title={t("respond.detail.mission", { code: incident.short_code })} />
      <OfflineBanner />
      <MissionCard incident={incident} />
      <PendingActions incidentId={incident.id} />
      <MissionProgress incident={incident} />
      <MissionMap incident={incident} />
      <section aria-labelledby="mission-visual" className="flex flex-col gap-3">
        <SectionTitle id="mission-visual">{t("respond.detail.visual")}</SectionTitle>
        <EvidencePanel incident={incident} />
      </section>
      <AiDescription incident={incident} />
      <Hospital incident={incident} />
      <TriageForm incident={incident} />
    </div>
  );
}
