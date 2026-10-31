import { Link } from "@tanstack/react-router";
import {
  BanIcon,
  CameraIcon,
  CarFrontIcon,
  EyeIcon,
  ShieldCheckIcon,
  VideoIcon,
  XIcon,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { confidenceOf } from "@/components/incident/ai-confidence";
import { AiSourceTag } from "@/components/incident/ai-source-tag";
import { AiStatusBadge } from "@/components/incident/ai-status";
import { LiveStream } from "@/components/stream/live-stream";
import { ViewSwitch } from "@/components/stream/view-switch";
import { Button, buttonVariants } from "@/components/ui/button";
import { formatAge, useLabel } from "@/lib/format";
import { locationText } from "@/lib/incident-format";
import type { Camera, Incident } from "@/lib/incident-queries";
import { cn } from "@/lib/utils";

import { streamUrls, type View } from "../camera-status";
import { RejectDialog } from "../incident/incident-actions";

const CAN_DECIDE = new Set(["candidate", "verified"]);

/**
 * Figma "Quick Inspection & Verification Panel" (node 75:6580): header with the age, the live
 * camera tile with its Raw / Annotated switch, the AI finding card with its confidence chip,
 * the factors, then "Dispatch Now" (gradient) over "Reject" and "Details". Decision support
 * only: confirming and dispatching happen on the incident page (human gate, NFR-SAFE-001).
 */
export function InspectPanel({
  incident,
  cameras,
  canAct,
}: {
  incident: Incident | null;
  cameras: Camera[];
  canAct: boolean;
}) {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  const [view, setView] = useState<View>("annotated");
  const [rejecting, setRejecting] = useState(false);
  if (!incident) {
    return (
      <div className="grid h-full place-items-center rounded-lg border border-dashed border-line p-6 text-center text-body-sm text-ink-muted">
        {t("ops.console.inspectEmpty")}
      </div>
    );
  }
  const camera = cameras.find((c) => c.id === incident.camera_id);
  const verifier = incident.verifier_result;
  const confidence = confidenceOf(verifier.yes_probability);
  const description = i18n.language === "ar" ? verifier.description_ar : verifier.description_fr;
  const vehicles = incident.ai_signals.vehicle_count;

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-col gap-1 border-b border-line pb-4">
        <div className="flex items-start justify-between gap-3">
          <h2 id="inspect-title" className="text-body-md font-medium text-ink">
            {t("ops.console.inspect")}
          </h2>
          <span className="shrink-0 text-body-xs text-brand-500">
            {formatAge(incident.event_time, i18n.language)}
          </span>
        </div>
        <p className="truncate text-body-xs text-ink-muted">
          <bdi dir="ltr" className="font-medium text-ink">
            INC-{incident.short_code}
          </bdi>{" "}
          · {locationText(incident)}
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-body-xs text-ink">
            <VideoIcon aria-hidden className="size-4 text-brand-500" />
            {t("ops.console.liveStream")}
          </p>
          {camera ? <ViewSwitch view={view} onChange={setView} /> : null}
        </div>
        {camera ? (
          <LiveStream
            key={`${camera.id}-${view}`}
            urls={streamUrls(camera.stream, view)}
            label={t("cameras.videoOf", { name: camera.name, view: t(`cameras.${view}`) })}
            className="aspect-[245/172] rounded-md"
          />
        ) : (
          <p className="rounded-md bg-surface-soft p-3 text-body-xs text-ink-muted">
            {t("ops.console.noCamera")}
          </p>
        )}
      </div>

      {incident.ai_status !== null ? (
        <div className="flex flex-col gap-2 rounded-lg border border-line bg-white p-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="flex items-center gap-2 text-body-xs text-ink">
              <CameraIcon aria-hidden className="size-[18px] text-brand-500" />
              {label(`ops.type.${incident.type}`, incident.type)}
            </p>
            {verifier.available && confidence ? (
              <span className="rounded-md bg-success-chip px-1.5 py-0.5 text-[0.625rem] text-white">
                {t(`ops.confidence.${confidence}`)}
              </span>
            ) : (
              <AiStatusBadge
                aiStatus={incident.ai_status}
                verifier={verifier}
                className="text-[0.625rem]"
              />
            )}
          </div>
          {description ? (
            <p className="line-clamp-4 text-body-xs text-ink-body">{description}</p>
          ) : null}
          {verifier.model ? <AiSourceTag source={{ kind: "model", id: verifier.model }} /> : null}
        </div>
      ) : null}

      {incident.priority_reasons.length || vehicles ? (
        <div className="flex flex-col gap-2">
          <p className="text-body-xs font-semibold tracking-[0.5px] text-brand-900 uppercase">
            {t("ops.console.factors")}
          </p>
          <ul className="flex flex-wrap gap-2">
            {incident.priority_reasons.map((reason) => (
              <li
                key={`${reason.rule}-${reason.level}`}
                className={cn(
                  "inline-flex items-center gap-1 rounded-md px-2 py-1 text-[0.6875rem]",
                  reason.level === 1 ? "bg-danger text-white" : "bg-surface-strong text-ink-body",
                )}
              >
                {reason.level === 1 ? <BanIcon aria-hidden className="size-3" /> : null}
                {reason.detail}
              </li>
            ))}
            {vehicles ? (
              <li className="inline-flex items-center gap-1 rounded-md bg-surface-strong px-2 py-1 text-[0.6875rem] text-ink-body">
                <CarFrontIcon aria-hidden className="size-3" />
                {t("ops.signals.vehicles", { count: vehicles })}
              </li>
            ) : null}
          </ul>
        </div>
      ) : null}

      <div className="mt-auto flex flex-col gap-2 pt-2">
        <Link
          to="/ops/incidents/$incidentId"
          params={{ incidentId: incident.id }}
          hash="dispatch"
          className={cn(buttonVariants({ variant: "gradient" }), "w-full")}
        >
          <ShieldCheckIcon aria-hidden />
          {incident.status === "candidate"
            ? t("ops.console.reviewNow")
            : t("ops.console.dispatchNow")}
        </Link>
        <div className="grid grid-cols-2 gap-2">
          <Button
            variant="neutral"
            size="sm"
            disabled={!canAct || !CAN_DECIDE.has(incident.status)}
            onClick={() => setRejecting(true)}
          >
            <XIcon aria-hidden />
            {t("ops.console.reject")}
          </Button>
          <Link
            to="/ops/incidents/$incidentId"
            params={{ incidentId: incident.id }}
            hash="evidence"
            className={buttonVariants({ variant: "neutral", size: "sm" })}
          >
            <EyeIcon aria-hidden />
            {t("ops.console.details")}
          </Link>
        </div>
      </div>
      <RejectDialog incident={incident} open={rejecting} onOpenChange={setRejecting} />
    </div>
  );
}
