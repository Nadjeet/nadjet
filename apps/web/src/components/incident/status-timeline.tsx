import { CheckIcon, CircleDotIcon, CircleIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { LIFECYCLE, type TimelineStatus, type TimelineStep } from "./lifecycle";

/** Algeria writes Arabic with Latin digits: `ar-DZ`, not `ar`. */
const DATE_LOCALES: Record<string, string> = { ar: "ar-DZ", fr: "fr-DZ", en: "en-GB" };

function formatTime(iso: string, language: string): string {
  return new Intl.DateTimeFormat(DATE_LOCALES[language] ?? language, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(iso));
}

/**
 * Vertical timeline. A step is done when it appears in `steps` before `current`; state is
 * shown by icon and text, not by colour alone.
 */
export function StatusTimeline({
  steps,
  current,
  className,
}: {
  steps: TimelineStep[];
  current: TimelineStatus;
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  const reached = new Map(steps.map((step) => [step.status, step.at]));
  const currentIndex = LIFECYCLE.indexOf(current);
  return (
    <ol aria-label={t("timeline.label")} className={cn("flex flex-col", className)}>
      {LIFECYCLE.map((status, index) => {
        const done = index < currentIndex && reached.has(status);
        const active = index === currentIndex;
        const at = reached.get(status);
        const Icon = done ? CheckIcon : active ? CircleDotIcon : CircleIcon;
        return (
          <li
            key={status}
            aria-current={active ? "step" : undefined}
            className="relative flex gap-3 pb-5 last:pb-0"
          >
            {index < LIFECYCLE.length - 1 ? (
              <span
                aria-hidden
                className={cn(
                  "absolute start-3 top-7 -ms-px h-[calc(100%-1.75rem)] w-0.5",
                  done ? "bg-primary" : "bg-border",
                )}
              />
            ) : null}
            <span
              aria-hidden
              className={cn(
                "z-10 flex size-6 shrink-0 items-center justify-center rounded-full border-2",
                done && "border-primary bg-primary text-primary-foreground",
                active && "border-primary bg-background text-primary",
                !done && !active && "border-muted-foreground bg-background text-muted-foreground",
              )}
            >
              <Icon className="size-3.5" />
            </span>
            <div className="flex min-w-0 flex-col">
              <span className={cn("text-body-sm", active ? "font-bold" : "font-medium")}>
                {t(`status.${status}`)}
              </span>
              <span className="text-body-xs text-muted-foreground">
                {at ? (
                  <>
                    {done ? <span className="sr-only">{t("timeline.done")} · </span> : null}
                    {formatTime(at, i18n.language)}
                  </>
                ) : done ? (
                  t("timeline.done")
                ) : active ? (
                  t("timeline.current")
                ) : (
                  t("timeline.pending")
                )}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
