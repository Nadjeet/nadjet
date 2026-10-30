import { useQueryClient } from "@tanstack/react-query";
import { CheckIcon, CircleDotIcon, CircleIcon } from "lucide-react";
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
import { useSession } from "@/lib/auth-store";
import type { IncidentDetail } from "@/lib/incident-queries";
import { submitAction } from "@/lib/responder-actions";
import { statusSms, type ResponderStatus } from "@/lib/sms-codes";
import { usePendingActions } from "@/lib/use-pending";
import { cn } from "@/lib/utils";

import { SmsButton } from "./sms-button";

const STEPS: ResponderStatus[] = [
  "acknowledged",
  "en_route",
  "on_scene",
  "transporting",
  "at_hospital",
  "closed",
];
const NEXT: Record<string, ResponderStatus | undefined> = {
  dispatched: "acknowledged",
  acknowledged: "en_route",
  en_route: "on_scene",
  on_scene: "transporting",
  transporting: "at_hospital",
  at_hospital: "closed",
};

/**
 * One big button for the next step, in the lifecycle order (FR-RSP-002). Acknowledge, en route,
 * on scene, transporting and at hospital are one tap; closing asks to confirm (two taps).
 * Offline, the step is saved on the phone and shown as reached; the SMS button sends the code.
 */
export function StatusActions({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const userId = useSession()?.user.id ?? "";
  const pending = usePendingActions(incident.id).filter(
    (a) => a.kind === "status" && a.state === "pending",
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<ResponderStatus | null>(null);

  const last = [...pending].reverse().find((a) => a.kind === "status");
  const effective = last?.kind === "status" ? last.status : incident.status;
  const next = NEXT[effective];
  const reached = STEPS.indexOf(effective as ResponderStatus);

  async function send(status: ResponderStatus) {
    setBusy(true);
    setMessage(null);
    const outcome = await submitAction(
      queryClient,
      { incidentId: incident.id, shortCode: incident.short_code, userId },
      { kind: "status", status },
    );
    setBusy(false);
    setConfirming(null);
    if (outcome === "queued") setMessage(t("respond.action.queued"));
    else if (outcome !== "sent") setMessage(t("respond.action.failed", { error: outcome.error }));
  }

  function press(status: ResponderStatus) {
    if (status === "closed") setConfirming(status);
    else void send(status);
  }

  if (effective === "closed") {
    return <p className="text-body-md font-medium">{t("respond.action.done")}</p>;
  }
  return (
    <section aria-labelledby="status-title" className="flex flex-col gap-3">
      <h2 id="status-title" className="text-body-md font-bold">
        {t("respond.action.title")}
      </h2>
      <ol className="flex flex-wrap gap-1.5">
        {STEPS.map((step, index) => {
          const done = index < reached;
          const current = index === reached;
          const Icon = done ? CheckIcon : current ? CircleDotIcon : CircleIcon;
          return (
            <li
              key={step}
              aria-current={current ? "step" : undefined}
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-body-xs",
                current ? "border-primary font-bold" : "border-border text-muted-foreground",
              )}
            >
              <Icon aria-hidden className="size-3" />
              {t(`respond.action.${step}`)}
            </li>
          );
        })}
      </ol>
      {next ? (
        <Button
          size="lg"
          className="h-14 w-full text-body-lg"
          disabled={busy}
          onClick={() => press(next)}
        >
          {busy ? t("respond.action.sending") : t(`respond.action.${next}`)}
        </Button>
      ) : (
        <p className="text-body-sm text-muted-foreground">{t("respond.action.waiting")}</p>
      )}
      {effective === "on_scene" ? (
        <Button variant="outline" disabled={busy} onClick={() => press("closed")}>
          {t("respond.action.closeNoTransport")}
        </Button>
      ) : null}
      {message ? (
        <p role="status" className="text-body-sm">
          {message}
        </p>
      ) : null}
      {next ? <SmsButton body={statusSms(next, incident.short_code)} /> : null}

      <Dialog open={confirming !== null} onOpenChange={(open) => !open && setConfirming(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("respond.action.confirmTitle", { code: incident.short_code })}
            </DialogTitle>
            <DialogDescription>{t("respond.action.confirmBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirming(null)}>
              {t("respond.action.cancel")}
            </Button>
            <Button disabled={busy} onClick={() => void send("closed")}>
              {t("respond.action.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
