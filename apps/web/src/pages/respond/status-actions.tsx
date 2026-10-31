import { useQueryClient } from "@tanstack/react-query";
import { AmbulanceIcon } from "lucide-react";
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

import { SmsButton } from "./sms-button";

/** Icon of the next-step button (Figma "Start Transport to Hospital" uses an ambulance). */
const NEXT_ICON = AmbulanceIcon;

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
    <section aria-label={t("respond.action.title")} className="flex flex-col gap-3">
      {next ? (
        <Button variant="gradient" className="w-full" disabled={busy} onClick={() => press(next)}>
          <NEXT_ICON aria-hidden />
          {busy ? t("respond.action.sending") : t(`respond.action.${next}`)}
        </Button>
      ) : (
        <p className="text-body-sm text-ink-muted">{t("respond.action.waiting")}</p>
      )}
      {effective === "on_scene" ? (
        <Button variant="neutral" disabled={busy} onClick={() => press("closed")}>
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
            <Button variant="gradient" disabled={busy} onClick={() => void send("closed")}>
              {t("respond.action.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
