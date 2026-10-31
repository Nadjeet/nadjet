import { Link } from "@tanstack/react-router";
import { ArrowRightIcon, MapPinIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAge, useLabel } from "@/lib/format";
import { locationText } from "@/lib/incident-format";
import { useIncidents, type Incident } from "@/lib/incident-queries";
import { usePushState } from "@/lib/push-context";
import { cn } from "@/lib/utils";

import { AlertsControl, OfflineBanner } from "./app-controls";
import { PendingActions } from "./pending-actions";

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

/**
 * Figma "home" mission card: region label, the place in large blue type, what is known and one
 * call to action. The AI text is shown as the AI wrote it (never a medical assessment).
 */
function MissionCard({ incident, now }: { incident: Incident; now: number }) {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  const verifier = incident.verifier_result;
  const ai = verifier.available
    ? i18n.language === "ar"
      ? verifier.description_ar
      : verifier.description_fr
    : null;
  const headline = incident.road ?? label(`ops.type.${incident.type}`, incident.type);
  return (
    <article className="relative flex w-[85%] shrink-0 snap-start flex-col gap-3 overflow-hidden rounded-2xl border border-brand-200 bg-card p-5 shadow-card first:w-full sm:w-80 sm:first:w-96">
      <div
        aria-hidden
        className="pointer-events-none absolute -end-16 -top-16 size-48 rounded-full bg-[radial-gradient(circle,rgb(85_168_254/0.25),transparent_70%)]"
      />
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1 text-body-xs text-primary">
          <MapPinIcon aria-hidden className="size-3.5" />
          {incident.wilaya ?? label(`ops.source.${incident.source}`, incident.source)}
        </span>
        <PriorityBadge level={incident.priority as PriorityLevel} />
      </div>
      <h2 className="text-display-xs font-semibold text-brand-500">
        <bdi>{headline}</bdi>
      </h2>
      <div className="flex flex-wrap items-center gap-2 text-body-xs">
        <bdi dir="ltr" className="font-mono font-semibold text-ink">
          {incident.short_code}
        </bdi>
        <Badge variant="secondary">{t(`status.${incident.status}`)}</Badge>
        <span className="text-ink-muted">{formatAge(incident.event_time, i18n.language, now)}</span>
      </div>
      <p className="line-clamp-3 text-body-sm text-ink-muted">
        {label(`ops.type.${incident.type}`, incident.type)} · {locationText(incident)}
        {ai ? ` — ${ai}` : ""}
      </p>
      <Link
        to="/respond/incidents/$incidentId"
        params={{ incidentId: incident.id }}
        className={cn(buttonVariants({ size: "sm" }), "mt-1 w-fit rounded-full px-5")}
      >
        {t("respond.list.openMission")}
        <ArrowRightIcon aria-hidden className="rtl:rotate-180" />
      </Link>
    </article>
  );
}

/** Incidents assigned to the responder's agency, most urgent first (FR-RSP-001, FR-SEC-002). */
export function RespondList() {
  const { t } = useTranslation();
  const now = useNow();
  const incidents = useIncidents({ status: "open" });
  const push = usePushState();
  const items = incidents.data?.items ?? [];
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-0.5">
        <h1 className="text-body-xl font-semibold text-ink">{t("respond.list.title")}</h1>
        <p className="text-body-sm text-ink-muted">{t("respond.list.subtitle")}</p>
      </div>
      <OfflineBanner />
      {push.state === "prompt" || push.state === "error" ? (
        <div className="rounded-2xl border border-border bg-card p-4 shadow-card">
          <AlertsControl />
        </div>
      ) : null}
      <PendingActions />
      {incidents.isPending ? <Skeleton className="h-56 w-full rounded-2xl" /> : null}
      {incidents.isError ? (
        <p role="alert">
          {t("respond.list.loadError")}{" "}
          <Button variant="link" onClick={() => void incidents.refetch()}>
            {t("common.retry")}
          </Button>
        </p>
      ) : null}
      {incidents.data && items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border p-6 text-center text-ink-muted">
          {t("respond.list.empty")}
        </p>
      ) : null}
      {items.length > 0 ? (
        <ul
          aria-label={t("respond.list.title")}
          className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:px-6"
        >
          {items.map((incident) => (
            <li key={incident.id} className="contents">
              <MissionCard incident={incident} now={now} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
