import { TriangleAlertIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/lib/auth-store";
import { formatTime } from "@/lib/format";
import { useHospitalBoard } from "@/lib/hospital-queries";

import { PreAlertCard } from "./prealert-card";
import { ReadinessPanel } from "./readiness-panel";

/** A clock that ticks every second, for the arrival countdowns. */
function useClock(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

/**
 * Hospital view (tablet): incoming pre-alerts of the user's facility, Ready/Divert, and the
 * arrivals of the day. It refreshes on every incident event, so a dispatch or a triage entry
 * shows within seconds (FR-HSP-001, FR-MAP-002).
 */
export function HospitalBoard() {
  const { t, i18n } = useTranslation();
  const facilityId = useSession()?.user.facility_id;
  const board = useHospitalBoard(facilityId);
  const now = useClock();

  if (!facilityId) return <p role="alert">{t("hospital.noFacility")}</p>;
  if (board.isPending) return <Skeleton className="h-64 w-full" />;
  if (board.isError || !board.data) {
    return (
      <p role="alert" className="text-body-lg">
        {t("hospital.loadError")}{" "}
        <Button variant="link" onClick={() => void board.refetch()}>
          {t("common.retry")}
        </Button>
      </p>
    );
  }
  const { facility, incoming, history } = board.data;
  const mass = incoming.filter((a) => a.mass_casualty);
  return (
    <div className="flex flex-col gap-6 text-body-lg">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col leading-tight">
          <span className="text-body-xs font-medium tracking-[0.5px] text-ink-muted uppercase">
            {t("surface.hospital")}
          </span>
          <h1 className="text-display-xs font-semibold text-ink">{facility.name}</h1>
        </div>
        <p className="rounded-full bg-accent px-3 py-1 text-body-sm font-medium text-primary">
          {t("hospital.incoming", { count: incoming.length })}
        </p>
      </header>

      {mass.length > 0 ? (
        <p
          role="alert"
          className="flex items-center gap-3 rounded-2xl border-2 border-danger bg-danger-soft p-4 text-body-xl font-semibold text-ink"
        >
          <TriangleAlertIcon aria-hidden className="size-8 shrink-0" />
          {t("hospital.massCasualtyBanner", {
            codes: mass.map((a) => a.short_code).join(", "),
          })}
        </p>
      ) : null}

      <ReadinessPanel
        facilityId={facility.id}
        state={facility.ready_state}
        exampleCode={incoming[0]?.short_code ?? "<code>"}
      />

      <section aria-labelledby="incoming-title" className="flex flex-col gap-4">
        <h2 id="incoming-title" className="text-body-lg font-semibold text-ink">
          {t("hospital.incomingTitle")}
        </h2>
        {incoming.length === 0 ? (
          <p className="text-ink-muted">{t("hospital.none")}</p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {incoming.map((alert) => (
              <PreAlertCard
                key={alert.incident_id}
                alert={alert}
                facilityId={facility.id}
                now={now}
              />
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="history-title" className="flex flex-col gap-3">
        <h2 id="history-title" className="text-body-lg font-semibold text-ink">
          {t("hospital.historyTitle")}
        </h2>
        {history.length === 0 ? (
          <p className="text-ink-muted">{t("hospital.noHistory")}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {history.map((alert) => (
              <li
                key={alert.incident_id}
                className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-card"
              >
                <bdi dir="ltr" className="font-mono text-body-xl font-bold">
                  {alert.short_code}
                </bdi>
                <PriorityBadge level={alert.priority as PriorityLevel} compact />
                <Badge variant="secondary">{t(`status.${alert.status}`)}</Badge>
                <span>{t("hospital.historyVictims", { count: alert.victims.total })}</span>
                <span className="text-ink-muted">
                  {t("hospital.card.dueAt", {
                    time: formatTime(alert.expected_arrival_at, i18n.language),
                  })}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
