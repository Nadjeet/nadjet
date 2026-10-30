import { LogOutIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LanguagePicker } from "@/components/brand/language-picker";
import { LiveIndicator } from "@/components/brand/live-indicator";
import { Button } from "@/components/ui/button";
import { authStore, useSession } from "@/lib/auth-store";

/** Live status, language and sign-out: shown in the header of every signed-in surface. */
export function AccountActions() {
  const { t } = useTranslation();
  const session = useSession();
  return (
    <div className="flex flex-wrap items-center gap-2">
      <LiveIndicator />
      <LanguagePicker />
      {session ? (
        <>
          <span className="hidden text-body-sm text-muted-foreground sm:inline">
            {t("common.signedInAs", { name: session.user.display_name })}
          </span>
          <Button variant="outline" size="xs" onClick={() => authStore.logout()}>
            <LogOutIcon aria-hidden className="rtl:-scale-x-100" />
            {t("common.logout")}
          </Button>
        </>
      ) : null}
    </div>
  );
}
