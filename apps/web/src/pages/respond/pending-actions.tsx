import { CloudOffIcon, TriangleAlertIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { remove } from "@/lib/offline-queue";
import { usePendingActions } from "@/lib/use-pending";

/** What waits for a connection, and what the API refused; each can be removed. */
export function PendingActions({ incidentId }: { incidentId?: string }) {
  const { t } = useTranslation();
  const actions = usePendingActions(incidentId);
  if (actions.length === 0) return null;
  return (
    <section aria-labelledby="pending-title" className="flex flex-col gap-2">
      <h2 id="pending-title" className="flex items-center gap-2 text-body-md font-bold">
        <CloudOffIcon aria-hidden className="size-5" />
        {t("respond.pending.title")}
      </h2>
      <ul className="flex flex-col gap-2">
        {actions.map((action) => (
          <li
            key={action.id}
            className="flex flex-col gap-2 rounded-lg border border-border p-3 text-body-sm"
          >
            <span className="font-medium">
              <bdi dir="ltr" className="font-mono">
                {action.shortCode}
              </bdi>{" "}
              {action.kind === "status"
                ? t("respond.pending.status", { status: t(`respond.action.${action.status}`) })
                : t("respond.pending.triage", {
                    tag: t(`respond.triage.${action.casualty.triage_tag}`),
                  })}
            </span>
            {action.state === "failed" ? (
              <span role="alert" className="flex items-center gap-1 text-danger">
                <TriangleAlertIcon aria-hidden className="size-4" />
                {t("respond.pending.failed", { error: action.error ?? "" })}
              </span>
            ) : null}
            <Button
              variant="ghost"
              size="xs"
              className="w-fit"
              onClick={() => void remove(action.id)}
            >
              {t("respond.pending.discard")}
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
