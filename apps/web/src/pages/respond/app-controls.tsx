import { BellIcon, CloudOffIcon, DownloadIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { usePushState } from "@/lib/push-context";
import { useInstallPrompt } from "@/lib/use-install-prompt";
import { useOnline } from "@/lib/use-online";

/** Push alerts: on, or one tap to turn them on (FR-RSP-005). */
export function AlertsControl() {
  const { t } = useTranslation();
  const { state, enable } = usePushState();
  if (state === "subscribed") {
    return <p className="text-body-sm">{t("respond.alerts.on")}</p>;
  }
  if (state === "unsupported" || state === "denied") {
    return (
      <p className="text-body-sm text-ink-muted">
        {t(state === "denied" ? "respond.alerts.denied" : "respond.alerts.unsupported")}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="text-body-sm">{t("respond.alerts.body")}</p>
      {state === "error" ? (
        <p role="alert" className="text-body-sm text-danger">
          {t("respond.alerts.error")}
        </p>
      ) : null}
      <Button className="w-fit" onClick={() => void enable()}>
        <BellIcon aria-hidden />
        {t("respond.alerts.enable")}
      </Button>
    </div>
  );
}

/** "Add to home screen" (FR-RSP-005). The browser offers the prompt only when it can install. */
export function InstallControl() {
  const { t } = useTranslation();
  const { available, installed, install } = useInstallPrompt();
  if (installed) return <p className="text-body-sm">{t("respond.install.done")}</p>;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-body-sm">{t("respond.install.body")}</p>
      {available ? (
        <Button className="w-fit" onClick={install}>
          <DownloadIcon aria-hidden />
          {t("respond.install.button")}
        </Button>
      ) : (
        <p className="text-body-xs text-ink-muted">{t("respond.install.manual")}</p>
      )}
    </div>
  );
}

export function OfflineBanner() {
  const { t } = useTranslation();
  if (useOnline()) return null;
  return (
    <p
      role="status"
      className="flex items-center gap-2 rounded-lg border border-dashed border-foreground/40 bg-muted px-4 py-3 text-body-sm"
    >
      <CloudOffIcon aria-hidden className="size-4 shrink-0" />
      {t("respond.offline")}
    </p>
  );
}
