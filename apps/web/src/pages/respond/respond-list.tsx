import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAge, useLabel } from "@/lib/format";
import { locationText } from "@/lib/incident-format";
import { useIncidents } from "@/lib/incident-queries";
import { usePushState } from "@/lib/push-context";

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

/** Incidents assigned to the responder's agency, most urgent first (FR-RSP-001, FR-SEC-002). */
export function RespondList() {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  const now = useNow();
  const incidents = useIncidents({ status: "open" });
  const push = usePushState();
  const items = incidents.data?.items ?? [];
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-display-xs font-bold">{t("respond.list.title")}</h1>
      <OfflineBanner />
      {push.state === "prompt" || push.state === "error" ? (
        <div className="rounded-lg border border-border p-3">
          <AlertsControl />
        </div>
      ) : null}
      <PendingActions />
      {incidents.isPending ? <Skeleton className="h-28 w-full" /> : null}
      {incidents.isError ? (
        <p role="alert">
          {t("respond.list.loadError")}{" "}
          <Button variant="link" onClick={() => void incidents.refetch()}>
            {t("common.retry")}
          </Button>
        </p>
      ) : null}
      {incidents.data && items.length === 0 ? (
        <p className="text-muted-foreground">{t("respond.list.empty")}</p>
      ) : null}
      <ul className="flex flex-col gap-3">
        {items.map((incident) => (
          <li key={incident.id}>
            <Link
              to="/respond/incidents/$incidentId"
              params={{ incidentId: incident.id }}
              className="flex min-h-14 flex-col gap-2 rounded-2xl border border-border bg-card p-4 shadow-soft focus-visible:shadow-focus"
            >
              <span className="flex flex-wrap items-center gap-2">
                <PriorityBadge level={incident.priority as PriorityLevel} />
                <bdi dir="ltr" className="font-mono text-body-lg font-bold">
                  {incident.short_code}
                </bdi>
                <Badge variant="secondary">{t(`status.${incident.status}`)}</Badge>
              </span>
              <span className="text-body-md font-medium">
                {label(`ops.type.${incident.type}`, incident.type)}
              </span>
              <span className="text-body-sm text-muted-foreground">
                {locationText(incident)} · {formatAge(incident.event_time, i18n.language, now)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
