import { Link, useParams } from "@tanstack/react-router";
import {
  ArrowLeftIcon,
  CircleCheckIcon,
  CircleXIcon,
  ShieldCheckIcon,
  TriangleAlertIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { AiSourceTag, type AiSource } from "@/components/incident/ai-source-tag";
import { confidenceOf } from "@/components/incident/ai-confidence";
import { AiStatusBadge } from "@/components/incident/ai-status";
import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { SimulatedLabel } from "@/components/incident/simulated-label";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, useLabel } from "@/lib/format";
import { useSession } from "@/lib/auth-store";

import { EvidencePanel } from "./evidence-panel";
import { IncidentActions } from "./incident-actions";
import {
  ApiError,
  useCameras,
  useIncident,
  useIntegrity,
  type IncidentDetail,
} from "./incident-queries";
import { locationText } from "./incident-format";

const DISPATCHERS = new Set(["operator", "supervisor", "admin"]);

/** A finding is a string today and `{statement, basis, frame_ids}` once the verifier cites frames. */
type FindingLike = string | { statement: string; basis?: string; frame_ids?: number[] };

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-body-lg font-bold">{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">{children}</CardContent>
    </Card>
  );
}

function Banner({ children }: { children: ReactNode }) {
  return (
    <p
      role="status"
      className="flex items-start gap-2 rounded-lg border border-dashed border-foreground/40 bg-muted px-4 py-3 text-body-sm"
    >
      <TriangleAlertIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

function Signals({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const entries = Object.entries(incident.ai_signals);
  if (entries.length === 0) return <p className="text-muted-foreground">{t("ops.signals.none")}</p>;
  return (
    <ul className="flex flex-col gap-2">
      {entries.map(([name, value]) => (
        <li key={name} className="flex flex-wrap items-center gap-3">
          <AiSourceTag source={{ kind: "rule", id: name }} />
          <bdi dir="ltr" className="font-mono text-body-sm">
            {value}
          </bdi>
        </li>
      ))}
    </ul>
  );
}

function Verdict({ incident }: { incident: IncidentDetail }) {
  const { t, i18n } = useTranslation();
  const verifier = incident.verifier_result;
  const extra = verifier as { not_assessable?: string[] };
  const findings = verifier.findings as FindingLike[];
  const confidence = confidenceOf(verifier.yes_probability);
  const description = i18n.language === "ar" ? verifier.description_ar : verifier.description_fr;
  if (incident.ai_status === null) {
    return <p className="text-muted-foreground">{t("ops.verdict.notApplicable")}</p>;
  }
  if (!verifier.available) {
    return (
      <div className="flex flex-col gap-2">
        <AiStatusBadge aiStatus={incident.ai_status} verifier={verifier} />
        <p role="status" className="text-body-sm">
          {t("ops.degraded.verifier")}
        </p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <AiStatusBadge aiStatus={incident.ai_status} verifier={verifier} />
        {verifier.model ? <AiSourceTag source={{ kind: "model", id: verifier.model }} /> : null}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-body-sm">
        <dt className="text-muted-foreground">{t("ops.verdict.label")}</dt>
        <dd>
          {verifier.collision_visible
            ? t(`ops.verdict.${verifier.collision_visible as "yes" | "no" | "cannot_judge"}`)
            : "—"}
        </dd>
        <dt className="text-muted-foreground">{t("ops.confidence.label")}</dt>
        <dd>{confidence ? t(`ops.confidence.${confidence}`) : "—"}</dd>
      </dl>
      {description ? <p className="text-body-sm">{description}</p> : null}
      <div>
        <h3 className="text-body-sm font-bold">{t("ops.verdict.findings")}</h3>
        {findings.length === 0 ? (
          <p className="text-body-sm text-muted-foreground">{t("ops.verdict.noFindings")}</p>
        ) : (
          <ul className="list-disc ps-5 text-body-sm">
            {findings.map((finding, index) => {
              const item = typeof finding === "string" ? { statement: finding } : finding;
              const frames = "frame_ids" in item ? (item.frame_ids ?? []) : [];
              return (
                <li key={index}>
                  {item.statement}
                  {frames.length > 0 ? (
                    <span className="ms-2 text-muted-foreground">
                      {t("ops.verdict.frames", { frames: frames.join(", ") })}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {(extra.not_assessable ?? []).length > 0 ? (
        <div>
          <h3 className="text-body-sm font-bold">{t("ops.verdict.notAssessable")}</h3>
          <ul className="list-disc ps-5 text-body-sm">
            {(extra.not_assessable ?? []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function PrioritySection({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const label = useLabel();
  const model = incident.verifier_result.model;
  const sourceOf = (id: string): AiSource => ({ kind: id === model ? "model" : "rule", id });
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <PriorityBadge level={incident.priority as PriorityLevel} />
        {incident.to_assess ? <Badge variant="outline">{t("ops.flags.to_assess")}</Badge> : null}
        {incident.mass_casualty ? (
          <Badge variant="outline">{t("ops.flags.mass_casualty")}</Badge>
        ) : null}
        {incident.needs_extrication ? (
          <Badge variant="outline">{t("ops.flags.needs_extrication")}</Badge>
        ) : null}
        {incident.quality_flags.map((flag) => (
          <Badge key={flag} variant="outline">
            {label(`ops.quality.${flag}`, flag)}
          </Badge>
        ))}
      </div>
      <ul className="flex flex-col gap-2">
        {incident.priority_reasons.map((reason, index) => (
          <li key={index} className="flex flex-wrap items-center gap-2 text-body-sm">
            <span className="font-mono font-bold">P{reason.level}</span>
            <span>{reason.detail}</span>
            <AiSourceTag source={sourceOf(reason.source)} />
          </li>
        ))}
      </ul>
    </>
  );
}

function eventSummary(
  event: IncidentDetail["events"][number],
  label: (k: string, f: string) => string,
) {
  const p = event.payload as Record<string, unknown>;
  if (event.kind === "status_changed" && typeof p.to === "string") {
    const reason =
      typeof p.reason === "string" ? ` (${label(`ops.reject.${p.reason}`, p.reason)})` : "";
    return `${label(`status.${p.to}`, p.to)}${reason}`;
  }
  return "";
}

function Timeline({ incident }: { incident: IncidentDetail }) {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  return (
    <ol aria-label={t("timeline.label")} className="flex flex-col gap-3">
      {incident.events.map((event) => (
        <li key={event.id} className="flex flex-col text-body-sm">
          <span className="font-medium">
            {label(`ops.event.${event.kind}`, event.kind)}
            {eventSummary(event, label) ? ` · ${eventSummary(event, label)}` : ""}
          </span>
          <span className="text-body-xs text-muted-foreground">
            {formatDateTime(event.ts, i18n.language)} · {event.actor_name ?? t("ops.event.system")}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Casualties({ incident }: { incident: IncidentDetail }) {
  const { t, i18n } = useTranslation();
  if (incident.casualties.length === 0) {
    return <p className="text-muted-foreground">{t("ops.casualties.none")}</p>;
  }
  const cols = ["tag", "avpu", "resp", "pulse", "spo2", "bleeding", "time"] as const;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-start text-body-sm">
        <caption className="sr-only">{t("ops.casualties.title")}</caption>
        <thead className="text-body-xs text-muted-foreground">
          <tr>
            {cols.map((col) => (
              <th key={col} scope="col" className="px-2 py-1 text-start font-medium">
                {t(`ops.casualties.${col}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {incident.casualties.map((c) => (
            <tr key={c.id} className="border-t border-border">
              <td className="px-2 py-1 font-medium">{t(`ops.triage.${c.triage_tag}`)}</td>
              <td className="px-2 py-1">{c.avpu ?? "—"}</td>
              <td className="px-2 py-1">{c.resp_rate ?? "—"}</td>
              <td className="px-2 py-1">{c.pulse ?? "—"}</td>
              <td className="px-2 py-1">{c.spo2 ?? "—"}</td>
              <td className="px-2 py-1">
                {c.bleeding === null || c.bleeding === undefined
                  ? "—"
                  : c.bleeding
                    ? t("ops.yes")
                    : t("ops.no")}
              </td>
              <td className="px-2 py-1 whitespace-nowrap">{formatDateTime(c.at, i18n.language)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IntegrityCheck({ id }: { id: string }) {
  const { t } = useTranslation();
  const check = useIntegrity(id);
  const result = check.data;
  return (
    <div className="flex flex-col gap-3">
      <Button
        variant="outline"
        className="w-fit"
        disabled={check.isPending}
        onClick={() => check.mutate()}
      >
        <ShieldCheckIcon aria-hidden />
        {t("ops.integrity.verify")}
      </Button>
      {check.isError ? (
        <p role="alert" className="text-body-sm text-danger">
          {check.error instanceof ApiError && check.error.status === 403
            ? t("ops.errors.forbidden")
            : t("ops.errors.generic")}
        </p>
      ) : null}
      {result ? (
        <div role="status" className="flex flex-col gap-2 text-body-sm">
          <p className="flex items-center gap-2 font-bold">
            {result.status === "valid" ? (
              <CircleCheckIcon aria-hidden className="size-5 text-success" />
            ) : (
              <CircleXIcon aria-hidden className="size-5 text-danger" />
            )}
            {t(`ops.integrity.${result.status}`)}
          </p>
          <p className="text-muted-foreground">
            {t("ops.integrity.checked", {
              events: result.events_checked,
              files: result.files_checked,
            })}
          </p>
          {result.failures.length > 0 ? (
            <ul className="list-disc ps-5">
              {result.failures.map((failure) => (
                <li key={`${failure.kind}-${failure.ref}`}>
                  <bdi dir="ltr" className="font-mono">
                    {failure.ref}
                  </bdi>{" "}
                  — {failure.detail}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** Incident detail: evidence, reasons behind every AI value, timeline, casualties (FR-MAP-003). */
export function IncidentDetailPage() {
  const { t } = useTranslation();
  const label = useLabel();
  const { incidentId } = useParams({ strict: false });
  const role = useSession()?.user.role;
  const query = useIncident(incidentId ?? "");
  const cameras = useCameras();
  const back = (
    <Button asChild variant="ghost" className="w-fit">
      <Link to="/ops">
        <ArrowLeftIcon aria-hidden className="rtl:rotate-180" />
        {t("ops.detail.back")}
      </Link>
    </Button>
  );

  if (query.isPending) return <Skeleton className="h-64 w-full" />;
  if (query.isError || !query.data) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="flex flex-col gap-3">
        {back}
        <p role="alert">{missing ? t("ops.detail.notFound") : t("ops.console.loadError")}</p>
      </div>
    );
  }

  const incident = query.data;
  const camera = cameras.data?.find((c) => c.id === incident.camera_id);
  const verifier = incident.verifier_result;
  const unavailable = incident.ai_status !== null && !verifier.available;
  const contradiction = verifier.available && verifier.collision_visible === "no";

  return (
    <div className="flex flex-col gap-4">
      {back}
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-display-sm font-bold">
            <bdi dir="ltr" className="font-mono">
              {incident.short_code}
            </bdi>
          </h1>
          <PriorityBadge level={incident.priority as PriorityLevel} />
          <Badge variant="secondary">{t(`status.${incident.status}`)}</Badge>
          {camera?.simulated ? <SimulatedLabel /> : null}
        </div>
        <p className="text-body-md text-muted-foreground">
          {label(`ops.type.${incident.type}`, incident.type)} ·{" "}
          {label(`ops.source.${incident.source}`, incident.source)} · {locationText(incident)} ·{" "}
          {t("ops.detail.reports", { count: incident.report_count })}
        </p>
        {incident.status === "rejected" && incident.reject_reason ? (
          <p className="text-body-sm">
            {t("ops.detail.rejectedFor", { reason: t(`ops.reject.${incident.reject_reason}`) })}
          </p>
        ) : null}
        {incident.status === "merged" && incident.merged_into ? (
          <p className="text-body-sm">
            {t("ops.detail.mergedInto")}{" "}
            <Link
              to="/ops/incidents/$incidentId"
              params={{ incidentId: incident.merged_into }}
              className="underline"
            >
              {t("ops.detail.openTarget")}
            </Link>
          </p>
        ) : null}
        {role && DISPATCHERS.has(role) ? <IncidentActions incident={incident} /> : null}
      </header>

      {unavailable ? <Banner>{t("ops.degraded.verifier")}</Banner> : null}
      {contradiction ? <Banner>{t("ops.degraded.contradiction")}</Banner> : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="flex flex-col gap-4">
          <Section title={t("ops.detail.evidence")}>
            <EvidencePanel incident={incident} />
          </Section>
          <Section title={t("ops.detail.rules")}>
            <Signals incident={incident} />
          </Section>
          <Section title={t("ops.detail.ai")}>
            <Verdict incident={incident} />
          </Section>
        </div>
        <div className="flex flex-col gap-4">
          <Section title={t("ops.detail.priority")}>
            <PrioritySection incident={incident} />
          </Section>
          <Section title={t("ops.detail.timeline")}>
            <Timeline incident={incident} />
          </Section>
          <Section title={t("ops.casualties.title")}>
            <Casualties incident={incident} />
          </Section>
          <Section title={t("ops.integrity.title")}>
            <IntegrityCheck id={incident.id} />
          </Section>
        </div>
      </div>
    </div>
  );
}
