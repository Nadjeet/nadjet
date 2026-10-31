import { LogOutIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LanguagePicker } from "@/components/brand/language-picker";
import { LiveIndicator } from "@/components/brand/live-indicator";
import { Button } from "@/components/ui/button";
import { authStore, useSession } from "@/lib/auth-store";

/** Initials of a display name (no photos are stored: privacy by design). */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? parts[0]![0]! + parts.at(-1)![0]! : name.slice(0, 2)).toUpperCase();
}

/** Figma "Welcome back" block: avatar, greeting and name, plus live status, language, sign-out. */
export function OpsAccount() {
  const { t } = useTranslation();
  const session = useSession();
  return (
    <div className="flex flex-wrap items-center gap-2 sm:gap-3">
      <LiveIndicator />
      <LanguagePicker />
      {session ? (
        <>
          <div className="flex items-center gap-3 ps-1">
            <span
              aria-hidden
              className="grid size-10 place-items-center rounded-full bg-[linear-gradient(135deg,#3568f5,#55a8fe)] text-body-sm font-semibold text-white"
            >
              {initials(session.user.display_name)}
            </span>
            <span className="hidden flex-col leading-tight sm:flex">
              <span className="text-body-xs text-ink-muted">{t("common.welcomeBack")}</span>
              <span className="text-body-md font-semibold text-ink">
                {session.user.display_name}
              </span>
            </span>
          </div>
          <Button
            variant="neutral"
            size="icon-sm"
            onClick={() => authStore.logout()}
            aria-label={t("common.logout")}
            title={t("common.logout")}
          >
            <LogOutIcon aria-hidden className="rtl:-scale-x-100" />
          </Button>
        </>
      ) : null}
    </div>
  );
}
