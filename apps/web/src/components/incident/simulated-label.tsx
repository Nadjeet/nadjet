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
        "inline-flex items-center gap-1.5 rounded-full border border-dashed border-muted-foreground px-3 py-1 text-body-xs font-medium text-muted-foreground",
        className,
      )}
    >
      <FlaskConicalIcon aria-hidden className="size-3.5" />
      {t("simulated.label")}
    </span>
  );
}
