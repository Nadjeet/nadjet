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
      className="flex flex-col gap-4 rounded-3xl border border-border bg-card p-5"
    >
      <h2 id="readiness-title" className="text-body-xl font-bold">
        {t("hospital.readiness.title")}
      </h2>
      <div className="flex flex-wrap items-stretch gap-3">
        <Button
          size="lg"
          variant={state === "ready" ? "success" : "outline"}
          aria-pressed={state === "ready"}
          className="h-16 min-w-44 flex-1 text-body-xl"
          disabled={busy}
          onClick={() => state !== "ready" && setReadiness.mutate("ready")}
        >
          <CircleCheckIcon aria-hidden className="size-6" />
          {t("hospital.readiness.ready")}
        </Button>
        <Button
          size="lg"
          variant={state === "divert" ? "destructive" : "outline"}
          aria-pressed={state === "divert"}
          className={cn("h-16 min-w-44 flex-1 text-body-xl")}
          disabled={busy}
          onClick={() => state !== "divert" && setConfirming(true)}
        >
          <TriangleAlertIcon aria-hidden className="size-6" />
          {t("hospital.readiness.divert")}
        </Button>
      </div>
      <p role="status" className="text-body-lg font-medium">
        {state === "ready" ? t("hospital.readiness.nowReady") : t("hospital.readiness.nowDivert")}
      </p>
      {setReadiness.isError ? (
        <p role="alert" className="text-body-md text-danger">
          {t("hospital.error")}
        </p>
      ) : null}
      <p className="text-body-md text-muted-foreground">
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
