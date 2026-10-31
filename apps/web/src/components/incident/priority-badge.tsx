import { CircleAlertIcon, InfoIcon, OctagonAlertIcon, TriangleAlertIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export type PriorityLevel = 1 | 2 | 3 | 4;

const STYLE = {
  1: { icon: OctagonAlertIcon, className: "bg-p1" },
  2: { icon: TriangleAlertIcon, className: "bg-p2" },
  3: { icon: CircleAlertIcon, className: "bg-p3" },
  4: { icon: InfoIcon, className: "bg-p4" },
} as const;

/**
 * P1–P4 with a distinct icon, the level and its name. Colour is a reinforcement only
 * (PRD NFR-INT-002); white text on each background is at least 4.5:1 (see apps/web/README.md).
 */
export function PriorityBadge({
  level,
  className,
  compact = false,
}: {
  level: PriorityLevel;
  className?: string;
  /** Hide the name and keep level + icon (the name stays available to screen readers). */
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const { icon: Icon, className: tone } = STYLE[level];
  const name = t(`priority.p${level}`);
  return (
    <span
      data-slot="priority-badge"
      data-level={level}
      className={cn(
        "inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-body-xs font-semibold text-white",
        tone,
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      <span>P{level}</span>
      <span className={cn("font-medium", compact && "sr-only")}>{name}</span>
    </span>
  );
}
