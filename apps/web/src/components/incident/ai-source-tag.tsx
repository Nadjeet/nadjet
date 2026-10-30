import { CpuIcon, ScaleIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export type AiSource = { kind: "rule" | "model"; id: string };

/** Shows where an AI value comes from: a rule name or a model id (PRD FR-VIS-021). */
export function AiSourceTag({ source, className }: { source: AiSource; className?: string }) {
  const { t } = useTranslation();
  const Icon = source.kind === "rule" ? ScaleIcon : CpuIcon;
  return (
    <span
      data-slot="ai-source-tag"
      title={t("ai.sourceLabel")}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full bg-accent px-3 py-1 text-body-xs font-medium text-accent-foreground",
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5 shrink-0" />
      <span className="shrink-0">{t(`ai.${source.kind}`)}</span>
      {/* Identifiers are technical names: never translated or mirrored. */}
      <bdi dir="ltr" className="truncate font-mono text-[0.7rem]">
        {source.id}
      </bdi>
    </span>
  );
}
