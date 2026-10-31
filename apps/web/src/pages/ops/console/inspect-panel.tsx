import { Link } from "@tanstack/react-router";
import { CameraIcon, EyeIcon, ShieldCheckIcon, VideoIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { confidenceOf } from "@/components/incident/ai-confidence";
import { AiSourceTag } from "@/components/incident/ai-source-tag";
import { AiStatusBadge } from "@/components/incident/ai-status";
import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { LiveStream } from "@/components/stream/live-stream";
import { buttonVariants } from "@/components/ui/button";
import { formatAge, useLabel } from "@/lib/format";
import { locationText } from "@/lib/incident-format";
import type { Camera, Incident } from "@/lib/incident-queries";
import { cn } from "@/lib/utils";

import { streamUrls, type View } from "../camera-status";
import { ViewSwitch } from "@/components/stream/view-switch";

/**
 * Figma "Inspect Incident" bento: the selected incident's camera, AI verdict with its model,
 * the priority factors and the way into the full review. Decision support only: confirming
 * and dispatching happen on the incident page (human gate, NFR-SAFE-001).
 */
export function InspectPanel({
  incident,
  cameras,
}: {
  incident: Incident | null;
  cameras: Camera[];
}) {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  const [view, setView] = useState<View>("annotated");
  if (!incident) {
    return (
      <div className="grid h-full place-items-center rounded-lg border border-dashed border-border p-6 text-center text-body-sm text-ink-muted">
        {t("ops.console.inspectEmpty")}
      </div>
    );
  }
  const camera = cameras.find((c) => c.id === incident.camera_id);
  const verifier = incident.verifier_result;
  const confidence = confidenceOf(verifier.yes_probability);
  const description = i18n.language === "ar" ? verifier.description_ar : verifier.description_fr;

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-start justify-between gap-3 border-b border-border pb-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-body-lg font-semibold text-ink">
            <span className="font-mono">{incident.short_code}</span>
            <PriorityBadge level={incident.priority as PriorityLevel} compact />
          </p>
          <p className="truncate text-body-sm text-ink-muted">{locationText(incident)}</p>
        </div>
        <span className="shrink-0 text-body-xs text-primary">
          {formatAge(incident.event_time, i18n.language)}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-body-sm text-ink">
            <VideoIcon aria-hidden className="size-4 text-primary" />
            {t("ops.console.liveStream")}
          </p>
          {camera ? <ViewSwitch view={view} onChange={setView} /> : null}
        </div>
        {camera ? (
          <LiveStream
            key={`${camera.id}-${view}`}
            urls={streamUrls(camera.stream, view)}
            label={t("cameras.videoOf", { name: camera.name, view: t(`cameras.${view}`) })}
            className="aspect-video rounded-lg"
          />
        ) : (
          <p className="rounded-lg bg-surface-soft p-3 text-body-xs text-ink-muted">
            {t("ops.console.noCamera")}
          </p>
        )}
      </div>

      {incident.ai_status !== null ? (
        <div className="flex flex-col gap-2 rounded-lg border border-border p-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="flex items-center gap-2 text-body-sm font-medium text-ink">
              <CameraIcon aria-hidden className="size-4 text-primary" />
              {label(`ops.type.${incident.type}`, incident.type)}
            </p>
            {verifier.available && confidence ? (
              <span className="rounded-sm bg-success-soft px-1.5 py-0.5 text-body-xs font-medium text-success">
                {t(`ops.confidence.${confidence}`)}
              </span>
            ) : null}
          </div>
          <AiStatusBadge
            aiStatus={incident.ai_status}
            verifier={verifier}
            className="text-body-xs"
          />
          {description ? <p className="text-body-sm text-ink-body">{description}</p> : null}
          {verifier.model ? <AiSourceTag source={{ kind: "model", id: verifier.model }} /> : null}
        </div>
      ) : null}

      {incident.priority_reasons.length ? (
        <div className="flex flex-col gap-2">
          <p className="text-body-xs font-medium tracking-[0.5px] text-ink-muted uppercase">
            {t("ops.console.factors")}
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {incident.priority_reasons.map((reason) => (
              <li
                key={`${reason.rule}-${reason.level}`}
                className={cn(
                  "rounded-md px-2 py-1 text-body-xs",
                  reason.level === 1
                    ? "bg-danger text-white"
                    : "border border-border bg-surface-soft text-ink-body",
                )}
              >
                {reason.detail}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-auto flex flex-col gap-2 pt-2">
        <Link
          to="/ops/incidents/$incidentId"
          params={{ incidentId: incident.id }}
          className={cn(buttonVariants(), "w-full")}
        >
          <ShieldCheckIcon aria-hidden />
          {t("ops.console.openReview")}
        </Link>
        <Link
          to="/ops/incidents/$incidentId"
          params={{ incidentId: incident.id }}
          hash="evidence"
          className={cn(buttonVariants({ variant: "neutral", size: "sm" }), "w-full")}
        >
          <EyeIcon aria-hidden />
          {t("ops.console.details")}
        </Link>
      </div>
    </div>
  );
}
