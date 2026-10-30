import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { startHls, startWhep, type PlaybackMode } from "./players";

export type StreamUrls = { whepUrl: string; hlsUrl: string };

export type StreamState = {
  phase: "connecting" | "playing" | "reconnecting";
  mode: PlaybackMode | null;
  latencyMs: number | null;
};

const INITIAL: StreamState = { phase: "connecting", mode: null, latencyMs: null };
const LATENCY_POLL_MS = 2_000;
const MIN_DELAY_MS = 1_000;
const MAX_DELAY_MS = 10_000;

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal.addEventListener("abort", done, { once: true });
  });
}

/** WebRTC first, LL-HLS when WebRTC fails; on a drop, start over with a growing delay. */
async function supervise(
  video: HTMLVideoElement,
  urls: StreamUrls,
  signal: AbortSignal,
  report: (state: StreamState) => void,
) {
  let attempt = 0;
  while (!signal.aborted) {
    report({ ...INITIAL, phase: attempt === 0 ? "connecting" : "reconnecting" });
    let mode: PlaybackMode = "webrtc";
    let playback = await startWhep(urls.whepUrl, video).catch(() => null);
    if (!playback) {
      mode = "hls";
      playback = await startHls(urls.hlsUrl, video).catch(() => null);
    }
    if (playback && !signal.aborted) {
      attempt = 0;
      const live = playback;
      const poll = async () => {
        report({ phase: "playing", mode, latencyMs: await live.latency().catch(() => null) });
      };
      await poll();
      const timer = setInterval(() => void poll(), LATENCY_POLL_MS);
      await Promise.race([
        live.lost,
        new Promise<void>((r) => signal.addEventListener("abort", () => r(), { once: true })),
      ]);
      clearInterval(timer);
    }
    playback?.stop();
    if (signal.aborted) return;
    attempt += 1;
    report({ ...INITIAL, phase: "reconnecting" });
    const base = Math.min(MIN_DELAY_MS * 2 ** (attempt - 1), MAX_DELAY_MS);
    await sleep(base / 2 + Math.random() * (base / 2), signal);
  }
}

/**
 * Live video of one MediaMTX path. Pass the `<cam>_ai` URLs for the annotated stream: the
 * path is dynamic, so any camera (simulated, phone) plays the same way.
 */
export function LiveStream({
  urls,
  label,
  onState,
  className,
}: {
  urls: StreamUrls;
  /** Accessible name of the video. */
  label: string;
  onState?: (state: StreamState) => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const video = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<StreamState>(INITIAL);
  const onStateRef = useRef(onState);
  useEffect(() => {
    onStateRef.current = onState;
  });

  const { whepUrl, hlsUrl } = urls;
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    const controller = new AbortController();
    void supervise(element, { whepUrl, hlsUrl }, controller.signal, (next) => {
      setState(next);
      onStateRef.current?.(next);
    });
    return () => controller.abort();
  }, [whepUrl, hlsUrl]);

  return (
    <div className={cn("relative overflow-hidden bg-black", className)}>
      <video
        ref={video}
        aria-label={label}
        className="size-full object-contain"
        autoPlay
        muted
        playsInline
      />
      <div className="absolute inset-x-0 bottom-0 flex flex-wrap items-center gap-2 bg-black/70 px-2 py-1 text-body-xs text-white">
        <span>{t(`stream.${state.phase}`)}</span>
        {state.mode ? (
          <bdi dir="ltr" className="font-mono">
            {state.mode === "webrtc" ? "WebRTC" : "LL-HLS"}
          </bdi>
        ) : null}
        {state.mode === "hls" ? <span>{t("stream.fallback")}</span> : null}
        {state.latencyMs !== null ? (
          <bdi dir="ltr" className="ms-auto font-mono">
            {t("stream.latency", { ms: Math.round(state.latencyMs) })}
          </bdi>
        ) : null}
      </div>
    </div>
  );
}
