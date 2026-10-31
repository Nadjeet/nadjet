import { useTranslation } from "react-i18next";

import logoUrl from "@/assets/brand/nadjet-logo.svg";
import { cn } from "@/lib/utils";

/** The mark alone (public/favicon.svg, cropped from the Figma logo): favicons and tight spots. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <img
      src="/favicon.svg"
      alt=""
      aria-hidden
      className={cn("size-9 shrink-0 object-contain", className)}
    />
  );
}

/**
 * The Nadjet logo from Figma (node 75:6347): Arabic and Latin wordmark with the mark. It already
 * shows both scripts, so it is the same in every language; the name is its text alternative.
 */
export function Logo({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <img
      src={logoUrl}
      alt={t("app.name")}
      width={195}
      height={52}
      className={cn("h-10 w-auto shrink-0", className)}
    />
  );
}
