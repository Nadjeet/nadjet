import { CheckCircle2Icon, MapPinIcon, MessageSquareIcon, SirenIcon } from "lucide-react";
import { lazy, Suspense, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "@tanstack/react-router";

import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api } from "@/api";
import { resizePhoto } from "@/lib/image";
import { buildAccidentSms, smsHref, type Point } from "@/lib/sms-report";
import { cn } from "@/lib/utils";

const LocationPicker = lazy(() => import("./location-picker"));

/** SIM number of the SMS gateway, baked into the build so the cached page works offline. */
const SMS_NUMBER = import.meta.env.VITE_SMS_GATEWAY_NUMBER as string | undefined;
const GPS_TIMEOUT_MS = 10_000;
const SEND_TIMEOUT_MS = 10_000;
const MAX_PHOTO_BYTES = 10 * 1024 * 1024;

type Failure = "location" | "network" | "limit" | "invalid";
type Stage =
  | { name: "idle" }
  | { name: "locating" }
  | { name: "sending" }
  | { name: "done"; code: string; merged: boolean }
  | { name: "failed"; reason: Failure };

function currentPosition(): Promise<Point> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) return reject(new Error("unsupported"));
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude }),
      reject,
      { enableHighAccuracy: true, timeout: GPS_TIMEOUT_MS, maximumAge: 0 },
    );
  });
}

/**
 * Public one-tap crash report (US-9, FR-CIT-001/006). The phone's GPS position goes to the API;
 * with no data the same report opens the SMS app, pre-filled for the gateway number.
 */
export function ReportPage() {
  const { t } = useTranslation();
  const [stage, setStage] = useState<Stage>({ name: "idle" });
  const [point, setPoint] = useState<Point | null>(null);
  const [people, setPeople] = useState("");
  const [trapped, setTrapped] = useState(false);
  const [phone, setPhone] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [place, setPlace] = useState("");
  // One key per report: a retry or a double tap returns the same incident, never a second one.
  const idempotencyKey = useRef(crypto.randomUUID());

  const peopleCount = people.trim() === "" ? null : Math.min(99, Math.max(0, Number(people)));
  const busy = stage.name === "locating" || stage.name === "sending";

  /** FR-CIT-006: a failed or impossible submission opens the SMS app; the button stays as a retry. */
  function fail(reason: Failure, where: Point) {
    setStage({ name: "failed", reason });
    if (SMS_NUMBER && (reason === "network" || reason === "limit")) {
      window.location.href = smsHref(
        SMS_NUMBER,
        buildAccidentSms({ point: where, people: peopleCount, trapped, place }),
      );
    }
  }

  async function send(where: Point) {
    setPoint(where);
    if (!navigator.onLine) return fail("network", where);
    setStage({ name: "sending" });
    try {
      const resized = photo ? await resizePhoto(photo) : null;
      const form = new FormData();
      form.set("lat", String(where.lat));
      form.set("lon", String(where.lon));
      form.set("trapped", String(trapped));
      if (peopleCount !== null) form.set("people_reported", String(peopleCount));
      if (phone.trim()) form.set("phone", phone.trim());
      if (resized && resized.size <= MAX_PHOTO_BYTES) form.set("photo", resized, "photo.jpg");
      const { data, response } = await api.POST("/public/reports", {
        body: form as unknown as { lat: number; lon: number; trapped: boolean },
        bodySerializer: (body) => body as unknown as FormData,
        headers: { "Idempotency-Key": idempotencyKey.current },
        signal: AbortSignal.timeout(SEND_TIMEOUT_MS),
      });
      if (data) return setStage({ name: "done", code: data.short_code, merged: data.merged });
      const reason: Failure =
        response.status === 429 ? "limit" : response.status === 422 ? "invalid" : "network";
      fail(reason, where);
    } catch {
      fail("network", where);
    }
  }

  async function report(event?: FormEvent) {
    event?.preventDefault();
    if (busy) return;
    setStage({ name: "locating" });
    try {
      await send(await currentPosition());
    } catch {
      setStage({ name: "failed", reason: "location" });
    }
  }

  if (stage.name === "done") {
    return (
      <section className="mx-auto flex max-w-xl flex-col gap-4 py-8" aria-live="polite">
        <CheckCircle2Icon aria-hidden className="size-14 text-success" />
        <h1 className="text-display-sm font-bold">{t("pages.public.report.doneTitle")}</h1>
        <p className="text-body-lg">{t("pages.public.report.doneBody")}</p>
        <p className="text-body-md">
          {t("pages.public.report.code")}{" "}
          <strong dir="ltr" className="font-mono text-display-sm">
            {stage.code}
          </strong>
        </p>
        {stage.merged ? <p>{t("pages.public.report.merged")}</p> : null}
        <p className="rounded-lg border p-3 text-body-sm">{t("pages.public.report.emergency")}</p>
        <Link to="/public" className={cn(buttonVariants({ variant: "outline" }), "self-start")}>
          {t("common.backHome")}
        </Link>
      </section>
    );
  }

  const failed = stage.name === "failed" ? stage.reason : null;
  const smsBody = buildAccidentSms({ point, people: peopleCount, trapped, place });
  const canSms = Boolean(SMS_NUMBER) && (point !== null || place.trim() !== "");

  return (
    <section className="mx-auto flex w-full max-w-xl flex-col gap-6 py-4">
      <h1 className="text-display-sm font-bold text-balance">{t("pages.public.report.title")}</h1>
      <form onSubmit={report} className="flex flex-col gap-5">
        <Button
          type="submit"
          size="lg"
          variant="destructive"
          loading={busy}
          className="h-28 w-full text-display-sm"
        >
          <SirenIcon aria-hidden className="size-8" />
          {stage.name === "locating"
            ? t("pages.public.report.locating")
            : stage.name === "sending"
              ? t("pages.public.report.sending")
              : t("pages.public.cta")}
        </Button>
        <p className="text-body-sm text-muted-foreground">{t("pages.public.report.hint")}</p>

        <fieldset className="flex flex-col gap-4 rounded-lg border p-4">
          <legend className="px-1 text-body-sm font-medium">
            {t("pages.public.report.questions")}
          </legend>
          <div className="flex flex-col gap-1">
            <Label htmlFor="report-people">{t("pages.public.report.people")}</Label>
            <Input
              id="report-people"
              type="number"
              inputMode="numeric"
              min={0}
              max={99}
              className="w-32"
              value={people}
              onChange={(e) => setPeople(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-3">
            <Switch id="report-trapped" checked={trapped} onCheckedChange={setTrapped} />
            <Label htmlFor="report-trapped">{t("pages.public.report.trapped")}</Label>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="report-phone">{t("pages.public.report.phone")}</Label>
            <Input
              id="report-phone"
              type="tel"
              autoComplete="tel"
              dir="ltr"
              maxLength={20}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="report-photo">{t("pages.public.report.photo")}</Label>
            <Input
              id="report-photo"
              type="file"
              accept="image/*"
              onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
            />
          </div>
        </fieldset>
        <p className="text-body-sm text-muted-foreground">
          {t("pages.public.report.consent")}{" "}
          <Link to="/public/privacy" className="underline">
            {t("nav.privacy")}
          </Link>
        </p>
      </form>

      {failed ? (
        <div role="alert" className="flex flex-col gap-4 rounded-lg border border-danger p-4">
          <p className="font-medium">{t(`pages.public.report.fail.${failed}`)}</p>
          {failed === "location" ? (
            <>
              <Suspense fallback={null}>
                <LocationPicker onPick={setPoint} />
              </Suspense>
              <Button
                type="button"
                disabled={!point || busy}
                onClick={() => point && void send(point)}
              >
                <MapPinIcon aria-hidden />
                {t("pages.public.report.sendPicked")}
              </Button>
              <div className="flex flex-col gap-1">
                <Label htmlFor="report-place">{t("pages.public.report.place")}</Label>
                <Input
                  id="report-place"
                  dir="ltr"
                  maxLength={100}
                  value={place}
                  onChange={(e) => setPlace(e.target.value)}
                />
              </div>
            </>
          ) : null}
          {failed === "network" ? (
            <Button type="button" variant="outline" onClick={() => point && void send(point)}>
              {t("common.retry")}
            </Button>
          ) : null}
          {failed !== "invalid" && SMS_NUMBER ? (
            <a
              href={canSms ? smsHref(SMS_NUMBER, smsBody) : undefined}
              aria-disabled={!canSms}
              className={cn(
                buttonVariants({ variant: "secondary", size: "lg" }),
                !canSms && "pointer-events-none opacity-50",
              )}
            >
              <MessageSquareIcon aria-hidden />
              {t("pages.public.report.viaSms")}
            </a>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
