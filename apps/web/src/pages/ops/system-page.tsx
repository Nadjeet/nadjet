import { useQuery } from "@tanstack/react-query";
import { CircleCheckIcon, CircleXIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "@/api";
import { AiSourceTag } from "@/components/incident/ai-source-tag";
import { SimulatedLabel } from "@/components/incident/simulated-label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { systemCamerasKey } from "@/live/keys";

import { fetchSystemCameras } from "./system-data";
import { SystemStatusCard } from "./system-status-card";

const STAGES = ["decode", "detect", "track", "annotate"] as const;

async function fetchAiStatus() {
  const { data, error } = await api.GET("/system/ai");
  if (!data) throw new Error(`system ai: ${JSON.stringify(error)}`);
  return data;
}

function AiCard() {
  const { t } = useTranslation();
  const { data, isPending, isError } = useQuery({
    queryKey: ["system", "ai"],
    queryFn: fetchAiStatus,
    refetchInterval: 15_000,
  });
  const available = data?.available === true;
  return (
    <Card>
      <CardHeader>
        <h2 className="text-body-lg font-semibold text-ink">{t("system.ai")}</h2>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-3">
        {isPending ? <p className="text-ink-muted">{t("system.checking")}</p> : null}
        {isError ? <p role="alert">{t("system.unreachable")}</p> : null}
        {data ? (
          <>
            <Badge variant={available ? "success" : "destructive"}>
              {available ? <CircleCheckIcon aria-hidden /> : <CircleXIcon aria-hidden />}
              {available ? t("system.aiAvailable") : t("system.aiUnavailable")}
            </Badge>
            {data.model ? <AiSourceTag source={{ kind: "model", id: data.model }} /> : null}
            {data.detail ? (
              <bdi dir="ltr" className="text-body-sm text-ink-muted">
                {data.detail}
              </bdi>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ms(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : value.toFixed(1);
}

function CamerasCard() {
  const { t } = useTranslation();
  const { data, isPending, isError } = useQuery({
    queryKey: systemCamerasKey,
    queryFn: fetchSystemCameras,
    refetchInterval: 5_000,
    // Age of the last frame when the data was fetched (select is not part of rendering).
    select: (rows) => {
      const now = Date.now();
      return rows.map((row) => ({
        ...row,
        frameAgeS: row.health?.last_frame_at
          ? Math.max(0, (now - Date.parse(row.health.last_frame_at)) / 1000)
          : null,
      }));
    },
  });
  return (
    <Card>
      <CardHeader>
        <h2 className="text-body-lg font-semibold text-ink">{t("system.cameras")}</h2>
      </CardHeader>
      <CardContent>
        {isPending ? <p className="text-ink-muted">{t("system.checking")}</p> : null}
        {isError ? <p role="alert">{t("system.unreachable")}</p> : null}
        {data ? (
          <div className="overflow-x-auto">
            <table className="w-full text-start text-body-sm">
              <caption className="sr-only">{t("system.cameras")}</caption>
              <thead>
                <tr className="border-b border-border text-ink-muted">
                  <th scope="col" className="py-2 pe-4 text-start">
                    {t("system.camera")}
                  </th>
                  <th scope="col" className="pe-4 text-start">
                    {t("system.state")}
                  </th>
                  <th scope="col" className="pe-4 text-start">
                    {t("system.fps")}
                  </th>
                  {STAGES.map((stage) => (
                    <th key={stage} scope="col" className="pe-4 text-start">
                      {t(`system.stage.${stage}`)}
                    </th>
                  ))}
                  <th scope="col" className="pe-4 text-start">
                    {t("system.queue")}
                  </th>
                  <th scope="col" className="pe-4 text-start">
                    {t("system.frameAge")}
                  </th>
                  <th scope="col" className="text-start">
                    {t("system.detector")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((row) => {
                  const health = row.health;
                  const state = row.stale
                    ? t("system.silent")
                    : health?.fault
                      ? t(`system.fault.${health.fault_reason ?? "stall"}`)
                      : t("system.healthy");
                  return (
                    <tr key={row.id} className="border-b border-border last:border-0">
                      <th scope="row" className="py-2 pe-4 text-start font-medium">
                        <span className="flex flex-wrap items-center gap-2">
                          {row.name}
                          {row.simulated ? <SimulatedLabel /> : null}
                        </span>
                      </th>
                      <td className="pe-4">
                        <Badge variant={row.stale || health?.fault ? "destructive" : "success"}>
                          {row.stale || health?.fault ? (
                            <CircleXIcon aria-hidden />
                          ) : (
                            <CircleCheckIcon aria-hidden />
                          )}
                          {state}
                        </Badge>
                      </td>
                      <td className="pe-4 font-mono">{health ? health.fps.toFixed(1) : "–"}</td>
                      {STAGES.map((stage) => (
                        <td key={stage} className="pe-4 font-mono">
                          {ms(health?.latency_ms?.[stage])}{" "}
                          {health?.latency_ms?.[stage] != null ? "ms" : ""}
                        </td>
                      ))}
                      <td className="pe-4 font-mono">{health?.queue_depth ?? "–"}</td>
                      <td className="pe-4 font-mono">
                        {row.frameAgeS === null ? "–" : `${row.frameAgeS.toFixed(1)} s`}
                      </td>
                      <td>
                        {health?.detector ? (
                          <AiSourceTag source={{ kind: "model", id: health.detector }} />
                        ) : (
                          "–"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function SystemPage() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-display-xs font-semibold text-ink text-balance">
        {t("pages.ops.system.title")}
      </h1>
      <SystemStatusCard />
      <AiCard />
      <CamerasCard />
    </div>
  );
}
