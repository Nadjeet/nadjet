import { useQuery } from "@tanstack/react-query";
import { Maximize2Icon, Minimize2Icon, SearchIcon, VideoOffIcon } from "lucide-react";
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "@/api";
import { SimulatedLabel } from "@/components/incident/simulated-label";
import { LiveStream } from "@/components/stream/live-stream";
import { ViewSwitch } from "@/components/stream/view-switch";
import { Skeleton } from "@/components/ui/skeleton";
import { incidentsKey, systemCamerasKey } from "@/live/keys";
import { useCameras } from "@/lib/incident-queries";
import { cn } from "@/lib/utils";

import { streamUrls, tileStatus, type Camera, type TileStatus, type View } from "./camera-status";
import { fetchSystemCameras } from "./system-data";

/** A grid cell in layout units (columns x rows of the stage). */
type Cell = { x: number; y: number; w: number; h: number };
type LayoutName = "single" | "grid4" | "focus" | "grid9";

const LAYOUTS: Record<LayoutName, Cell[]> = {
  single: [{ x: 0, y: 0, w: 1, h: 1 }],
  grid4: [
    { x: 0, y: 0, w: 1, h: 1 },
    { x: 1, y: 0, w: 1, h: 1 },
    { x: 0, y: 1, w: 1, h: 1 },
    { x: 1, y: 1, w: 1, h: 1 },
  ],
  focus: [
    { x: 0, y: 0, w: 3, h: 2 },
    { x: 0, y: 2, w: 1, h: 1 },
    { x: 1, y: 2, w: 1, h: 1 },
    { x: 2, y: 2, w: 1, h: 1 },
  ],
  grid9: Array.from({ length: 9 }, (_, i) => ({ x: i % 3, y: Math.floor(i / 3), w: 1, h: 1 })),
};
const LAYOUT_NAMES = Object.keys(LAYOUTS) as LayoutName[];

const STATUS_DOT: Record<TileStatus, string> = {
  live: "bg-success",
  degraded: "bg-warning",
  offline: "bg-ink-subtle",
};

function span(cells: Cell[]): { columns: number; rows: number } {
  return {
    columns: Math.max(...cells.map((c) => c.x + c.w)),
    rows: Math.max(...cells.map((c) => c.y + c.h)),
  };
}

/** Small drawing of a layout for its picker button. */
function LayoutIcon({ cells, active }: { cells: Cell[]; active: boolean }) {
  const { columns, rows } = span(cells);
  const w = 28 / columns;
  const h = 22 / rows;
  return (
    <svg aria-hidden viewBox="0 0 30 24" className="h-6 w-7.5">
      {cells.map((c, i) => (
        <rect
          key={i}
          x={1 + c.x * w + 0.75}
          y={1 + c.y * h + 0.75}
          width={c.w * w - 1.5}
          height={c.h * h - 1.5}
          rx={1.5}
          className={active ? "fill-brand-500" : "fill-surface-strong stroke-ink-subtle"}
          strokeWidth={0.8}
        />
      ))}
    </svg>
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

function where(camera: Camera): string {
  return camera.pk_km === null ? camera.road : `${camera.road} PK ${camera.pk_km}`;
}

/**
 * One surveillance tile: a thin header bar (status dot, id and name, open incident) over the
 * live video. The selected tile has a blue frame, a tile with an open incident a red one.
 */
function CameraTile({
  camera,
  status,
  incidents,
  view,
  selected,
  onSelect,
  onEnlarge,
}: {
  camera: Camera;
  status: TileStatus;
  incidents: string[];
  view: View;
  selected: boolean;
  onSelect: () => void;
  onEnlarge: (event: MouseEvent<HTMLDivElement>) => void;
}) {
  const { t } = useTranslation();
  const alert = incidents.length > 0;
  // The AI boxes stream only exists while the camera's worker runs: fall back to raw video.
  const shown: View = view === "annotated" && status !== "live" ? "raw" : view;
  return (
    <div
      className={cn(
        "flex size-full min-h-0 min-w-0 flex-col overflow-hidden rounded-md border-2 bg-black",
        alert ? "border-danger" : selected ? "border-brand-500" : "border-white/10",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className={cn(
          "flex h-7 shrink-0 items-center gap-2 px-2.5 text-start text-[0.6875rem] focus-visible:shadow-focus",
          alert
            ? "bg-danger text-white"
            : selected
              ? "bg-brand-500 text-white"
              : "bg-ink text-white/75",
        )}
      >
        <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", STATUS_DOT[status])} />
        <bdi dir="ltr" className="shrink-0 font-medium">
          {camera.id}
        </bdi>
        <span className="truncate opacity-80">· {camera.name}</span>
        <span className="sr-only">{t(`cameras.status.${status}`)}</span>
        {alert ? (
          <span className="ms-auto shrink-0 rounded bg-white px-1.5 font-semibold text-danger">
            <bdi dir="ltr">INC-{incidents[0]}</bdi>
          </span>
        ) : (
          <span className="ms-auto flex shrink-0 items-center gap-1 font-semibold tracking-wide">
            <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-danger" />
            {t("cameras.liveTag")}
          </span>
        )}
      </button>
      <div className="relative min-h-0 flex-1 select-none" onDoubleClick={onEnlarge}>
        <LiveStream
          key={`${camera.id}-${shown}`}
          urls={streamUrls(camera.stream, shown)}
          label={t("cameras.videoOf", { name: camera.name, view: t(`cameras.${shown}`) })}
          className="size-full"
        />
        {shown !== view ? (
          <span className="pointer-events-none absolute start-2 top-2 rounded bg-warning px-1.5 py-0.5 text-[0.625rem] font-medium text-ink">
            {t("cameras.aiUnavailable")}
          </span>
        ) : null}
        <span className="pointer-events-none absolute end-2 top-2 rounded bg-black/55 px-1.5 py-0.5 text-[0.625rem] text-white/90 backdrop-blur-sm">
          <bdi dir="ltr">{where(camera)}</bdi> · {camera.wilaya}
        </span>
      </div>
    </div>
  );
}

function EmptySlot() {
  const { t } = useTranslation();
  return (
    <div className="flex size-full min-h-0 flex-col overflow-hidden rounded-md border-2 border-white/10">
      <p className="flex h-7 shrink-0 items-center bg-ink px-2.5 text-[0.6875rem] text-white/50">
        {t("cameras.emptySlot")}
      </p>
      <div className="grid flex-1 place-items-center bg-[#111827] text-white/25">
        <VideoOffIcon aria-hidden className="size-10" />
      </div>
    </div>
  );
}

/**
 * Camera wall in the style of a surveillance video wall: a dark stage of edge-to-edge tiles,
 * a layout bar (1, 2x2, 1+3, 3x3) with the Raw / AI boxes switch and full screen, and the camera
 * list on the side. Double-click a tile to enlarge it; click a camera to select it (FR-CAM-003,
 * FR-MAP-006).
 */
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
  const [layout, setLayout] = useState<LayoutName>("grid4");
  const [view, setView] = useState<View>("annotated");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [enlargedId, setEnlargedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const stage = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    const sync = () => setFullscreen(document.fullscreenElement === stage.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  const healthById = new Map(health.data?.map((row) => [row.id, row]));
  const statusOf = (camera: Camera): TileStatus => {
    if (camera.live_demo) return tileStatus(camera.status, false);
    const row = healthById.get(camera.id);
    return tileStatus(row?.status ?? camera.status, row?.stale ?? false);
  };
  const list = cameras.data ?? [];
  const incidentsOf = (id: string) => incidents.data?.get(id) ?? [];

  // Cameras with an open incident come first and offline ones last; the selected camera takes
  // the first (largest) slot of the single and focus layouts.
  const rank = (camera: Camera) =>
    incidentsOf(camera.id).length > 0 ? 0 : statusOf(camera) === "offline" ? 2 : 1;
  const sorted = [...list].sort((a, b) => rank(a) - rank(b));
  const first = sorted.find((c) => c.id === selectedId);
  const ordered =
    first && (layout === "single" || layout === "focus")
      ? [first, ...sorted.filter((c) => c.id !== first.id)]
      : sorted;

  const cells = LAYOUTS[layout];
  const { columns, rows } = span(cells);
  const enlarged = list.find((c) => c.id === enlargedId);
  const liveCount = list.filter((c) => statusOf(c) === "live").length;
  const needle = query.trim().toLowerCase();
  const filtered = needle
    ? sorted.filter((c) =>
        [c.id, c.name, c.road, c.wilaya].some((v) => v.toLowerCase().includes(needle)),
      )
    : sorted;

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void stage.current?.requestFullscreen();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-body-xl leading-7 font-semibold text-ink">
          {t("pages.ops.cameras.title")}
        </h1>
        {cameras.data ? (
          <span className="rounded-md bg-success-soft px-2 py-0.5 text-body-xs text-success-text">
            {t("cameras.liveCount", { live: liveCount, total: list.length })}
          </span>
        ) : null}
        <span className="ms-auto text-body-xs text-ink-muted">{t("cameras.hint")}</span>
      </div>
      {cameras.isError ? <p role="alert">{t("cameras.loadFailed")}</p> : null}

      <div className="flex flex-col gap-4 xl:flex-row">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div
            ref={stage}
            className="relative h-[calc(100dvh-16rem)] min-h-[26rem] rounded-2xl bg-ink p-1.5 shadow-card"
          >
            {cameras.isPending ? (
              <Skeleton className="size-full rounded-xl bg-white/10" />
            ) : enlarged ? (
              <CameraTile
                camera={enlarged}
                status={statusOf(enlarged)}
                incidents={incidentsOf(enlarged.id)}
                view={view}
                selected
                onSelect={() => setSelectedId(enlarged.id)}
                onEnlarge={() => setEnlargedId(null)}
              />
            ) : (
              <div
                className="grid size-full gap-1.5"
                style={{
                  gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
                  gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
                }}
              >
                {cells.map((cell, index) => {
                  const camera = ordered[index];
                  return (
                    <div
                      key={index}
                      className="min-h-0 min-w-0"
                      style={{
                        gridColumn: `${cell.x + 1} / span ${cell.w}`,
                        gridRow: `${cell.y + 1} / span ${cell.h}`,
                      }}
                    >
                      {camera ? (
                        <CameraTile
                          camera={camera}
                          status={statusOf(camera)}
                          incidents={incidentsOf(camera.id)}
                          view={view}
                          selected={camera.id === selectedId}
                          onSelect={() => setSelectedId(camera.id)}
                          onEnlarge={() => setEnlargedId(camera.id)}
                        />
                      ) : (
                        <EmptySlot />
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-white px-4 py-2.5 shadow-card">
            <div role="group" aria-label={t("cameras.layout")} className="flex items-center gap-1">
              {LAYOUT_NAMES.map((name) => (
                <button
                  key={name}
                  type="button"
                  aria-pressed={layout === name}
                  title={t(`cameras.layouts.${name}`)}
                  onClick={() => {
                    setLayout(name);
                    setEnlargedId(null);
                  }}
                  className={cn(
                    "rounded-md p-1 transition-colors focus-visible:shadow-focus",
                    layout === name ? "bg-brand-50" : "hover:bg-surface-strong",
                  )}
                >
                  <LayoutIcon cells={LAYOUTS[name]} active={layout === name} />
                  <span className="sr-only">{t(`cameras.layouts.${name}`)}</span>
                </button>
              ))}
            </div>
            <span aria-hidden className="h-6 w-px bg-line" />
            <ViewSwitch view={view} onChange={setView} />
            <button
              type="button"
              onClick={toggleFullscreen}
              className="ms-auto inline-flex h-9 items-center gap-2 rounded-xl bg-surface-strong px-3 text-body-xs font-medium text-ink transition-colors hover:bg-line focus-visible:shadow-focus"
            >
              {fullscreen ? (
                <Minimize2Icon aria-hidden className="size-4" />
              ) : (
                <Maximize2Icon aria-hidden className="size-4" />
              )}
              {fullscreen ? t("cameras.exitFullscreen") : t("cameras.fullscreen")}
            </button>
          </div>
        </div>

        <aside
          aria-labelledby="camera-list-title"
          className="flex w-full shrink-0 flex-col gap-3 rounded-2xl bg-white p-4 shadow-card xl:w-[17rem]"
        >
          <h2 id="camera-list-title" className="text-body-md font-medium text-ink">
            {t("cameras.list")}
          </h2>
          <label className="relative">
            <span className="sr-only">{t("cameras.search")}</span>
            <SearchIcon
              aria-hidden
              className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-ink-subtle"
            />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("cameras.search")}
              className="h-10 w-full rounded-xl bg-input ps-9 pe-3 text-body-sm text-ink outline-none placeholder:text-ink-subtle focus-visible:shadow-focus"
            />
          </label>
          <ul className="flex flex-col gap-2">
            {filtered.map((camera) => {
              const status = statusOf(camera);
              const open = incidentsOf(camera.id);
              const selected = camera.id === selectedId;
              return (
                <li key={camera.id}>
                  <button
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setSelectedId(camera.id)}
                    onDoubleClick={() => setEnlargedId(camera.id)}
                    className={cn(
                      "flex w-full flex-col gap-1 rounded-lg border p-3 text-start transition-colors focus-visible:shadow-focus",
                      selected
                        ? "border-2 border-brand-indigo bg-[rgb(239_246_255/0.4)]"
                        : "border-line hover:border-brand-200",
                    )}
                  >
                    <span className="flex items-center gap-1.5 text-body-xs font-semibold text-ink">
                      <span
                        aria-hidden
                        className={cn("size-1.5 shrink-0 rounded-full", STATUS_DOT[status])}
                      />
                      <bdi dir="ltr" className="truncate">
                        {camera.id}
                      </bdi>
                      <span className="ms-auto shrink-0 text-[0.625rem] font-normal text-ink-muted">
                        {t(`cameras.status.${status}`)}
                      </span>
                    </span>
                    <span className="truncate text-[0.6875rem] text-ink-body">{camera.name}</span>
                    <span className="flex items-center gap-1.5 text-[0.6875rem] text-ink-muted">
                      <bdi dir="ltr">{where(camera)}</bdi> · {camera.wilaya}
                    </span>
                    {open.length > 0 ? (
                      <span className="w-fit rounded-md bg-danger px-1.5 py-0.5 text-[0.625rem] text-white">
                        {t("cameras.openCount", { count: open.length })}
                      </span>
                    ) : null}
                    {camera.live_demo ? (
                      <span className="w-fit rounded-md bg-brand-50 px-1.5 py-0.5 text-[0.625rem] text-brand-indigo">
                        {t("cameras.liveDemo")}
                      </span>
                    ) : camera.simulated ? (
                      <SimulatedLabel className="w-fit" />
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>
      </div>
    </div>
  );
}
