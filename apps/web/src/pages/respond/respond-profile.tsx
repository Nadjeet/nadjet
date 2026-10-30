import { useTranslation } from "react-i18next";

import { useSession } from "@/lib/auth-store";
import { useSmsGateway } from "@/lib/incident-queries";

import { AlertsControl, InstallControl } from "./app-controls";
import { PendingActions } from "./pending-actions";

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-4">
      <h2 className="text-body-md font-bold">{title}</h2>
      {children}
    </section>
  );
}

/** Alerts, installation, the SMS fallback number and the offline queue. */
export function RespondProfile() {
  const { t } = useTranslation();
  const user = useSession()?.user;
  const gateway = useSmsGateway();
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-display-xs font-bold">{t("respond.profile.title")}</h1>
      {user ? (
        <p className="text-body-md">
          {user.display_name}
          {user.agency ? ` · ${t(`ops.agency.${user.agency}`)}` : ""}
        </p>
      ) : null}
      <Block title={t("respond.profile.alerts")}>
        <AlertsControl />
      </Block>
      <Block title={t("respond.profile.app")}>
        <InstallControl />
      </Block>
      <Block title={t("respond.profile.gateway")}>
        {gateway.data ? (
          <bdi dir="ltr" className="font-mono text-body-md">
            {gateway.data}
          </bdi>
        ) : (
          <p className="text-body-sm text-muted-foreground">{t("respond.sms.noNumber")}</p>
        )}
      </Block>
      <Block title={t("respond.profile.queue")}>
        <PendingActions />
        <p className="text-body-sm text-muted-foreground">{t("respond.profile.queueHint")}</p>
      </Block>
    </div>
  );
}
