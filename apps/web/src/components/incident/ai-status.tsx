import { CircleHelpIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { Verifier } from "./ai-confidence";
import { cn } from "@/lib/utils";

import { isUncertain } from "./ai-confidence";

/** Graded AI status with an explicit "uncertain" mark (icon + text, never colour alone). */
export function AiStatusBadge({
  aiStatus,
  verifier,
  className,
}: {
  aiStatus: string | null;
  verifier: Verifier;
  className?: string;
}) {
  const { t } = useTranslation();
  if (aiStatus === null) {
    return <span className="text-muted-foreground">{t("ops.aiStatus.none")}</span>;
  }
  const uncertain = isUncertain(aiStatus, verifier);
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1.5", className)}>
      <span className="font-medium">
        {t(
          `ops.aiStatus.${aiStatus as "confirmed" | "probable" | "possible" | "insufficient_evidence"}`,
        )}
      </span>
      {uncertain ? (
        <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-muted-foreground px-2 py-0.5 text-body-xs text-muted-foreground">
          <CircleHelpIcon aria-hidden className="size-3" />
          {t("ops.uncertain")}
        </span>
      ) : null}
    </span>
  );
}
