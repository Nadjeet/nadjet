import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export type View = "raw" | "annotated";

/** Figma "Raw | Annotated" segmented switch. */
export function ViewSwitch({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="group"
      aria-label={t("cameras.view")}
      className="inline-flex rounded-md border border-border bg-card p-0.5 text-body-xs"
    >
      {(["raw", "annotated"] as const).map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={view === option}
          onClick={() => onChange(option)}
          className={cn(
            "rounded-[5px] px-2 py-0.5 font-medium transition-colors focus-visible:shadow-focus",
            view === option ? "bg-accent text-primary" : "text-ink-muted hover:text-ink",
          )}
        >
          {t(`cameras.${option}`)}
        </button>
      ))}
    </div>
  );
}
