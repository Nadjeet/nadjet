import { RadioIcon, RefreshCwIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useLiveEvents } from "@/live/live-events-context";
import { cn } from "@/lib/utils";

/** "Live / reconnecting" indicator (text + icon + colour, announced politely to screen readers). */
export function LiveIndicator({ className }: { className?: string }) {
  const { t } = useTranslation();
  const status = useLiveEvents();
  const live = status === "live";
  return (
    <span
      role="status"
      aria-live="polite"
      data-status={status}
      title={t("live.label")}
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-3 py-1 text-body-xs font-medium",
        live ? "bg-success text-white" : "bg-muted text-foreground ring-1 ring-border",
        className,
      )}
    >
      {live ? (
        <RadioIcon aria-hidden className="size-3.5" />
      ) : (
        <RefreshCwIcon aria-hidden className="size-3.5 motion-safe:animate-spin" />
      )}
      {t(`live.${status}`)}
    </span>
  );
}
