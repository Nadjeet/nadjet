import { CircleCheckIcon, TriangleAlertIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useSetReadiness, type ReadyState } from "@/lib/hospital-queries";
import { cn } from "@/lib/utils";

/**
 * Ready / Divert for the whole hospital (FR-HSP-002): the state dispatch ranks by. Ready is one
 * tap; Divert asks to confirm because it alerts the operators (E-10). The SMS equivalent is
 * shown so the hospital can answer without the screen.
 */
export function ReadinessPanel({
  facilityId,
  state,
  exampleCode,
}: {
  facilityId: string;
  state: ReadyState;
  exampleCode: string;
}) {
  const { t } = useTranslation();
  const setReadiness = useSetReadiness(facilityId);
  const [confirming, setConfirming] = useState(false);
  const busy = setReadiness.isPending;

  return (
    <section
      aria-labelledby="readiness-title"
      className="flex flex-col gap-4 rounded-2xl bg-white p-5 shadow-card"
    >
      <h2 id="readiness-title" className="text-body-md font-medium text-ink">
        {t("hospital.readiness.title")}
      </h2>
      <div className="flex flex-wrap items-stretch gap-3">
        <Button
          size="lg"
          variant={state === "ready" ? "success-solid" : "success"}
          aria-pressed={state === "ready"}
          className="min-w-36 flex-1"
          disabled={busy}
          onClick={() => state !== "ready" && setReadiness.mutate("ready")}
        >
          <CircleCheckIcon aria-hidden className="size-5" />
          {t("hospital.readiness.ready")}
        </Button>
        <Button
          size="lg"
          variant={state === "divert" ? "destructive" : "neutral"}
          aria-pressed={state === "divert"}
          className="min-w-36 flex-1"
          disabled={busy}
          onClick={() => state !== "divert" && setConfirming(true)}
        >
          <TriangleAlertIcon aria-hidden className="size-5" />
          {t("hospital.readiness.divert")}
        </Button>
      </div>
      <p
        role="status"
        className={cn(
          "flex items-start gap-2 rounded-md px-3 py-2 text-body-sm",
          state === "ready"
            ? "bg-success-soft text-success-text"
            : "bg-danger-soft text-danger-strong",
        )}
      >
        {state === "ready" ? t("hospital.readiness.nowReady") : t("hospital.readiness.nowDivert")}
      </p>
      {setReadiness.isError ? (
        <p role="alert" className="text-body-sm text-danger-strong">
          {t("hospital.error")}
        </p>
      ) : null}
      <p className="text-body-xs text-ink-muted">
        {t("hospital.readiness.sms")}{" "}
        <bdi dir="ltr" className="font-mono">
          H {exampleCode} READY
        </bdi>
        {" · "}
        <bdi dir="ltr" className="font-mono">
          H {exampleCode} DIVERT
        </bdi>
      </p>

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("hospital.readiness.confirmTitle")}</DialogTitle>
            <DialogDescription>{t("hospital.readiness.confirmBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              {t("respond.action.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() =>
                setReadiness.mutate("divert", { onSuccess: () => setConfirming(false) })
              }
            >
              {t("hospital.readiness.divert")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
