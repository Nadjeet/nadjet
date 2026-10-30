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
const TILE: Record<(typeof TAGS)[number], string> = {
  red: "border-red-700",
  yellow: "border-yellow-600",
  green: "border-green-700",
  black: "border-foreground",
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
    <div className="flex flex-col">
      <span className="flex items-center gap-2 text-body-md text-muted-foreground">
        <ClockIcon aria-hidden className="size-5" />
        {seconds >= 0 ? t("hospital.card.arrivesIn") : t("hospital.card.overdue")}
      </span>
      <time
        dateTime={dueAt}
        dir="ltr"
        className={cn("font-mono text-display-md font-bold", seconds < 0 && "text-danger")}
      >
        {clock}
      </time>
      <span className="text-body-sm text-muted-foreground">
        {t("hospital.card.dueAt", { time: formatTime(dueAt, i18n.language) })}
      </span>
    </div>
  );
}

function Victims({ alert }: { alert: PreAlert }) {
  const { t, i18n } = useTranslation();
  return (
    <section aria-label={t("hospital.card.victims")} className="flex flex-col gap-3">
      <h3 className="text-body-lg font-bold">
        {t("hospital.card.victims")} · {alert.victims.total}
      </h3>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {TAGS.map((tag) => (
          <li key={tag} className={cn("flex flex-col rounded-xl border-4 px-3 py-2", TILE[tag])}>
            <span className="font-mono text-display-sm font-bold">{alert.victims[tag]}</span>
            <span className="text-body-sm font-medium">{t(`respond.triage.${tag}`)}</span>
          </li>
        ))}
      </ul>
      {alert.casualties.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[32rem] text-start text-body-md">
            <caption className="sr-only">{t("hospital.card.vitals")}</caption>
            <thead className="text-body-sm text-muted-foreground">
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
                <tr key={c.id} className="border-t border-border">
                  <th scope="row" className="px-2 py-1 text-start font-bold">
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
        <p className="text-body-md text-muted-foreground">{t("hospital.card.noVictims")}</p>
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
      className="flex flex-col gap-4 rounded-3xl border border-border bg-card p-5 shadow-soft"
    >
      <header className="flex flex-wrap items-center gap-3">
        <h2 id={`prealert-${alert.short_code}`} className="text-display-sm font-bold">
          <bdi dir="ltr" className="font-mono">
            {alert.short_code}
          </bdi>
        </h2>
        <PriorityBadge level={alert.priority as PriorityLevel} />
        <Badge variant="secondary">{t(`status.${alert.status}`)}</Badge>
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
      <div className="grid gap-4 sm:grid-cols-2">
        <Countdown dueAt={alert.expected_arrival_at} now={now} />
        <div className="flex flex-col gap-1 text-body-md">
          <span className="flex items-center gap-2 font-medium">
            <SirenIcon aria-hidden className="size-5" />
            {alert.units.length === 0
              ? t("hospital.card.noUnit")
              : alert.units.map((u) => u.callsign).join(", ")}
          </span>
          {alert.units.some((u) => u.simulated) ? <SimulatedLabel className="w-fit" /> : null}
          <span>{label(`ops.type.${alert.type}`, alert.type)}</span>
          <span className="text-muted-foreground">{place(alert)}</span>
          {alert.people_reported !== null ? (
            <span>{t("respond.detail.people", { count: alert.people_reported })}</span>
          ) : null}
        </div>
      </div>
      <Victims alert={alert} />
      <footer className="flex flex-wrap items-center gap-3">
        {alert.acknowledged_at ? (
          <p className="flex items-center gap-2 text-body-md font-medium">
            <CheckIcon aria-hidden className="size-5" />
            {t("hospital.card.acknowledged", {
              name: alert.acknowledged_by ?? "",
              time: formatTime(alert.acknowledged_at, i18n.language),
            })}
          </p>
        ) : (
          <Button
            size="lg"
            className="h-14 px-8 text-body-lg"
            disabled={acknowledge.isPending}
            onClick={() => acknowledge.mutate(alert.incident_id)}
          >
            {t("hospital.card.acknowledge")}
          </Button>
        )}
        {acknowledge.isError ? (
          <p role="alert" className="text-body-md text-danger">
            {t("hospital.error")}
          </p>
        ) : null}
      </footer>
    </article>
  );
}
