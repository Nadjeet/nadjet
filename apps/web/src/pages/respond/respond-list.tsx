import { Link, useNavigate } from "@tanstack/react-router";
import { MapPinCheckIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAge, useLabel } from "@/lib/format";
import { locationText } from "@/lib/incident-format";
import { useIncidents, type Incident } from "@/lib/incident-queries";
import { usePushState } from "@/lib/push-context";
import { OpsMap } from "@/pages/ops/incident/ops-map";

import { AlertsControl, OfflineBanner } from "./app-controls";
import { SectionTitle } from "./mission";
import { PendingActions } from "./pending-actions";

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

const noop = () => undefined;

/**
 * Figma "home" hero card (348 × 267, blue border, 18.6 px radius): location chip, the place in
 * large #2a93fe type, what is known in light blue, the priority chip and the gradient pill.
 * The AI text is shown as the AI wrote it (never a medical assessment).
 */
function HeroCard({ incident, now }: { incident: Incident; now: number }) {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  const verifier = incident.verifier_result;
  const ai = verifier.available
    ? i18n.language === "ar"
      ? verifier.description_ar
      : verifier.description_fr
    : null;
  const type = label(`ops.type.${incident.type}`, incident.type);
  return (
    <article className="relative flex min-h-[16.7rem] w-[87%] shrink-0 snap-start flex-col gap-3 overflow-hidden rounded-[18.6px] border border-brand-500 bg-white p-[18.6px] first:w-full">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 end-0 w-2/3 bg-[radial-gradient(circle_at_80%_30%,rgb(128_190_255/0.35),transparent_65%)]"
      />
      <div className="relative flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1 text-body-xs text-brand-500">
          <MapPinCheckIcon aria-hidden className="size-4 shrink-0" />
          <span className="truncate">
            {incident.wilaya ?? label(`ops.source.${incident.source}`, incident.source)}
          </span>
        </span>
        {incident.priority === 1 ? (
          <span className="shrink-0 rounded-md bg-danger px-2 py-0.5 text-[0.625rem] leading-[0.9rem] font-semibold text-white uppercase">
            {t("priority.p1")}
          </span>
        ) : (
          <PriorityBadge level={incident.priority as PriorityLevel} compact />
        )}
      </div>
      <h2 className="relative text-[1.4375rem] leading-tight font-semibold text-[#2a93fe]">
        <bdi>{incident.road ?? type}</bdi>
      </h2>
      <p className="relative line-clamp-4 text-[0.725rem] leading-[1.1rem] text-brand-300">
        <bdi dir="ltr">#{incident.short_code}</bdi> · {t(`status.${incident.status}`)} ·{" "}
        {formatAge(incident.event_time, i18n.language, now)}
        <br />
        {type} · {locationText(incident)}
        {ai ? ` — ${ai}` : ""}
      </p>
      <Link
        to="/respond/incidents/$incidentId"
        params={{ incidentId: incident.id }}
        className="relative mt-auto inline-flex h-9 w-fit items-center rounded-full bg-[linear-gradient(124deg,#3568f5_7.6%,#80beff_95.5%)] px-5 text-body-xs font-semibold text-white shadow-card transition-opacity hover:opacity-90 focus-visible:shadow-focus"
      >
        {t("respond.list.openMission")}
      </Link>
    </article>
  );
}

/**
 * Figma "home" screen (node 75:7914): the agency's missions as hero cards, most urgent first,
 * then the "Incidents Map" card (FR-RSP-001, FR-SEC-002).
 */
export function RespondList() {
  const { t } = useTranslation();
  const now = useNow();
  const navigate = useNavigate();
  const incidents = useIncidents({ status: "open" });
  const push = usePushState();
  const items = incidents.data?.items ?? [];
  return (
    <div className="flex flex-col gap-6">
      <h1 className="sr-only">{t("respond.list.title")}</h1>
      <OfflineBanner />
      {push.state === "prompt" || push.state === "error" ? (
        <div className="rounded-xl border border-brand-200 bg-white p-4">
          <AlertsControl />
        </div>
      ) : null}
      <PendingActions />
      {incidents.isPending ? <Skeleton className="h-[16.7rem] w-full rounded-[18.6px]" /> : null}
      {incidents.isError ? (
        <p role="alert">
          {t("respond.list.loadError")}{" "}
          <Button variant="link" onClick={() => void incidents.refetch()}>
            {t("common.retry")}
          </Button>
        </p>
      ) : null}
      {incidents.data && items.length === 0 ? (
        <p className="rounded-[18.6px] border border-dashed border-brand-200 bg-white p-6 text-center text-body-sm text-ink-muted">
          {t("respond.list.empty")}
        </p>
      ) : null}
      {items.length > 0 ? (
        <ul
          aria-label={t("respond.list.title")}
          className="-mx-6 flex snap-x snap-mandatory gap-3 overflow-x-auto px-6 pb-1"
        >
          {items.map((incident) => (
            <li key={incident.id} className="contents">
              <HeroCard incident={incident} now={now} />
            </li>
          ))}
        </ul>
      ) : null}
      {items.length > 0 ? (
        <section aria-labelledby="home-map" className="flex flex-col gap-3">
          <SectionTitle id="home-map">{t("respond.list.map")}</SectionTitle>
          <OpsMap
            incidents={items}
            cameras={[]}
            resources={undefined}
            pickMode={false}
            picked={null}
            onSelectIncident={(id) =>
              void navigate({ to: "/respond/incidents/$incidentId", params: { incidentId: id } })
            }
            onPick={noop}
            className="h-[17rem] overflow-hidden rounded-[10px] border-[0.8px] border-brand-500"
          />
        </section>
      ) : null}
    </div>
  );
}
