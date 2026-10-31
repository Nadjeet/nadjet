import { CheckIcon, ClockIcon, SirenIcon, TriangleAlertIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { SimulatedLabel } from "@/components/incident/simulated-label";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatTime, useLabel } from "@/lib/format";
import { useAcknowledgePreAlert, type PreAlert } from "@/lib/hospital-queries";
import { cn } from "@/lib/utils";

const TAGS = ["red", "yellow", "green", "black"] as const;
/** Figma status palette: error, warning, success, then neutral ink for deceased. */
const TILE: Record<(typeof TAGS)[number], { tile: string; dot: string }> = {
  red: { tile: "bg-danger-soft text-danger-strong", dot: "bg-danger" },
  yellow: { tile: "bg-warning-soft text-warning-strong", dot: "bg-warning" },
  green: { tile: "bg-success-soft text-success-text", dot: "bg-success" },
  black: { tile: "bg-surface-strong text-ink", dot: "bg-ink" },
};

function place(alert: PreAlert): string {
  const road = [alert.road, alert.pk_km !== null ? `PK ${alert.pk_km}` : null]
    .filter(Boolean)
    .join(" ");
  return [road, alert.wilaya].filter(Boolean).join(", ") || alert.location_text || "—";
}

/** `mm:ss` until the ambulance is due; after that, how long it is overdue. */
function Countdown({ dueAt, now }: { dueAt: string; now: number }) {
  const { t, i18n } = useTranslation();
  const seconds = Math.round((new Date(dueAt).getTime() - now) / 1000);
  const abs = Math.abs(seconds);
  const clock = `${Math.floor(abs / 60)}:${String(abs % 60).padStart(2, "0")}`;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="flex items-center gap-1.5 text-body-sm font-light text-brand-500">
        <ClockIcon aria-hidden className="size-4" />
        {seconds >= 0 ? t("hospital.card.arrivesIn") : t("hospital.card.overdue")}
      </span>
      <time
        dateTime={dueAt}
        dir="ltr"
        className={cn(
          "text-[2.125rem] leading-[2.6rem] font-semibold tracking-tight tabular-nums",
          seconds < 0 ? "text-danger-strong" : "text-brand-500",
        )}
      >
        {clock}
      </time>
      <span className="text-body-xs text-brand-200">
        {t("hospital.card.dueAt", { time: formatTime(dueAt, i18n.language) })}
      </span>
    </div>
  );
}

function Victims({ alert }: { alert: PreAlert }) {
  const { t, i18n } = useTranslation();
  return (
    <section aria-label={t("hospital.card.victims")} className="flex flex-col gap-3">
      <h3 className="text-body-xs font-semibold tracking-[0.5px] text-brand-900 uppercase">
        {t("hospital.card.victims")} · {alert.victims.total}
      </h3>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {TAGS.map((tag) => (
          <li
            key={tag}
            className={cn("flex flex-col gap-0.5 rounded-lg px-3 py-2", TILE[tag].tile)}
          >
            <span className="text-display-xs font-semibold tabular-nums">{alert.victims[tag]}</span>
            <span className="flex items-center gap-1.5 text-body-xs font-medium">
              <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", TILE[tag].dot)} />
              {t(`respond.triage.${tag}`)}
            </span>
          </li>
        ))}
      </ul>
      {alert.casualties.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[32rem] text-start text-body-sm">
            <caption className="sr-only">{t("hospital.card.vitals")}</caption>
            <thead className="text-[0.6875rem] tracking-[0.55px] text-ink-subtle uppercase">
              <tr>
                {(["tag", "avpu", "resp", "pulse", "spo2", "bleeding", "time"] as const).map(
                  (col) => (
                    <th key={col} scope="col" className="px-2 py-1 text-start font-medium">
                      {t(`ops.casualties.${col}`)}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {alert.casualties.map((c) => (
                <tr key={c.id} className="border-t border-line text-ink-body">
                  <th scope="row" className="px-2 py-1 text-start font-semibold text-ink">
                    {t(`ops.triage.${c.triage_tag}`)}
                  </th>
                  <td className="px-2 py-1">{c.avpu ?? "—"}</td>
                  <td className="px-2 py-1">{c.resp_rate ?? "—"}</td>
                  <td className="px-2 py-1">{c.pulse ?? "—"}</td>
                  <td className="px-2 py-1">{c.spo2 ?? "—"}</td>
                  <td className="px-2 py-1">
                    {c.bleeding === null ? "—" : c.bleeding ? t("ops.yes") : t("ops.no")}
                  </td>
                  <td className="px-2 py-1 whitespace-nowrap">{formatTime(c.at, i18n.language)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-body-sm text-ink-muted">{t("hospital.card.noVictims")}</p>
      )}
    </section>
  );
}

/** One incoming patient group: due time, sending unit, victims with vitals, acknowledgement. */
export function PreAlertCard({
  alert,
  facilityId,
  now,
}: {
  alert: PreAlert;
  facilityId: string;
  now: number;
}) {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  const acknowledge = useAcknowledgePreAlert(facilityId);
  return (
    <article
      aria-labelledby={`prealert-${alert.short_code}`}
      className={cn(
        "flex flex-col gap-4 rounded-lg p-4",
        alert.acknowledged_at
          ? "border border-line bg-white"
          : "border-2 border-brand-indigo bg-[rgb(239_246_255/0.4)] shadow-card",
      )}
    >
      <header className="flex flex-wrap items-center gap-2">
        {alert.priority === 1 ? (
          <span className="rounded-md bg-danger px-1 py-0.5 text-[0.625rem] leading-[0.9rem] text-white">
            {t("priority.p1")}
          </span>
        ) : (
          <PriorityBadge level={alert.priority as PriorityLevel} compact />
        )}
        <h3 id={`prealert-${alert.short_code}`} className="text-body-sm font-semibold text-ink">
          <bdi dir="ltr">INC-{alert.short_code}</bdi>
        </h3>
        <span className="flex items-center gap-1.5 text-[0.6875rem] text-brand-900">
          <span aria-hidden className="size-1.5 rounded-full bg-brand-indigo" />
          {t(`status.${alert.status}`)}
        </span>
        {alert.mass_casualty ? (
          <Badge variant="destructive">
            <TriangleAlertIcon aria-hidden />
            {t("hospital.massCasualty")}
          </Badge>
        ) : null}
        {alert.needs_extrication ? (
          <Badge variant="outline">{t("hospital.card.extrication")}</Badge>
        ) : null}
      </header>
      <div className="grid gap-4 border-b border-line pb-4 sm:grid-cols-2">
        <Countdown dueAt={alert.expected_arrival_at} now={now} />
        <div className="flex flex-col gap-1 text-body-sm text-ink-body">
          <span className="flex items-center gap-2 font-medium text-ink">
            <SirenIcon aria-hidden className="size-4 text-brand-500" />
            {alert.units.length === 0
              ? t("hospital.card.noUnit")
              : alert.units.map((u) => u.callsign).join(", ")}
          </span>
          {alert.units.some((u) => u.simulated) ? <SimulatedLabel className="w-fit" /> : null}
          <span>{label(`ops.type.${alert.type}`, alert.type)}</span>
          <span className="text-ink-muted">{place(alert)}</span>
          {alert.people_reported !== null ? (
            <span>{t("respond.detail.people", { count: alert.people_reported })}</span>
          ) : null}
        </div>
      </div>
      <Victims alert={alert} />
      <footer className="flex flex-wrap items-center gap-3">
        {alert.acknowledged_at ? (
          <p className="flex items-center gap-2 rounded-md bg-success-soft px-3 py-2 text-body-sm font-medium text-success-text">
            <CheckIcon aria-hidden className="size-4" />
            {t("hospital.card.acknowledged", {
              name: alert.acknowledged_by ?? "",
              time: formatTime(alert.acknowledged_at, i18n.language),
            })}
          </p>
        ) : (
          <Button
            variant="gradient"
            size="lg"
            className="w-full sm:w-auto sm:px-8"
            disabled={acknowledge.isPending}
            onClick={() => acknowledge.mutate(alert.incident_id)}
          >
            {t("hospital.card.acknowledge")}
          </Button>
        )}
        {acknowledge.isError ? (
          <p role="alert" className="text-body-sm text-danger-strong">
            {t("hospital.error")}
          </p>
        ) : null}
      </footer>
    </article>
  );
}
