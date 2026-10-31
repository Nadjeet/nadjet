import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { AiStatusBadge } from "@/components/incident/ai-status";
import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { formatAge, useLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

import { locationText } from "@/lib/incident-format";
import type {
  CandidateSource,
  Incident,
  IncidentStatus,
  QueueFilters,
} from "@/lib/incident-queries";

const STATUSES: IncidentStatus[] = [
  "candidate",
  "verified",
  "dispatched",
  "acknowledged",
  "en_route",
  "on_scene",
  "transporting",
  "at_hospital",
  "closed",
  "rejected",
  "merged",
];
const SOURCES: CandidateSource[] = ["camera", "citizen", "operator"];
const ALL = "all";

function Filter({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-44">
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper">{children}</SelectContent>
      </Select>
    </div>
  );
}

export function QueueFiltersBar({
  filters,
  onChange,
}: {
  filters: QueueFilters;
  onChange: (filters: QueueFilters) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-3">
      <Filter
        id="filter-status"
        label={t("ops.filters.status")}
        value={filters.status}
        onChange={(status) => onChange({ ...filters, status: status as QueueFilters["status"] })}
      >
        <SelectItem value="open">{t("ops.filters.open")}</SelectItem>
        {STATUSES.map((status) => (
          <SelectItem key={status} value={status}>
            {t(`status.${status}`)}
          </SelectItem>
        ))}
      </Filter>
      <Filter
        id="filter-priority"
        label={t("ops.filters.priority")}
        value={filters.priority ? String(filters.priority) : ALL}
        onChange={(value) =>
          onChange({
            ...filters,
            priority: value === ALL ? undefined : (Number(value) as 1 | 2 | 3 | 4),
          })
        }
      >
        <SelectItem value={ALL}>{t("ops.filters.all")}</SelectItem>
        {([1, 2, 3, 4] as const).map((level) => (
          <SelectItem key={level} value={String(level)}>
            P{level} · {t(`priority.p${level}`)}
          </SelectItem>
        ))}
      </Filter>
      <Filter
        id="filter-source"
        label={t("ops.filters.source")}
        value={filters.source ?? ALL}
        onChange={(value) =>
          onChange({ ...filters, source: value === ALL ? undefined : (value as CandidateSource) })
        }
      >
        <SelectItem value={ALL}>{t("ops.filters.all")}</SelectItem>
        {SOURCES.map((source) => (
          <SelectItem key={source} value={source}>
            {t(`ops.source.${source}`)}
          </SelectItem>
        ))}
      </Filter>
    </div>
  );
}

/** Re-render every 30 s so the age column stays current without refetching. */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

/** Priority-sorted queue; the API already orders by priority then recency (FR-MAP-002). */
export function IncidentQueue({
  incidents,
  selectedId,
}: {
  incidents: Incident[];
  selectedId?: string;
}) {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  const now = useNow();
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[56rem] text-start text-body-sm">
        <caption className="sr-only">{t("ops.console.queue")}</caption>
        <thead className="bg-muted text-body-xs text-ink-muted">
          <tr>
            {(
              ["code", "priority", "type", "ai", "source", "location", "age", "reports"] as const
            ).map((col) => (
              <th key={col} scope="col" className="px-3 py-2 text-start font-medium">
                {t(`ops.col.${col}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <tr
              key={incident.id}
              aria-current={incident.id === selectedId ? "true" : undefined}
              className={cn(
                "border-t border-border align-middle",
                incident.id === selectedId && "bg-accent",
              )}
            >
              <th scope="row" className="px-3 py-2 text-start font-mono font-bold">
                <Link
                  to="/ops/incidents/$incidentId"
                  params={{ incidentId: incident.id }}
                  className="rounded-sm underline-offset-4 hover:underline focus-visible:shadow-focus"
                >
                  {incident.short_code}
                </Link>
              </th>
              <td className="px-3 py-2">
                <PriorityBadge level={incident.priority as PriorityLevel} compact />
              </td>
              <td className="px-3 py-2">{label(`ops.type.${incident.type}`, incident.type)}</td>
              <td className="px-3 py-2">
                <AiStatusBadge aiStatus={incident.ai_status} verifier={incident.verifier_result} />
              </td>
              <td className="px-3 py-2">
                {label(`ops.source.${incident.source}`, incident.source)}
              </td>
              <td className="px-3 py-2">{locationText(incident)}</td>
              <td className="px-3 py-2 whitespace-nowrap">
                {formatAge(incident.event_time, i18n.language, now)}
              </td>
              <td className="px-3 py-2">{incident.report_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
