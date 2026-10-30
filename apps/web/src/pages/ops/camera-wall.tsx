import { useQuery } from "@tanstack/react-query";
import { CircleAlertIcon, CircleCheckIcon, CircleOffIcon, MaximizeIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "@/api";
import { SimulatedLabel } from "@/components/incident/simulated-label";
import { LiveStream } from "@/components/stream/live-stream";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { incidentsKey, systemCamerasKey } from "@/live/keys";
import { cn } from "@/lib/utils";

import { streamUrls, tileStatus, type Camera, type TileStatus, type View } from "./camera-status";
import { useCameras } from "./incident/incident-queries";
import { fetchSystemCameras } from "./system-data";

const STATUS_ICON = { live: CircleCheckIcon, degraded: CircleAlertIcon, offline: CircleOffIcon };

function StatusBadge({ status }: { status: TileStatus }) {
  const { t } = useTranslation();
  const Icon = STATUS_ICON[status];
  return (
    <Badge
      variant={status === "live" ? "success" : status === "degraded" ? "destructive" : "secondary"}
    >
      <Icon aria-hidden />
      {t(`cameras.status.${status}`)}
    </Badge>
  );
}

function ViewToggle({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  const { t } = useTranslation();
  return (
    <div role="group" aria-label={t("cameras.view")} className="flex gap-1">
      {(["annotated", "raw"] as const).map((option) => (
        <Button
          key={option}
          type="button"
          size="xs"
          variant={view === option ? "default" : "secondary"}
          aria-pressed={view === option}
          onClick={() => onChange(option)}
        >
          {t(`cameras.${option}`)}
        </Button>
      ))}
    </div>
  );
}

function CameraTile({
  camera,
  status,
  incidents,
}: {
  camera: Camera;
  status: TileStatus;
  incidents: string[];
}) {
  const { t } = useTranslation();
  const [view, setView] = useState<View>("annotated");
  const [fullscreen, setFullscreen] = useState(false);
  const urls = streamUrls(camera.stream, view);
  const where = camera.pk_km === null ? camera.road : `${camera.road} PK ${camera.pk_km}`;
  return (
    <li
      className={cn(
        "flex flex-col gap-2 rounded-xl border bg-card p-3",
        incidents.length > 0 ? "border-danger ring-2 ring-danger" : "border-border",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate text-body-md font-bold">{camera.name}</h2>
          <bdi dir="ltr" className="text-body-sm text-muted-foreground">
            {where}
          </bdi>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {camera.simulated ? <SimulatedLabel /> : null}
          <StatusBadge status={status} />
        </div>
      </div>
      {incidents.length > 0 ? (
        <p
          role="status"
          className="flex items-center gap-2 text-body-sm font-medium text-danger dark:text-red-400"
        >
          <CircleAlertIcon aria-hidden className="size-4" />
          {t("cameras.incident", { codes: incidents.join(", ") })}
        </p>
      ) : null}
      <LiveStream
        urls={urls}
        label={t("cameras.videoOf", { name: camera.name, view: t(`cameras.${view}`) })}
        className="aspect-video rounded-lg"
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ViewToggle view={view} onChange={setView} />
        <Button type="button" size="xs" variant="outline" onClick={() => setFullscreen(true)}>
          <MaximizeIcon aria-hidden />
          {t("cameras.fullscreen")}
        </Button>
      </div>
      <Dialog open={fullscreen} onOpenChange={setFullscreen}>
        <DialogContent className="max-w-[95vw] sm:max-w-[min(95vw,120rem)]">
          <DialogTitle>{camera.name}</DialogTitle>
          <DialogDescription>{where}</DialogDescription>
          <LiveStream
            urls={urls}
            label={t("cameras.videoOf", { name: camera.name, view: t(`cameras.${view}`) })}
            className="aspect-video rounded-lg"
          />
          <ViewToggle view={view} onChange={setView} />
        </DialogContent>
      </Dialog>
    </li>
  );
}

/** Open incidents keyed by camera so their tile can be highlighted (FR-MAP-006). */
async function fetchOpenIncidentsByCamera(): Promise<Map<string, string[]>> {
  const { data } = await api.GET("/incidents", {
    params: { query: { open_only: true, limit: 200 } },
  });
  const byCamera = new Map<string, string[]>();
  for (const incident of data?.items ?? []) {
    if (!incident.camera_id) continue;
    byCamera.set(incident.camera_id, [
      ...(byCamera.get(incident.camera_id) ?? []),
      incident.short_code,
    ]);
  }
  return byCamera;
}

export function CameraWall() {
  const { t } = useTranslation();
  const cameras = useCameras();
  const health = useQuery({
    queryKey: systemCamerasKey,
    queryFn: fetchSystemCameras,
    refetchInterval: 5_000,
  });
  const incidents = useQuery({
    queryKey: [...incidentsKey, "by-camera"],
    queryFn: fetchOpenIncidentsByCamera,
  });
  const healthById = new Map(health.data?.map((row) => [row.id, row]));
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-display-sm font-bold text-balance">{t("pages.ops.cameras.title")}</h1>
      {cameras.isError ? <p role="alert">{t("cameras.loadFailed")}</p> : null}
      {cameras.isPending ? (
        <Skeleton className="aspect-video w-full max-w-xl" />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {cameras.data?.map((camera) => {
            const row = healthById.get(camera.id);
            return (
              <CameraTile
                key={camera.id}
                camera={camera}
                status={tileStatus(row?.status ?? camera.status, row?.stale ?? false)}
                incidents={incidents.data?.get(camera.id) ?? []}
              />
            );
          })}
        </ul>
      )}
    </div>
  );
}
