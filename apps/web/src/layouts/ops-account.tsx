import { LogOutIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Avatar } from "@/components/brand/avatar";
import { LanguagePicker } from "@/components/brand/language-picker";
import { LiveIndicator } from "@/components/brand/live-indicator";
import { Button } from "@/components/ui/button";
import { authStore, useSession } from "@/lib/auth-store";

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
            <Avatar />
            <span className="hidden flex-col leading-5 sm:flex">
              <span className="text-body-xs font-medium text-ink-muted">
                {t("common.welcomeBack")}
              </span>
              <span className="text-body-sm font-medium text-[#081021]">
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
