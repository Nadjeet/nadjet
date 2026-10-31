import {
  ActivityIcon,
  BellRingIcon,
  ClockIcon,
  ShieldCheckIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/lib/auth-store";
import { formatTime } from "@/lib/format";
import { useHospitalBoard } from "@/lib/hospital-queries";
import { KpiCard } from "@/pages/ops/console/kpi-ribbon";

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
  if (board.isPending) return <Skeleton className="h-64 w-full rounded-2xl" />;
  if (board.isError || !board.data) {
    return (
      <p role="alert" className="text-body-md">
        {t("hospital.loadError")}{" "}
        <Button variant="link" onClick={() => void board.refetch()}>
          {t("common.retry")}
        </Button>
      </p>
    );
  }
  const { facility, incoming, history } = board.data;
  const mass = incoming.filter((a) => a.mass_casualty);
  const victims = incoming.reduce((sum, a) => sum + a.victims.total, 0);
  const next = incoming
    .map((a) => new Date(a.expected_arrival_at).getTime())
    .filter((due) => due >= now)
    .sort((a, b) => a - b)[0];
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3 rounded-2xl bg-white p-5 shadow-card">
        <div className="flex min-w-0 flex-col">
          <span className="text-body-xs font-medium text-ink-muted uppercase">
            {t("hospital.welcome")}
          </span>
          <h1 className="truncate text-body-xl leading-7 font-semibold text-ink">
            {facility.name}
          </h1>
        </div>
        <span className="rounded-md bg-brand-400 px-2.5 py-1 text-body-xs text-white">
          {t("hospital.incoming", { count: incoming.length })}
        </span>
      </header>

      {mass.length > 0 ? (
        <p
          role="alert"
          className="flex items-center gap-3 rounded-2xl border-2 border-danger bg-danger-soft p-4 text-body-lg font-semibold text-danger-strong"
        >
          <TriangleAlertIcon aria-hidden className="size-7 shrink-0" />
          {t("hospital.massCasualtyBanner", {
            codes: mass.map((a) => a.short_code).join(", "),
          })}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard
          title={t("hospital.kpi.incoming")}
          value={incoming.length}
          badge={mass.length || undefined}
          hint={t("hospital.kpi.incomingHint")}
          hintIcon={BellRingIcon}
        />
        <KpiCard
          title={t("hospital.kpi.victims")}
          value={victims}
          hint={t("hospital.kpi.victimsHint")}
          hintIcon={ActivityIcon}
        />
        <KpiCard
          title={t("hospital.kpi.next")}
          value={next ? formatTime(new Date(next).toISOString(), i18n.language) : "—"}
          hint={t("hospital.kpi.nextHint")}
          hintIcon={ClockIcon}
        />
        <KpiCard
          title={t("hospital.kpi.state")}
          value={
            facility.ready_state === "ready"
              ? t("hospital.readiness.ready")
              : t("hospital.readiness.divert")
          }
          hint={t("hospital.kpi.stateHint")}
          hintIcon={ShieldCheckIcon}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-12">
        <section
          aria-labelledby="incoming-title"
          className="flex flex-col gap-4 rounded-2xl bg-white p-5 shadow-card xl:col-span-8"
        >
          <h2 id="incoming-title" className="text-body-md font-medium text-ink">
            {t("hospital.incomingTitle")}
          </h2>
          {incoming.length === 0 ? (
            <p className="rounded-lg border border-dashed border-line p-6 text-center text-body-sm text-ink-muted">
              {t("hospital.none")}
            </p>
          ) : (
            <div className="flex flex-col gap-5">
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

        <div className="flex flex-col gap-6 xl:col-span-4">
          <ReadinessPanel
            facilityId={facility.id}
            state={facility.ready_state}
            exampleCode={incoming[0]?.short_code ?? "<code>"}
          />
          <section
            aria-labelledby="history-title"
            className="flex flex-col gap-4 rounded-2xl bg-white p-5 shadow-card"
          >
            <h2 id="history-title" className="text-body-md font-medium text-ink">
              {t("hospital.historyTitle")}
            </h2>
            {history.length === 0 ? (
              <p className="text-body-sm text-ink-muted">{t("hospital.noHistory")}</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {history.map((alert) => (
                  <li
                    key={alert.incident_id}
                    className="flex flex-col gap-1.5 rounded-lg border border-line p-3.5"
                  >
                    <div className="flex items-center gap-1.5">
                      <PriorityBadge level={alert.priority as PriorityLevel} compact />
                      <bdi dir="ltr" className="text-body-xs font-semibold text-ink">
                        INC-{alert.short_code}
                      </bdi>
                      <span className="ms-auto text-body-xs text-brand-500">
                        {formatTime(alert.expected_arrival_at, i18n.language)}
                      </span>
                    </div>
                    <p className="text-[0.6875rem] text-ink-muted">
                      {t(`status.${alert.status}`)} ·{" "}
                      {t("hospital.historyVictims", { count: alert.victims.total })}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
