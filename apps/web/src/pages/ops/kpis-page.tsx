import { useQuery } from "@tanstack/react-query";
import type { ParseKeys } from "i18next";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { components } from "@nadjet/api-client";

import { api } from "@/api";
import { PriorityBadge } from "@/components/incident/priority-badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fieldClasses } from "@/components/ui/input";
import { formatDateTime, useLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

type Report = components["schemas"]["KpiReport"];
type Group = components["schemas"]["KpiGroup"];
type Period = Report["period"];

const METRICS = [
  "detection_s",
  "verification_s",
  "acknowledge_s",
  "scene_s",
  "hospital_s",
] as const;

/** `4 s`, `2 min 30 s`, `1 h 05 min`: Latin digits in every language. */
function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "–";
  const total = Math.round(seconds);
  if (total < 60) return `${total} s`;
  if (total < 3600) return `${Math.floor(total / 60)} min ${String(total % 60).padStart(2, "0")} s`;
  return `${Math.floor(total / 3600)} h ${String(Math.floor((total % 3600) / 60)).padStart(2, "0")} min`;
}

function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

async function fetchKpis(since: string, until: string, period: Period): Promise<Report> {
  const { data, error } = await api.GET("/kpis", {
    params: {
      query: { since: `${since}T00:00:00Z`, until: `${until}T23:59:59Z`, period },
    },
  });
  if (!data) throw new Error(`kpis: ${JSON.stringify(error)}`);
  return data;
}

/** Median bars on a shared scale; every bar carries its value as text (never colour alone). */
function MetricBars({ group }: { group: Group }) {
  const { t } = useTranslation();
  const max = Math.max(1, ...METRICS.map((m) => group.metrics[m]?.p90_s ?? 0));
  return (
    <ul className="flex flex-col gap-3">
      {METRICS.map((metric) => {
        const stats = group.metrics[metric];
        const median = stats?.median_s ?? null;
        const p90 = stats?.p90_s ?? null;
        return (
          <li key={metric} className="grid gap-1">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-medium">{t(`kpis.metric.${metric}`)}</span>
              <span className="text-body-sm text-ink-muted">{t(`kpis.metricHelp.${metric}`)}</span>
            </div>
            <div
              className="relative h-6 overflow-hidden rounded-full bg-secondary"
              role="img"
              aria-label={`${t(`kpis.metric.${metric}`)}: ${t("kpis.median")} ${formatDuration(median)}, ${t("kpis.p90")} ${formatDuration(p90)}`}
            >
              <div
                className="absolute inset-y-0 start-0 bg-primary/35"
                style={{ width: `${((p90 ?? 0) / max) * 100}%` }}
              />
              <div
                className="absolute inset-y-0 start-0 bg-primary"
                style={{ width: `${((median ?? 0) / max) * 100}%` }}
              />
            </div>
            <bdi dir="ltr" className="text-body-sm">
              {t("kpis.median")} {formatDuration(median)} · {t("kpis.p90")} {formatDuration(p90)} ·{" "}
              {t("kpis.samples")} = {stats?.n ?? 0}
            </bdi>
          </li>
        );
      })}
    </ul>
  );
}

function GroupTable({ title, groups }: { title: ParseKeys; groups: Group[] }) {
  const { t } = useTranslation();
  const label = useLabel();
  return (
    <Card>
      <CardHeader>
        <h2 className="text-body-lg font-semibold text-ink">{t(title)}</h2>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {groups.length === 0 ? (
          <p className="text-ink-muted">{t("kpis.none")}</p>
        ) : (
          <table className="w-full text-start text-body-sm">
            <caption className="sr-only">{t(title)}</caption>
            <thead>
              <tr className="border-b border-border text-ink-muted">
                <th scope="col" className="py-2 pe-4 text-start">
                  {t("kpis.group")}
                </th>
                <th scope="col" className="pe-4 text-start">
                  {t("kpis.incidents")}
                </th>
                {METRICS.map((m) => (
                  <th key={m} scope="col" className="pe-4 text-start">
                    {t(`kpis.metric.${m}`)} ({t("kpis.median").toLowerCase()})
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g.key} className="border-b border-border last:border-0">
                  <th scope="row" className="py-2 pe-4 text-start font-medium">
                    {label(`admin.agencies.${g.key}`, g.key)}
                  </th>
                  <td className="pe-4">{g.incidents}</td>
                  {METRICS.map((m) => (
                    <td key={m} className="pe-4">
                      <bdi dir="ltr">{formatDuration(g.metrics[m]?.median_s)}</bdi>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

function FalseAlarms({ report }: { report: Report }) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <h2 className="text-body-lg font-semibold text-ink">{t("kpis.falseAlarms")}</h2>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {report.false_alarms.length === 0 ? (
          <p className="text-ink-muted">{t("kpis.none")}</p>
        ) : (
          <table className="w-full text-start text-body-sm">
            <caption className="sr-only">{t("kpis.falseAlarms")}</caption>
            <thead>
              <tr className="border-b border-border text-ink-muted">
                <th scope="col" className="py-2 pe-4 text-start">
                  {t("kpis.camera")}
                </th>
                <th scope="col" className="pe-4 text-start">
                  {t("kpis.raised")}
                </th>
                <th scope="col" className="pe-4 text-start">
                  {t("kpis.falsePositives")}
                </th>
                <th scope="col" className="text-start">
                  {t("kpis.rate")}
                </th>
              </tr>
            </thead>
            <tbody>
              {report.false_alarms.map((row) => (
                <tr key={row.camera_id} className="border-b border-border last:border-0">
                  <th scope="row" className="py-2 pe-4 text-start font-medium">
                    <bdi dir="ltr">{row.camera_id}</bdi>
                  </th>
                  <td className="pe-4">{row.incidents}</td>
                  <td className="pe-4">{row.false_positives}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div
                        className="h-3 w-24 overflow-hidden rounded-full bg-secondary"
                        aria-hidden
                      >
                        <div
                          className="h-full bg-danger"
                          style={{ width: `${(row.rate ?? 0) * 100}%` }}
                        />
                      </div>
                      <bdi dir="ltr">
                        {row.rate === null ? "–" : `${Math.round(row.rate * 100)} %`}
                      </bdi>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

function IncidentTable({ report }: { report: Report }) {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  return (
    <Card>
      <CardHeader>
        <h2 className="text-body-lg font-semibold text-ink">{t("kpis.perIncident")}</h2>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {report.incidents.length === 0 ? (
          <p className="text-ink-muted">{t("kpis.none")}</p>
        ) : (
          <table className="w-full text-start text-body-sm">
            <caption className="sr-only">{t("kpis.perIncident")}</caption>
            <thead>
              <tr className="border-b border-border text-ink-muted">
                <th scope="col" className="py-2 pe-4 text-start">
                  {t("kpis.code")}
                </th>
                <th scope="col" className="pe-4 text-start">
                  {t("kpis.priority")}
                </th>
                <th scope="col" className="pe-4 text-start">
                  {t("kpis.status")}
                </th>
                <th scope="col" className="pe-4 text-start">
                  {t("kpis.eventTime")}
                </th>
                {METRICS.map((m) => (
                  <th key={m} scope="col" className="pe-4 text-start">
                    {t(`kpis.metric.${m}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.incidents.map((incident) => (
                <tr key={incident.id} className="border-b border-border last:border-0">
                  <th scope="row" className="py-2 pe-4 text-start font-medium">
                    <bdi dir="ltr">{incident.short_code}</bdi>
                  </th>
                  <td className="pe-4">
                    <PriorityBadge level={incident.priority as 1 | 2 | 3 | 4} compact />
                  </td>
                  <td className="pe-4">{label(`status.${incident.status}`, incident.status)}</td>
                  <td className="pe-4">
                    <bdi dir="ltr">{formatDateTime(incident.event_time, i18n.language)}</bdi>
                  </td>
                  {METRICS.map((m) => (
                    <td key={m} className="pe-4">
                      <bdi dir="ltr">{formatDuration(incident.durations[m])}</bdi>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

/** Supervisor and admin: response-time KPIs from the incident timeline (US-11, FR-KPI-001/002). */
export function KpisPage() {
  const { t } = useTranslation();
  const [until, setUntil] = useState(() => isoDay(new Date()));
  const [since, setSince] = useState(() => isoDay(new Date(Date.now() - 30 * 86_400_000)));
  const [period, setPeriod] = useState<Period>("week");
  const { data, isPending, isError } = useQuery({
    queryKey: ["kpis", since, until, period],
    queryFn: () => fetchKpis(since, until, period),
    refetchInterval: 30_000,
  });
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-display-xs font-semibold text-ink text-balance">{t("kpis.title")}</h1>
        <p className="text-ink-muted">{t("kpis.intro")}</p>
      </div>
      <form className="flex flex-wrap items-end gap-4" onSubmit={(e) => e.preventDefault()}>
        <div className="grid gap-1.5">
          <Label htmlFor="kpi-since">{t("kpis.from")}</Label>
          <Input
            id="kpi-since"
            type="date"
            size="sm"
            value={since}
            max={until}
            onChange={(e) => e.target.value && setSince(e.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="kpi-until">{t("kpis.to")}</Label>
          <Input
            id="kpi-until"
            type="date"
            size="sm"
            value={until}
            min={since}
            onChange={(e) => e.target.value && setUntil(e.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="kpi-period">{t("kpis.periodLabel")}</Label>
          <select
            id="kpi-period"
            className={cn(fieldClasses, "h-10 text-body-sm")}
            value={period}
            onChange={(e) => setPeriod(e.target.value as Period)}
          >
            {(["day", "week", "month"] as const).map((p) => (
              <option key={p} value={p}>
                {t(`kpis.period.${p}`)}
              </option>
            ))}
          </select>
        </div>
      </form>
      {isPending ? <p className="text-ink-muted">{t("kpis.loading")}</p> : null}
      {isError ? <p role="alert">{t("kpis.error")}</p> : null}
      {data ? (
        <>
          <Card>
            <CardHeader>
              <h2 className="text-body-lg font-semibold text-ink">
                {t("kpis.overall")} ({data.overall.incidents})
              </h2>
            </CardHeader>
            <CardContent>
              <MetricBars group={data.overall} />
            </CardContent>
          </Card>
          <GroupTable title="kpis.byPeriod" groups={data.by_period} />
          <GroupTable title="kpis.byAgency" groups={data.by_agency} />
          <GroupTable title="kpis.byWilaya" groups={data.by_wilaya} />
          <FalseAlarms report={data} />
          <IncidentTable report={data} />
        </>
      ) : null}
    </div>
  );
}
