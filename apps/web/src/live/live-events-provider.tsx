import { useEffect, useState, type ReactNode } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api } from "@/api";
import { useSession } from "@/lib/auth-store";

import { camerasKey, incidentKey, incidentsKey } from "./keys";
import { LiveEventsContext, type LiveStatus } from "./live-events-context";
import { SseParser } from "./sse";

const MIN_DELAY_MS = 1_000;
const MAX_DELAY_MS = 15_000;
/** The API sends a heartbeat every 15 s; silence for two beats plus a margin means it is dead. */
const STALE_AFTER_MS = 35_000;

const INCIDENT_EVENTS = new Set([
  "incident.created",
  "incident.updated",
  "incident.status_changed",
]);

function handleMessage(queryClient: QueryClient, event: string, data: string) {
  if (event === "camera_fault" || event === "camera_recovered") {
    void queryClient.invalidateQueries({ queryKey: camerasKey });
    return;
  }
  if (!INCIDENT_EVENTS.has(event)) return;
  void queryClient.invalidateQueries({ queryKey: incidentsKey });
  try {
    const { incident_id: id } = JSON.parse(data) as { incident_id?: string };
    if (id) void queryClient.invalidateQueries({ queryKey: incidentKey(id) });
  } catch {
    // Malformed payload: the queue refetch above is enough.
  }
}

function backoff(attempt: number): number {
  const base = Math.min(MIN_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
  return base / 2 + Math.random() * (base / 2);
}

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

/** One connection: resolves when the stream ends, goes silent or fails. */
async function readStream(
  signal: AbortSignal,
  queryClient: QueryClient,
  onOpen: () => void,
): Promise<void> {
  const connection = new AbortController();
  const abort = () => connection.abort();
  signal.addEventListener("abort", abort);
  let watchdog: ReturnType<typeof setTimeout> | undefined;
  const arm = () => {
    clearTimeout(watchdog);
    watchdog = setTimeout(abort, STALE_AFTER_MS);
  };
  try {
    // The client adds the bearer token (an EventSource cannot send headers).
    const { data: body, response } = await api.GET("/events", {
      parseAs: "stream",
      signal: connection.signal,
      headers: { Accept: "text/event-stream" },
    });
    if (!response.ok || !body) return;
    arm();
    const reader = body.pipeThrough(new TextDecoderStream()).getReader();
    const parser = new SseParser();
    let opened = false;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return;
      arm();
      // Live only once the API has spoken (it sends a comment at once): a proxy that answers
      // 200 and closes must not reset the back-off into a tight reconnect loop.
      if (!opened) {
        opened = true;
        onOpen();
      }
      for (const message of parser.push(value)) {
        handleMessage(queryClient, message.event, message.data);
      }
    }
  } catch {
    // Network error or abort: the caller reconnects unless the session ended.
  } finally {
    clearTimeout(watchdog);
    signal.removeEventListener("abort", abort);
    connection.abort();
  }
}

/** Keeps one live-events stream open while signed in; reconnects with back-off (FR-MAP-002). */
export function LiveEventsProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const token = useSession()?.token;
  const [status, setStatus] = useState<LiveStatus>("connecting");

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    const { signal } = controller;
    void (async () => {
      let attempt = 0;
      setStatus("connecting");
      while (!signal.aborted) {
        let opened = false;
        await readStream(signal, queryClient, () => {
          opened = true;
          attempt = 0;
          setStatus("live");
          // Anything missed while disconnected: refetch the queue.
          void queryClient.invalidateQueries({ queryKey: incidentsKey });
        });
        if (signal.aborted) return;
        setStatus("reconnecting");
        await sleep(backoff(opened ? 0 : attempt++), signal);
      }
    })();
    return () => controller.abort();
  }, [token, queryClient]);

  return <LiveEventsContext.Provider value={status}>{children}</LiveEventsContext.Provider>;
}
