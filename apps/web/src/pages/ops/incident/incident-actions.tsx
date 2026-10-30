import { useNavigate } from "@tanstack/react-router";
import { CheckIcon, GitMergeIcon, XIcon } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLabel } from "@/lib/format";

import {
  ApiError,
  useIncidents,
  useMerge,
  useReject,
  useVerify,
  type Incident,
  type RejectReason,
} from "./incident-queries";
import { locationText } from "./incident-format";

const REASONS: RejectReason[] = ["false_positive", "duplicate", "not_emergency", "other"];

function useErrorText() {
  const { t } = useTranslation();
  return (error: unknown) =>
    error instanceof ApiError && error.status === 409
      ? t("ops.errors.conflict")
      : error instanceof ApiError && error.status === 403
        ? t("ops.errors.forbidden")
        : t("ops.errors.generic");
}

function RejectDialog({
  incident,
  open,
  onOpenChange,
}: {
  incident: Incident;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const reject = useReject(incident.id);
  const [reason, setReason] = useState<RejectReason>("false_positive");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("ops.actions.rejectTitle", { code: incident.short_code })}</DialogTitle>
          <DialogDescription>{t("ops.actions.rejectBody")}</DialogDescription>
        </DialogHeader>
        <RadioGroup
          value={reason}
          onValueChange={(value) => setReason(value as RejectReason)}
          aria-label={t("ops.actions.reason")}
        >
          {REASONS.map((value) => (
            <div key={value} className="flex items-center gap-3">
              <RadioGroupItem id={`reason-${value}`} value={value} />
              <Label htmlFor={`reason-${value}`}>{t(`ops.reject.${value}`)}</Label>
            </div>
          ))}
        </RadioGroup>
        {reject.isError ? (
          <p role="alert" className="text-body-sm text-danger">
            {errorText(reject.error)}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("ops.actions.cancel")}
          </Button>
          <Button
            variant="destructive"
            disabled={reject.isPending}
            onClick={() => reject.mutate(reason, { onSuccess: () => onOpenChange(false) })}
          >
            {t("ops.actions.reject")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MergeDialog({
  incident,
  open,
  onOpenChange,
}: {
  incident: Incident;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const label = useLabel();
  const errorText = useErrorText();
  const navigate = useNavigate();
  const merge = useMerge(incident.id);
  const open_ = useIncidents({ status: "open" });
  const [target, setTarget] = useState("");
  const targets = (open_.data?.items ?? []).filter((i) => i.id !== incident.id);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("ops.actions.mergeTitle", { code: incident.short_code })}</DialogTitle>
          <DialogDescription>{t("ops.actions.mergeBody")}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1">
          <Label htmlFor="merge-target">{t("ops.actions.mergeTarget")}</Label>
          <Select value={target} onValueChange={setTarget}>
            <SelectTrigger id="merge-target" className="w-full">
              <SelectValue placeholder={t("ops.actions.mergePlaceholder")} />
            </SelectTrigger>
            <SelectContent position="popper">
              {targets.map((i) => (
                <SelectItem key={i.id} value={i.id}>
                  {i.short_code} · P{i.priority} · {label(`ops.type.${i.type}`, i.type)} ·{" "}
                  {locationText(i)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {targets.length === 0 ? (
            <p className="text-body-xs text-muted-foreground">{t("ops.actions.mergeNone")}</p>
          ) : null}
        </div>
        {merge.isError ? (
          <p role="alert" className="text-body-sm text-danger">
            {errorText(merge.error)}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("ops.actions.cancel")}
          </Button>
          <Button
            disabled={!target || merge.isPending}
            onClick={() =>
              merge.mutate(target, {
                onSuccess: (merged) => {
                  onOpenChange(false);
                  void navigate({
                    to: "/ops/incidents/$incidentId",
                    params: { incidentId: merged.id },
                  });
                },
              })
            }
          >
            {t("ops.actions.merge")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Confirm, reject (with reason) and merge: only candidates can be triaged (FR-INC-005/006). */
export function IncidentActions({ incident }: { incident: Incident }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const verify = useVerify(incident.id);
  const [rejecting, setRejecting] = useState(false);
  const [merging, setMerging] = useState(false);
  if (incident.status !== "candidate") return null;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button variant="success" disabled={verify.isPending} onClick={() => verify.mutate()}>
          <CheckIcon aria-hidden />
          {t("ops.actions.confirm")}
        </Button>
        <Button variant="destructive" onClick={() => setRejecting(true)}>
          <XIcon aria-hidden />
          {t("ops.actions.reject")}
        </Button>
        <Button variant="outline" onClick={() => setMerging(true)}>
          <GitMergeIcon aria-hidden />
          {t("ops.actions.merge")}
        </Button>
      </div>
      {verify.isError ? (
        <p role="alert" className="text-body-sm text-danger">
          {errorText(verify.error)}
        </p>
      ) : null}
      <RejectDialog incident={incident} open={rejecting} onOpenChange={setRejecting} />
      <MergeDialog incident={incident} open={merging} onOpenChange={setMerging} />
    </div>
  );
}
