import { CircleAlertIcon, CameraIcon, SquareIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import {
  TryError,
  createSession,
  endSession,
  fetchSession,
  pingSession,
  publishWhip,
  type TrySession,
} from "./try-data";

const PING_MS = 10_000;
const POLL_MS = 2_000;

/** Phone as a live camera: WHIP to the video server, AI checks every 4 s shown below. */
export function TryLivePage() {
  const { t } = useTranslation();
  const preview = useRef<HTMLVideoElement>(null);
  const [session, setSession] = useState<TrySession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stopRef = useRef<(() => void) | null>(null);
  const idRef = useRef<string | null>(null);

  async function leave() {
    stopRef.current?.();
    stopRef.current = null;
    const id = idRef.current;
    idRef.current = null;
    setSession(null);
    if (id) await endSession(id);
  }

  async function start() {
    setError(null);
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: false,
      });
      // Until publishing works, a failure must still turn the phone camera off.
      stopRef.current = () => {
        for (const track of media.getTracks()) track.stop();
      };
      if (preview.current) preview.current.srcObject = media;
      const created = await createSession();
      idRef.current = created.id;
      const stopPeer = await publishWhip(created.whip_url, media, created.publish_token);
      stopRef.current = () => {
        stopPeer();
        for (const track of media.getTracks()) track.stop();
      };
      setSession(created);
    } catch (caught) {
      await leave();
      setError(
        caught instanceof TryError && caught.kind === "rateLimited"
          ? t("pages.public.try.errors.rateLimited")
          : t("pages.public.try.live.failed"),
      );
    }
  }

  useEffect(() => {
    if (!session) return;
    const ping = setInterval(() => void pingSession(session.id), PING_MS);
    const poll = setInterval(async () => {
      const fresh = await fetchSession(session.id);
      if (fresh) setSession(fresh);
      else void leave();
    }, POLL_MS);
    const onHide = () => void endSession(session.id);
    window.addEventListener("pagehide", onHide);
    return () => {
      clearInterval(ping);
      clearInterval(poll);
      window.removeEventListener("pagehide", onHide);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.id]);

  useEffect(() => () => void leave(), []);

  return (
    <section className="flex flex-col gap-4 py-6">
      <h1 className="text-display-sm font-bold text-balance">{t("pages.public.try.live.title")}</h1>
      <p className="max-w-2xl text-body-lg text-muted-foreground">
        {t("pages.public.try.live.body")}
      </p>
      <p className="rounded-xl border border-border bg-card p-4 text-body-sm text-muted-foreground">
        {t("pages.public.try.consent.body")}
      </p>
      <video
        ref={preview}
        autoPlay
        muted
        playsInline
        className="aspect-video w-full max-w-xl rounded-xl bg-black"
        aria-label={t("pages.public.try.live.preview")}
      />
      <div className="flex flex-wrap items-center gap-3">
        {session ? (
          <>
            <Badge variant="success">{t("pages.public.try.live.on")}</Badge>
            <Button type="button" variant="outline" onClick={() => void leave()}>
              <SquareIcon aria-hidden />
              {t("pages.public.try.live.stop")}
            </Button>
          </>
        ) : (
          <Button type="button" size="lg" onClick={() => void start()}>
            <CameraIcon aria-hidden />
            {t("pages.public.try.live.start")}
          </Button>
        )}
      </div>
      {error ? (
        <p
          role="alert"
          className="flex items-center gap-2 font-medium text-danger dark:text-red-400"
        >
          <CircleAlertIcon aria-hidden className="size-4" />
          {error}
        </p>
      ) : null}
      {session ? (
        <ol aria-live="polite" className="flex max-w-xl flex-col gap-1 text-body-sm">
          {[...session.events].reverse().map((event) => (
            <li key={`${event.at}-${event.kind}-${event.label}`}>
              <bdi dir="ltr" className="font-medium">
                {new Date(event.at).toLocaleTimeString()}
              </bdi>{" "}
              {event.label} <span className="text-muted-foreground">({event.source})</span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
