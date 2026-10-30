import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

/** Placeholder brand mark (public/logo-mark.svg). Decorative: the wordmark carries the name. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <img src="/logo-mark.svg" alt="" aria-hidden className={cn("size-10 shrink-0", className)} />
  );
}

/** Mark and wordmark. The wordmark follows the active language (نجاة in Arabic). */
export function Logo({ className, showName = true }: { className?: string; showName?: boolean }) {
  const { t } = useTranslation();
  return (
    <span className={cn("inline-flex items-center gap-3", className)}>
      <LogoMark />
      {showName ? (
        <span className="text-display-xs font-bold tracking-tight">{t("app.name")}</span>
      ) : (
        <span className="sr-only">{t("app.name")}</span>
      )}
    </span>
  );
}
