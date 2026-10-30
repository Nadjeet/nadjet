import { useNavigate } from "@tanstack/react-router";
import { PlusIcon, XIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { LiveIndicator } from "@/components/brand/live-indicator";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { SimulatedLabel } from "@/components/incident/simulated-label";
import { useSession } from "@/lib/auth-store";

import {
  useCameras,
  useIncidents,
  useMapResources,
  type QueueFilters,
} from "@/lib/incident-queries";
import { IncidentQueue, QueueFiltersBar } from "./incident/incident-queue";
import { NewIncidentDialog } from "./incident/new-incident-dialog";
import { OpsMap, type PickedPoint } from "./incident/ops-map";
import { SystemStatusCard } from "./system-status-card";

const CAN_CREATE = new Set(["operator", "supervisor", "admin"]);

/** Operator console: live incident queue next to the live map (FR-MAP-001, FR-MAP-002). */
export function ConsolePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const role = useSession()?.user.role;
  const [filters, setFilters] = useState<QueueFilters>({ status: "open" });
  const incidents = useIncidents(filters);
  const cameras = useCameras();
  const resources = useMapResources();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [pickMode, setPickMode] = useState(false);
  const [picked, setPicked] = useState<PickedPoint | null>(null);

  const open = useCallback(
    (id: string) => void navigate({ to: "/ops/incidents/$incidentId", params: { incidentId: id } }),
    [navigate],
  );
  const onPick = useCallback((point: PickedPoint) => {
    setPicked(point);
    setPickMode(false);
    setDialogOpen(true);
  }, []);

  useEffect(() => {
    if (!pickMode) return;
    const cancel = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setPickMode(false);
      setDialogOpen(true);
    };
    window.addEventListener("keydown", cancel);
    return () => window.removeEventListener("keydown", cancel);
  }, [pickMode]);

  const items = incidents.data?.items ?? [];
  const hasSimulated =
    (cameras.data ?? []).some((c) => c.simulated) ||
    (resources.data?.facilities ?? []).some((f) => f.simulated) ||
    (resources.data?.units ?? []).some((u) => u.simulated);

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-display-sm font-bold">{t("ops.console.title")}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <LiveIndicator />
          {hasSimulated ? <SimulatedLabel /> : null}
          {role && CAN_CREATE.has(role) ? (
            <Button onClick={() => setDialogOpen(true)}>
              <PlusIcon aria-hidden />
              {t("ops.console.newIncident")}
            </Button>
          ) : null}
        </div>
      </header>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-labelledby="queue-title" className="flex min-w-0 flex-col gap-3">
          <h2 id="queue-title" className="text-display-xs font-bold">
            {t("ops.console.queue")}
            {incidents.data ? (
              <span className="ms-2 text-body-md font-normal text-muted-foreground">
                {t("ops.console.count", { count: incidents.data.total })}
              </span>
            ) : null}
          </h2>
          <QueueFiltersBar filters={filters} onChange={setFilters} />
          {incidents.isPending ? <Skeleton className="h-40 w-full" /> : null}
          {incidents.isError ? (
            <p role="alert">
              {t("ops.console.loadError")}{" "}
              <Button variant="link" onClick={() => void incidents.refetch()}>
                {t("common.retry")}
              </Button>
            </p>
          ) : null}
          {incidents.data && items.length === 0 ? (
            <p className="text-muted-foreground">{t("ops.console.empty")}</p>
          ) : null}
          {items.length > 0 ? <IncidentQueue incidents={items} /> : null}
        </section>

        <section aria-labelledby="map-title" className="flex min-w-0 flex-col gap-3">
          <h2 id="map-title" className="text-display-xs font-bold">
            {t("ops.console.map")}
          </h2>
          {pickMode ? (
            <p
              role="status"
              className="flex items-center justify-between gap-3 rounded-lg bg-accent px-4 py-2 text-body-sm text-accent-foreground"
            >
              {t("ops.create.pickHint")}
              <Button
                size="xs"
                variant="outline"
                onClick={() => {
                  setPickMode(false);
                  setDialogOpen(true);
                }}
              >
                <XIcon aria-hidden />
                {t("ops.actions.cancel")}
              </Button>
            </p>
          ) : null}
          <OpsMap
            className="h-[28rem] overflow-hidden rounded-lg border border-border xl:h-[calc(100dvh-14rem)]"
            incidents={items}
            cameras={cameras.data ?? []}
            resources={resources.data}
            pickMode={pickMode}
            picked={picked}
            onSelectIncident={open}
            onPick={onPick}
          />
          <p className="text-body-xs text-muted-foreground">{t("ops.console.mapLegend")}</p>
        </section>
      </div>

      <NewIncidentDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        picked={picked}
        onPickOnMap={() => {
          setDialogOpen(false);
          setPickMode(true);
        }}
        onCreated={(id) => {
          setPicked(null);
          open(id);
        }}
      />
      <SystemStatusCard />
    </div>
  );
}
