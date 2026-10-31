import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { AiStatusBadge } from "@/components/incident/ai-status";
import { PriorityBadge, type PriorityLevel } from "@/components/incident/priority-badge";
import { formatAge, useLabel } from "@/lib/format";
import { locationText } from "@/lib/incident-format";
import type { Incident, QueueFilters } from "@/lib/incident-queries";
import { cn } from "@/lib/utils";

/** Re-render every 30 s so ages stay current without refetching. */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

/** Figma queue tabs "All · P1 · P2 · P3": a segmented priority filter. */
export function PriorityTabs({
  filters,
  onChange,
}: {
  filters: QueueFilters;
  onChange: (filters: QueueFilters) => void;
}) {
  const { t } = useTranslation();
  const options = [undefined, 1, 2, 3, 4] as const;
  return (
    <div role="group" aria-label={t("ops.filters.priority")} className="flex flex-wrap gap-1.5">
      {options.map((level) => {
        const active = filters.priority === level;
        return (
          <button
            key={level ?? "all"}
            type="button"
            aria-pressed={active}
            onClick={() => onChange({ ...filters, priority: level })}
            className={cn(
              "h-7 rounded-md px-2.5 text-body-xs font-medium transition-colors focus-visible:shadow-focus",
              active
                ? level === undefined
                  ? "bg-ink text-white"
                  : "bg-primary text-white"
                : "bg-surface-strong text-ink-body hover:bg-accent hover:text-primary",
            )}
          >
            {level === undefined ? t("ops.console.allPriorities") : `P${level}`}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Figma "Queue Cards Stack": one card per incident, priority first (the API orders by
 * priority then recency, FR-MAP-002). Selecting a card fills the inspect panel; "Review" opens
 * the incident page.
 */
export function QueueCards({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: Incident[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const label = useLabel();
  const now = useNow();
  return (
    <ul className="flex flex-col gap-3" aria-label={t("ops.console.queue")}>
      {incidents.map((incident) => {
        const selected = incident.id === selectedId;
        return (
          <li key={incident.id}>
            <article
              aria-current={selected ? "true" : undefined}
              className={cn(
                "relative flex flex-col gap-2 rounded-lg border bg-card p-3.5 transition-colors",
                selected
                  ? "border-2 border-brand-indigo bg-brand-50/60 shadow-card"
                  : "border-border hover:border-brand-200",
              )}
            >
              <div className="flex items-center gap-2">
                <PriorityBadge level={incident.priority as PriorityLevel} compact />
                <button
                  type="button"
                  onClick={() => onSelect(incident.id)}
                  className="font-mono text-body-sm font-semibold text-ink after:absolute after:inset-0 after:rounded-lg focus-visible:outline-none focus-visible:after:shadow-focus"
                >
                  {incident.short_code}
                </button>
                <span className="ms-auto text-body-xs whitespace-nowrap text-primary">
                  {formatAge(incident.event_time, i18n.language, now)}
                </span>
              </div>
              <p className="text-body-sm font-medium text-ink">
                {label(`ops.type.${incident.type}`, incident.type)}
              </p>
              <p className="truncate text-body-xs text-ink-muted">{locationText(incident)}</p>
              <div className="flex items-end justify-between gap-2">
                <div className="flex min-w-0 flex-col gap-0.5 text-body-xs">
                  <span className="font-medium text-ink-body">
                    {label(`ops.source.${incident.source}`, incident.source)}
                  </span>
                  <AiStatusBadge
                    aiStatus={incident.ai_status}
                    verifier={incident.verifier_result}
                    className="text-ink-muted"
                  />
                </div>
                <Link
                  to="/ops/incidents/$incidentId"
                  params={{ incidentId: incident.id }}
                  className="relative z-10 inline-flex h-7 shrink-0 items-center rounded-md bg-brand-200/70 px-3 text-body-xs font-medium text-brand-700 transition-colors hover:bg-brand-200 focus-visible:shadow-focus"
                >
                  {t("ops.console.review")}
                  <span className="sr-only"> {incident.short_code}</span>
                </Link>
              </div>
            </article>
          </li>
        );
      })}
    </ul>
  );
}
