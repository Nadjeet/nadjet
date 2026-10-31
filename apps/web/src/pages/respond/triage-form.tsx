import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/lib/auth-store";
import type { CasualtyIn, IncidentDetail, TriageTag } from "@/lib/incident-queries";
import { submitAction } from "@/lib/responder-actions";
import { triageSms } from "@/lib/sms-codes";
import { usePendingActions } from "@/lib/use-pending";
import { cn } from "@/lib/utils";

import { SmsButton } from "./sms-button";

const TAGS: TriageTag[] = ["red", "yellow", "green", "black"];
const BORDER: Record<TriageTag, string> = {
  red: "border-red-700",
  yellow: "border-yellow-600",
  green: "border-green-700",
  black: "border-foreground",
};
const AVPU = ["A", "V", "P", "U"] as const;

function optionalInt(value: string): number | null {
  const number = Number.parseInt(value, 10);
  return Number.isFinite(number) ? number : null;
}

function Choice({
  name,
  value,
  checked,
  onChange,
  className,
  children,
}: {
  name: string;
  value: string;
  checked: boolean;
  onChange: () => void;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex min-h-12 cursor-pointer items-center gap-2 rounded-lg border-2 px-3 py-2 text-body-sm font-medium has-[:checked]:bg-accent has-[:checked]:font-bold has-[:focus-visible]:shadow-focus",
        className,
      )}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onChange}
        className="size-4 accent-[var(--primary)]"
      />
      {children}
    </label>
  );
}

/**
 * START triage of one victim (FR-RSP-003): category, AVPU, breathing, pulse, SpO₂, bleeding,
 * notes. Priority is recomputed from the tags (FR-INC-004). Offline, the entry is queued and the
 * SMS button carries the counts (`T 7F3 R1 Y2`).
 */
export function TriageForm({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const userId = useSession()?.user.id ?? "";
  const pending = usePendingActions(incident.id).filter(
    (a) => a.kind === "triage" && a.state === "pending",
  );
  const [tag, setTag] = useState<TriageTag | null>(null);
  const [avpu, setAvpu] = useState<(typeof AVPU)[number] | null>(null);
  const [resp, setResp] = useState("");
  const [pulse, setPulse] = useState("");
  const [spo2, setSpo2] = useState("");
  const [bleeding, setBleeding] = useState<boolean | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const recorded = incident.casualties.length + pending.length;
  const counts: Partial<Record<TriageTag, number>> = {};
  for (const action of pending) {
    if (action.kind === "triage") {
      const victim = action.casualty.triage_tag;
      counts[victim] = (counts[victim] ?? 0) + 1;
    }
  }
  if (tag) counts[tag] = (counts[tag] ?? 0) + 1;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!tag) return;
    setBusy(true);
    const casualty: CasualtyIn = {
      triage_tag: tag,
      source: "app",
      avpu,
      resp_rate: optionalInt(resp),
      pulse: optionalInt(pulse),
      spo2: optionalInt(spo2),
      bleeding,
      notes: notes.trim() === "" ? null : notes.trim(),
    };
    const outcome = await submitAction(
      queryClient,
      { incidentId: incident.id, shortCode: incident.short_code, userId },
      { kind: "triage", casualty },
    );
    setBusy(false);
    if (typeof outcome === "object") {
      setMessage(t("respond.action.failed", { error: outcome.error }));
      return;
    }
    setMessage(outcome === "queued" ? t("respond.triage.queued") : t("respond.triage.saved"));
    setTag(null);
    setAvpu(null);
    setResp("");
    setPulse("");
    setSpo2("");
    setBleeding(null);
    setNotes("");
  }

  return (
    <section aria-labelledby="triage-title" className="flex flex-col gap-3">
      <h2 id="triage-title" className="text-body-md font-bold">
        {t("respond.triage.title")}
      </h2>
      <p className="text-body-sm text-ink-muted">
        {t("respond.triage.recorded", { count: recorded })}
      </p>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <fieldset className="grid grid-cols-2 gap-2">
          <legend className="mb-2 text-body-sm font-medium">{t("respond.triage.tag")}</legend>
          {TAGS.map((value) => (
            <Choice
              key={value}
              name="triage-tag"
              value={value}
              checked={tag === value}
              onChange={() => setTag(value)}
              className={BORDER[value]}
            >
              {t(`respond.triage.${value}`)}
            </Choice>
          ))}
        </fieldset>
        <fieldset className="grid grid-cols-2 gap-2">
          <legend className="mb-2 text-body-sm font-medium">{t("respond.triage.avpu")}</legend>
          {AVPU.map((value) => (
            <Choice
              key={value}
              name="triage-avpu"
              value={value}
              checked={avpu === value}
              onChange={() => setAvpu(value)}
              className="border-border"
            >
              {value} · {t(`respond.triage.${value}`)}
            </Choice>
          ))}
        </fieldset>
        <div className="grid grid-cols-3 gap-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="triage-resp">{t("respond.triage.resp")}</Label>
            <Input
              id="triage-resp"
              inputMode="numeric"
              min={0}
              max={120}
              value={resp}
              onChange={(e) => setResp(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="triage-pulse">{t("respond.triage.pulse")}</Label>
            <Input
              id="triage-pulse"
              inputMode="numeric"
              min={0}
              max={300}
              value={pulse}
              onChange={(e) => setPulse(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="triage-spo2">{t("respond.triage.spo2")}</Label>
            <Input
              id="triage-spo2"
              inputMode="numeric"
              min={0}
              max={100}
              value={spo2}
              onChange={(e) => setSpo2(e.target.value)}
            />
          </div>
        </div>
        <fieldset className="grid grid-cols-2 gap-2">
          <legend className="mb-2 text-body-sm font-medium">{t("respond.triage.bleeding")}</legend>
          <Choice
            name="triage-bleeding"
            value="yes"
            checked={bleeding === true}
            onChange={() => setBleeding(true)}
            className="border-border"
          >
            {t("ops.yes")}
          </Choice>
          <Choice
            name="triage-bleeding"
            value="no"
            checked={bleeding === false}
            onChange={() => setBleeding(false)}
            className="border-border"
          >
            {t("ops.no")}
          </Choice>
        </fieldset>
        <div className="flex flex-col gap-1">
          <Label htmlFor="triage-notes">{t("respond.triage.notes")}</Label>
          <Textarea
            id="triage-notes"
            maxLength={1000}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        <Button type="submit" size="lg" className="h-14 w-full" disabled={!tag || busy}>
          {t("respond.triage.submit")}
        </Button>
      </form>
      {message ? (
        <p role="status" className="text-body-sm">
          {message}
        </p>
      ) : null}
      <SmsButton body={triageSms(incident.short_code, counts)} />
    </section>
  );
}
