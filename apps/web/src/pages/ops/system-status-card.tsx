import { useQuery } from "@tanstack/react-query";
import { CircleCheckIcon, CircleXIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "@/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Readiness = {
  status: string;
  dependencies: Record<string, { ok: boolean; detail: string }>;
};

async function fetchReadiness(): Promise<Readiness> {
  const { data, error, response } = await api.GET("/ready");
  // /ready answers 503 with the same body shape when a dependency is down.
  const body = (data ?? error) as Readiness | undefined;
  if (!body?.dependencies) throw new Error(`API answered HTTP ${response.status}`);
  return body;
}

export function SystemStatusCard() {
  const { t } = useTranslation();
  const { data, isPending, isError } = useQuery({
    queryKey: ["ready"],
    queryFn: fetchReadiness,
    refetchInterval: 15_000,
  });
  return (
    <Card aria-labelledby="system-status-title">
      <CardHeader>
        <CardTitle id="system-status-title">{t("system.title")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isPending ? <p className="text-muted-foreground">{t("system.checking")}</p> : null}
        {isError ? <p role="alert">{t("system.unreachable")}</p> : null}
        {data ? (
          <ul className="flex flex-col gap-2">
            {Object.entries(data.dependencies).map(([name, dependency]) => (
              <li key={name} className="flex flex-wrap items-center gap-3">
                <span
                  className={
                    dependency.ok
                      ? "inline-flex items-center gap-1.5 font-medium text-success dark:text-emerald-400"
                      : "inline-flex items-center gap-1.5 font-medium text-danger dark:text-red-400"
                  }
                >
                  {dependency.ok ? (
                    <CircleCheckIcon aria-hidden className="size-4" />
                  ) : (
                    <CircleXIcon aria-hidden className="size-4" />
                  )}
                  {dependency.ok ? t("system.ok") : t("system.down")}
                </span>
                <bdi dir="ltr" className="font-mono text-body-sm">
                  {name}
                </bdi>
                <bdi dir="ltr" className="text-body-sm text-muted-foreground">
                  {dependency.detail}
                </bdi>
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
