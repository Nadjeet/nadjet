import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CircleAlertIcon, TrashIcon, UploadIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import {
  TryError,
  checkClip,
  deleteJob,
  fetchStatus,
  followJob,
  isFinal,
  uploadClip,
  type TryJob,
} from "./try-data";

function formatSeconds(value: number) {
  return `${value.toFixed(1)} s`;
}

function Consent() {
  const { t } = useTranslation();
  return (
    <section
      aria-labelledby="try-consent"
      className="rounded-xl border border-border bg-card p-4 text-body-sm"
    >
      <h2 id="try-consent" className="font-bold">
        {t("pages.public.try.consent.title")}
      </h2>
      <p className="mt-1 text-muted-foreground">{t("pages.public.try.consent.body")}</p>
    </section>
  );
}

function Result({ job, onDelete }: { job: TryJob; onDelete: () => void }) {
  const { t, i18n } = useTranslation();
  const result = job.result;
  if (!result) return null;
  const incident = result.sandbox_incident;
  const timeline = result.timeline ?? [];
  const verdict = result.refine ?? result.scan;
  const description = i18n.language === "ar" ? verdict?.description_ar : verdict?.description_fr;
  return (
    <div className="flex flex-col gap-4">
      {!result.ai_available ? (
        <p
          role="alert"
          className="flex items-center gap-2 rounded-lg border border-danger p-3 font-medium text-danger dark:text-red-400"
        >
          <CircleAlertIcon aria-hidden className="size-4" />
          {t("pages.public.try.aiUnavailable")}
        </p>
      ) : null}
      {job.has_video ? (
        <video
          className="aspect-video w-full rounded-xl bg-black"
          controls
          src={`/api/public/try/jobs/${job.id}/video`}
          aria-label={t("pages.public.try.annotated")}
        />
      ) : null}
      <section className="rounded-xl border border-border bg-card p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-body-lg font-bold">{t("pages.public.try.incident")}</h2>
          <Badge variant="secondary">{t("pages.public.try.sandbox")}</Badge>
        </div>
        {incident ? (
          <dl className="mt-2 grid gap-1 text-body-sm">
            <div>
              <dt className="inline font-medium">{t("pages.public.try.status")}: </dt>
              <dd className="inline">{t(`ops.aiStatus.${incident.ai_status}`)}</dd>
            </div>
            <div>
              <dt className="inline font-medium">{t("pages.public.try.time")}: </dt>
              <dd className="inline">{formatSeconds(incident.event_time_s)}</dd>
            </div>
            <div>
              <dt className="inline font-medium">{t("pages.public.try.vehicles")}: </dt>
              <dd className="inline">{(incident.vehicles ?? []).length}</dd>
            </div>
            {description ? <p className="mt-1">{description}</p> : null}
          </dl>
        ) : (
          <p className="mt-2 text-body-sm text-muted-foreground">
            {result.ai_available
              ? t("pages.public.try.noCollision")
              : t("pages.public.try.noRuleCollision")}
          </p>
        )}
        {verdict?.findings?.length ? (
          <ul className="mt-2 list-disc ps-5 text-body-sm">
            {(verdict.findings ?? []).map((finding) => (
              <li key={`${finding.statement}-${(finding.frame_ids ?? []).join(",")}`}>
                {finding.statement}{" "}
                <bdi dir="ltr" className="text-muted-foreground">
                  ({t("pages.public.try.frames")} {(finding.frame_ids ?? []).join(", ")})
                </bdi>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
      <section className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-body-lg font-bold">{t("pages.public.try.timeline")}</h2>
        {timeline.length === 0 ? (
          <p className="mt-2 text-body-sm text-muted-foreground">
            {t("pages.public.try.timelineEmpty")}
          </p>
        ) : (
          <ol className="mt-2 flex flex-col gap-1 text-body-sm">
            {timeline.map((entry) => (
              <li key={`${entry.t}-${entry.kind}-${entry.label}`}>
                <bdi dir="ltr" className="font-medium">
                  {formatSeconds(entry.t)}
                </bdi>{" "}
                {entry.label} <span className="text-muted-foreground">({entry.source})</span>
              </li>
            ))}
          </ol>
        )}
      </section>
      <div>
        <Button type="button" variant="outline" onClick={onDelete}>
          <TrashIcon aria-hidden />
          {t("pages.public.try.delete")}
        </Button>
      </div>
    </div>
  );
}

export function TryPage() {
  const { t } = useTranslation();
  const status = useQuery({
    queryKey: ["try-status"],
    queryFn: fetchStatus,
    refetchInterval: 10_000,
  });
  const [error, setError] = useState<TryError | null>(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<TryJob | null>(null);
  const stop = useRef<(() => void) | null>(null);
  useEffect(() => () => stop.current?.(), []);

  async function onFile(file: File | undefined) {
    if (!file || !status.data) return;
    setError(null);
    setJob(null);
    const problem = await checkClip(file, status.data);
    if (problem) return setError(problem);
    setBusy(true);
    try {
      const created = await uploadClip(file);
      setJob(created);
      stop.current?.();
      stop.current = followJob(created.id, setJob, () => setJob(null));
    } catch (caught) {
      setError(caught instanceof TryError ? caught : new TryError("failed", String(caught)));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete() {
    if (!job) return;
    await deleteJob(job.id);
    setJob(null);
  }

  const working = job !== null && !isFinal(job);
  return (
    <section className="flex flex-col gap-4 py-6">
      <h1 className="text-display-sm font-bold text-balance">{t("pages.public.try.title")}</h1>
      <p className="max-w-2xl text-body-lg text-muted-foreground">
        {t("pages.public.try.body", {
          seconds: status.data?.max_seconds ?? 60,
          mb: status.data?.max_mb ?? 100,
        })}
      </p>
      <Consent />
      {status.data && !status.data.ai_available ? (
        <p
          role="status"
          className="flex items-center gap-2 font-medium text-danger dark:text-red-400"
        >
          <CircleAlertIcon aria-hidden className="size-4" />
          {t("pages.public.try.aiUnavailable")}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <label
          className={cn(
            buttonVariants({ size: "lg" }),
            "cursor-pointer",
            (busy || working || !status.data) && "pointer-events-none opacity-50",
          )}
        >
          <UploadIcon aria-hidden />
          {t("pages.public.try.choose")}
          <input
            type="file"
            accept="video/*"
            className="sr-only"
            disabled={busy || working || !status.data}
            onChange={(event) => void onFile(event.target.files?.[0])}
          />
        </label>
        <Link
          to="/public/try/live"
          className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
        >
          {t("pages.public.try.livePhone")}
        </Link>
      </div>
      {error ? (
        <p role="alert" className="font-medium text-danger dark:text-red-400">
          {t(`pages.public.try.errors.${error.kind}`, {
            seconds: status.data?.max_seconds ?? 60,
            mb: status.data?.max_mb ?? 100,
          })}
        </p>
      ) : null}
      {working && job ? (
        <div role="status" aria-live="polite" className="flex flex-col gap-2">
          <p>{t(`pages.public.try.stages.${job.stage}`, { defaultValue: job.stage })}</p>
          <progress
            className="h-2 w-full max-w-md"
            max={1}
            value={job.progress}
            aria-label={t("pages.public.try.progress")}
          />
        </div>
      ) : null}
      {job && (job.status === "failed" || job.status === "rejected") ? (
        <p role="alert" className="font-medium text-danger dark:text-red-400">
          {job.error ?? t("pages.public.try.errors.failed")}
        </p>
      ) : null}
      {job?.status === "done" ? <Result job={job} onDelete={() => void onDelete()} /> : null}
    </section>
  );
}
