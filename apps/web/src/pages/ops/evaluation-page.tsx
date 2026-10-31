import { useQuery } from "@tanstack/react-query";
import { TriangleAlertIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { components } from "@nadjet/api-client";

import { api } from "@/api";
import { AiSourceTag } from "@/components/incident/ai-source-tag";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";

type Results = components["schemas"]["EvaluationResults"];
type Metric = components["schemas"]["Metric"];

async function fetchEvaluation(): Promise<Results | null> {
  const { data, error, response } = await api.GET("/evaluation/latest");
  if (response.status === 404) return null;
  if (!data) throw new Error(`evaluation: ${JSON.stringify(error)}`);
  return data;
}

function number(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? "–" : value.toFixed(digits);
}

/** A value with its bootstrap interval, `0.91 [0.80, 0.97]`. */
function Interval({ metric, digits = 2 }: { metric: Metric; digits?: number }) {
  return (
    <bdi dir="ltr">
      {number(metric.value, digits)}
      {metric.ci ? (
        <span className="text-ink-muted">
          {" "}
          [{number(metric.ci.low, digits)}, {number(metric.ci.high, digits)}]
        </span>
      ) : null}
    </bdi>
  );
}

function Header({ results }: { results: Results }) {
  const { t, i18n } = useTranslation();
  return (
    <Card>
      <CardContent className="grid gap-3 sm:grid-cols-2">
        <p>
          <span className="text-ink-muted">{t("evaluation.generated")}: </span>
          <bdi dir="ltr">{formatDateTime(results.generated_at, i18n.language)}</bdi>
        </p>
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-ink-muted">{t("evaluation.commit")}: </span>
          <bdi dir="ltr" className="font-mono">
            {results.git_sha}
          </bdi>
          {results.dirty ? <Badge variant="secondary">{t("evaluation.dirty")}</Badge> : null}
        </p>
        <p>
          <span className="text-ink-muted">{t("evaluation.seed")}: </span>
          <bdi dir="ltr">{results.seed}</bdi> · {t("evaluation.samples")}:{" "}
          <bdi dir="ltr">{results.bootstrap_samples}</bdi>
        </p>
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-ink-muted">{t("evaluation.cameraHours")}: </span>
          <bdi dir="ltr">{number(results.camera_hours)}</bdi>
          <Badge variant={results.meets_camera_hour_target ? "success" : "secondary"}>
            {results.meets_camera_hour_target
              ? t("evaluation.targetMet")
              : t("evaluation.targetMissed")}
          </Badge>
        </p>
        <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
          <span className="text-ink-muted">{t("evaluation.models")}: </span>
          {Object.entries(results.models).map(([role, id]) => (
            <span key={role} className="flex items-center gap-1">
              <bdi dir="ltr">{role}</bdi>
              <AiSourceTag source={{ kind: "model", id }} />
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function Ablation({ results }: { results: Results }) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <h2 className="text-body-lg font-semibold text-ink">{t("evaluation.ablation")}</h2>
        <p className="text-body-sm text-ink-muted">{t("evaluation.ci")}</p>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-start text-body-sm">
          <caption className="sr-only">{t("evaluation.ablation")}</caption>
          <thead>
            <tr className="border-b border-border text-ink-muted">
              <th scope="col" className="py-2 pe-4 text-start">
                {t("evaluation.configuration")}
              </th>
              {(["precision", "recall", "f1", "delay", "falseAlarmsPerHour"] as const).map((k) => (
                <th key={k} scope="col" className="pe-4 text-start">
                  {t(`evaluation.${k}`)}
                </th>
              ))}
              <th scope="col" className="text-start">
                {t("evaluation.tp")} / {t("evaluation.fp")} / {t("evaluation.fn")}
              </th>
            </tr>
          </thead>
          <tbody>
            {results.ablation.map((row) => (
              <tr key={row.name} className="border-b border-border align-top last:border-0">
                <th scope="row" className="py-2 pe-4 text-start font-medium">
                  {row.name}
                  <span className="block font-normal text-ink-muted">{row.description}</span>
                </th>
                {row.metrics ? (
                  <>
                    <td className="pe-4">
                      <Interval metric={row.metrics.precision} />
                    </td>
                    <td className="pe-4">
                      <Interval metric={row.metrics.recall} />
                    </td>
                    <td className="pe-4">
                      <Interval metric={row.metrics.f1} />
                    </td>
                    <td className="pe-4">
                      <Interval metric={row.metrics.median_delay_s} digits={1} />
                    </td>
                    <td className="pe-4">
                      <Interval metric={row.metrics.false_alarms_per_camera_hour} />
                    </td>
                    <td>
                      <bdi dir="ltr">
                        {row.metrics.true_positives} / {row.metrics.false_positives} /{" "}
                        {row.metrics.false_negatives}
                      </bdi>
                    </td>
                  </>
                ) : (
                  <td colSpan={6}>
                    <Badge variant="outline">{t("evaluation.notRun")}</Badge> {row.not_run_reason}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function AiQuality({ results }: { results: Results }) {
  const { t } = useTranslation();
  const quality = results.ai_quality;
  const latency = Object.entries(results.latency_ms ?? {});
  if (!quality && latency.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <h2 className="text-body-lg font-semibold text-ink">{t("evaluation.aiQuality")}</h2>
      </CardHeader>
      <CardContent className="grid gap-4">
        {quality ? (
          <dl className="grid gap-2 sm:grid-cols-2">
            <div>
              <dt className="text-ink-muted">{t("evaluation.verifications")}</dt>
              <dd>
                <bdi dir="ltr">{quality.verifications}</bdi> · {t("evaluation.unavailable")}:{" "}
                <bdi dir="ltr">{quality.unavailable}</bdi>
              </dd>
            </div>
            <div>
              <dt className="text-ink-muted">{t("evaluation.validFirstTry")}</dt>
              <dd>
                <Interval metric={quality.valid_first_try} />
              </dd>
            </div>
            <div>
              <dt className="text-ink-muted">{t("evaluation.droppedCitations")}</dt>
              <dd>
                <Interval metric={quality.dropped_citation_share} />
              </dd>
            </div>
            <div>
              <dt className="text-ink-muted">{t("evaluation.cannotJudge")}</dt>
              <dd>
                <Interval metric={quality.cannot_judge_share} />
              </dd>
            </div>
          </dl>
        ) : null}
        {latency.length > 0 ? (
          <table className="w-full text-start text-body-sm">
            <caption className="text-start font-medium">{t("evaluation.latency")}</caption>
            <thead>
              <tr className="border-b border-border text-ink-muted">
                <th scope="col" className="py-2 pe-4 text-start" />
                <th scope="col" className="pe-4 text-start">
                  {t("evaluation.calls")}
                </th>
                <th scope="col" className="pe-4 text-start">
                  {t("evaluation.p50")}
                </th>
                <th scope="col" className="text-start">
                  {t("evaluation.p95")}
                </th>
              </tr>
            </thead>
            <tbody>
              {latency.map(([name, p]) => (
                <tr key={name} className="border-b border-border last:border-0">
                  <th scope="row" className="py-2 pe-4 text-start font-medium">
                    <bdi dir="ltr">{name}</bdi>
                  </th>
                  <td className="pe-4">
                    <bdi dir="ltr">{p.count}</bdi>
                  </td>
                  <td className="pe-4">
                    <bdi dir="ltr">{number(p.p50, 0)}</bdi>
                  </td>
                  <td>
                    <bdi dir="ltr">{number(p.p95, 0)}</bdi>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Clips({ results }: { results: Results }) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <h2 className="text-body-lg font-semibold text-ink">{t("evaluation.clips")}</h2>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="overflow-x-auto">
          <table className="w-full text-start text-body-sm">
            <caption className="sr-only">{t("evaluation.clips")}</caption>
            <thead>
              <tr className="border-b border-border text-ink-muted">
                <th scope="col" className="py-2 pe-4 text-start">
                  {t("evaluation.clip")}
                </th>
                <th scope="col" className="pe-4 text-start">
                  {t("evaluation.kind")}
                </th>
                <th scope="col" className="text-start">
                  {t("evaluation.alerts")}
                </th>
              </tr>
            </thead>
            <tbody>
              {results.clips.map((clip) => (
                <tr key={clip.id} className="border-b border-border last:border-0">
                  <th scope="row" className="py-2 pe-4 text-start font-medium">
                    <bdi dir="ltr">{clip.id}</bdi>
                  </th>
                  <td className="pe-4">{clip.kind}</td>
                  <td>
                    <bdi dir="ltr">{(clip.alerts ?? []).length}</bdi>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(results.skipped_clips ?? []).length > 0 ? (
          <div>
            <h3 className="font-medium">{t("evaluation.skipped")}</h3>
            <ul className="list-disc ps-6 text-body-sm">
              {(results.skipped_clips ?? []).map((clip) => (
                <li key={clip.id}>
                  <bdi dir="ltr">{clip.id}</bdi>: {clip.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Supervisor and admin: the latest evaluation on the evaluation clips (FR-KPI-003, SC-004/005). */
export function EvaluationPage() {
  const { t } = useTranslation();
  const { data, isPending, isError } = useQuery({
    queryKey: ["evaluation", "latest"],
    queryFn: fetchEvaluation,
  });
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-display-xs font-semibold text-ink text-balance">
        {t("evaluation.title")}
      </h1>
      {isPending ? <p className="text-ink-muted">{t("evaluation.loading")}</p> : null}
      {isError ? <p role="alert">{t("evaluation.error")}</p> : null}
      {data === null ? <p>{t("evaluation.none")}</p> : null}
      {data ? (
        <>
          <Header results={data} />
          <Ablation results={data} />
          <AiQuality results={data} />
          <Clips results={data} />
          <Card>
            <CardHeader>
              <h2 className="flex items-center gap-2 text-body-lg font-semibold text-ink">
                <TriangleAlertIcon aria-hidden className="size-5" />
                {t("evaluation.limits")}
              </h2>
              <p className="text-body-sm text-ink-muted">{t("evaluation.limitsNote")}</p>
            </CardHeader>
            <CardContent>
              <ul className="list-disc ps-6">
                {(data.limitations ?? []).map((limit) => (
                  <li key={limit}>{limit}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
