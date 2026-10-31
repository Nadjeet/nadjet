import { useNavigate } from "@tanstack/react-router";
import {
  PhoneCallIcon,
  PlusIcon,
  ShieldCheckIcon,
  SlidersHorizontalIcon,
  XIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

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
import { InspectPanel } from "./console/inspect-panel";
import { KpiRibbon } from "./console/kpi-ribbon";
import { PriorityTabs, QueueCards } from "./console/queue-cards";
import { QueueFiltersBar } from "./incident/incident-queue";
import { NewIncidentDialog } from "./incident/new-incident-dialog";
import { OpsMap, type PickedPoint } from "./incident/ops-map";
import { SystemStatusCard } from "./system-status-card";

const CAN_CREATE = new Set(["operator", "supervisor", "admin"]);

/**
 * Operator console, Figma "control" dashboard: KPI ribbon, then queue cards, live map and the
 * inspect panel side by side, then the audit strip (FR-MAP-001, FR-MAP-002, NFR-SAFE-001).
 */
export function ConsolePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const role = useSession()?.user.role;
  const [filters, setFilters] = useState<QueueFilters>({ status: "open" });
  const incidents = useIncidents(filters);
  const openIncidents = useIncidents({ status: "open" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
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

  const selected = items.find((incident) => incident.id === selectedId) ?? items[0] ?? null;
  const canCreate = role !== undefined && CAN_CREATE.has(role);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-display-xs font-semibold text-ink">{t("ops.console.title")}</h1>
        <div className="flex flex-wrap items-center gap-3">
          {hasSimulated ? <SimulatedLabel /> : null}
          {canCreate ? (
            <Button onClick={() => setDialogOpen(true)}>
              <PlusIcon aria-hidden />
              {t("ops.console.newIncident")}
            </Button>
          ) : null}
        </div>
      </header>

      <KpiRibbon open={openIncidents.data?.items} resources={resources.data} />

      <div className="grid gap-6 xl:grid-cols-12">
        <section
          aria-labelledby="queue-title"
          className="flex min-w-0 flex-col gap-4 rounded-2xl border border-border bg-card p-5 shadow-card xl:col-span-3 xl:max-h-[calc(100dvh-10rem)]"
        >
          <div className="flex items-center justify-between gap-2 border-b border-border pb-3">
            <h2 id="queue-title" className="flex items-center gap-1 text-body-lg font-semibold">
              {t("ops.console.queue")}
              {incidents.data ? (
                <span className="relative -top-2 grid min-w-4 place-items-center rounded-full bg-danger px-1 text-[0.625rem] font-semibold text-white">
                  {incidents.data.total}
                  <span className="sr-only">
                    {t("ops.console.count", { count: incidents.data.total })}
                  </span>
                </span>
              ) : null}
            </h2>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-expanded={showFilters}
              aria-label={t("ops.console.moreFilters")}
              title={t("ops.console.moreFilters")}
              onClick={() => setShowFilters((value) => !value)}
            >
              <SlidersHorizontalIcon aria-hidden />
            </Button>
          </div>
          <PriorityTabs filters={filters} onChange={setFilters} />
          {showFilters ? <QueueFiltersBar filters={filters} onChange={setFilters} /> : null}
          <div className="-me-2 min-h-0 flex-1 overflow-y-auto pe-2">
            {incidents.isPending ? <Skeleton className="h-40 w-full" /> : null}
            {incidents.isError ? (
              <p role="alert" className="text-body-sm">
                {t("ops.console.loadError")}{" "}
                <Button variant="link" onClick={() => void incidents.refetch()}>
                  {t("common.retry")}
                </Button>
              </p>
            ) : null}
            {incidents.data && items.length === 0 ? (
              <p className="text-body-sm text-ink-muted">{t("ops.console.empty")}</p>
            ) : null}
            {items.length > 0 ? (
              <QueueCards
                incidents={items}
                selectedId={selected?.id ?? null}
                onSelect={setSelectedId}
              />
            ) : null}
          </div>
          {canCreate ? (
            <Button variant="success-solid" className="w-full" onClick={() => setDialogOpen(true)}>
              <PhoneCallIcon aria-hidden />
              {t("ops.console.manualCall")}
            </Button>
          ) : null}
        </section>

        <section
          aria-labelledby="map-title"
          className="flex min-w-0 flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-card xl:col-span-6"
        >
          <h2 id="map-title" className="text-body-lg font-semibold">
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
            className="h-[28rem] overflow-hidden rounded-lg border border-border xl:h-auto xl:min-h-[34rem] xl:flex-1"
            incidents={items}
            cameras={cameras.data ?? []}
            resources={resources.data}
            pickMode={pickMode}
            picked={picked}
            onSelectIncident={open}
            onPick={onPick}
          />
          <p className="text-body-xs text-ink-muted">{t("ops.console.mapLegend")}</p>
        </section>

        <section
          aria-labelledby="inspect-title"
          className="flex min-w-0 flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-card xl:col-span-3"
        >
          <h2 id="inspect-title" className="text-body-lg font-semibold">
            {t("ops.console.inspect")}
          </h2>
          <InspectPanel incident={selected} cameras={cameras.data ?? []} />
        </section>
      </div>

      <footer className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-5 py-4 shadow-card">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-body-xs text-ink-body">
          <span className="inline-flex items-center gap-1.5 font-medium">
            <ShieldCheckIcon aria-hidden className="size-4 text-brand-indigo" />
            {t("ops.console.humanGate")}
          </span>
          <span className="text-ink-muted">{t("ops.console.humanGateHint")}</span>
        </p>
        <span className="rounded-md bg-surface-strong px-2 py-1 text-body-xs text-ink-body">
          {t("ops.console.standards")}
        </span>
      </footer>

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
