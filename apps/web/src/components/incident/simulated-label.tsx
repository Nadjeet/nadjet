import { FlaskConicalIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

/** Marks simulated data (demo facilities, simulated cameras) so it is never taken as real. */
export function SimulatedLabel({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <span
      data-slot="simulated-label"
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border border-dashed border-ink-subtle bg-surface-soft px-2 py-0.5 text-body-xs font-medium text-ink-muted",
        className,
      )}
    >
      <FlaskConicalIcon aria-hidden className="size-3.5" />
      {t("simulated.label")}
    </span>
  );
}
