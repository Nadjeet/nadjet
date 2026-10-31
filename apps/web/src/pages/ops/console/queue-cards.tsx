import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

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
              "h-[26px] min-w-8 rounded-md px-2.5 text-[0.6875rem] transition-colors focus-visible:shadow-focus",
              active
                ? level === undefined
                  ? "bg-ink text-white"
                  : "bg-brand-400 text-white"
                : "bg-surface-strong text-ink-body hover:bg-line",
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
    <ul className="flex flex-col gap-5" aria-label={t("ops.console.queue")}>
      {incidents.map((incident) => {
        const selected = incident.id === selectedId;
        return (
          <li key={incident.id}>
            <article
              aria-current={selected ? "true" : undefined}
              className={cn(
                "relative flex flex-col gap-2 rounded-lg border p-3.5 transition-colors",
                selected
                  ? "border-2 border-brand-indigo bg-[rgb(239_246_255/0.4)] shadow-card"
                  : "border-line bg-white hover:border-brand-200",
              )}
            >
              <div className="flex items-center gap-1.5">
                {incident.priority === 1 ? (
                  <span className="rounded-md bg-danger px-1 py-0.5 text-[0.625rem] leading-[0.9rem] text-white">
                    {t("priority.p1")}
                  </span>
                ) : (
                  <PriorityBadge level={incident.priority as PriorityLevel} compact />
                )}
                <button
                  type="button"
                  onClick={() => onSelect(incident.id)}
                  className="text-body-xs font-semibold text-ink after:absolute after:inset-0 after:rounded-lg focus-visible:outline-none focus-visible:after:shadow-focus"
                >
                  <bdi dir="ltr">INC-{incident.short_code}</bdi>
                </button>
                <span className="ms-auto text-body-xs whitespace-nowrap text-brand-500">
                  {formatAge(incident.event_time, i18n.language, now)}
                </span>
              </div>
              <p className="text-body-xs text-ink">
                {label(`ops.type.${incident.type}`, incident.type)}
              </p>
              <p className="truncate text-[0.6875rem] text-ink-muted">{locationText(incident)}</p>
              <div className="flex items-end justify-between gap-2">
                {incident.status === "candidate" || incident.status === "verified" ? (
                  <span className="flex items-center gap-1.5 text-[0.6875rem] leading-tight text-danger-strong">
                    <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-danger-strong" />
                    {t(`status.${incident.status}`)}
                  </span>
                ) : (
                  <span className="text-[0.6875rem] leading-tight text-brand-900">
                    {label(`ops.source.${incident.source}`, incident.source)} ·{" "}
                    {t(`status.${incident.status}`)}
                  </span>
                )}
                <Link
                  to="/ops/incidents/$incidentId"
                  params={{ incidentId: incident.id }}
                  className="relative z-10 inline-flex h-6 shrink-0 items-center rounded-md bg-brand-200 px-3.5 text-body-xs text-white transition-colors hover:bg-brand-300 focus-visible:shadow-focus"
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
