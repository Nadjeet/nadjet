import type { components } from "@nadjet/api-client";

import { api } from "@/api";

export type TryJob = components["schemas"]["TryJobOut"];
export type TrySession = components["schemas"]["TrySessionOut"];
export type TryStatus = components["schemas"]["TryStatus"];

export const FINAL_STATUSES = ["done", "failed", "rejected"] as const;
export const isFinal = (job: TryJob) => (FINAL_STATUSES as readonly string[]).includes(job.status);

export class TryError extends Error {
  constructor(
    readonly kind: "tooLarge" | "notVideo" | "tooLong" | "rateLimited" | "failed",
    message: string,
  ) {
    super(message);
  }
}

export async function fetchStatus(): Promise<TryStatus> {
  const { data } = await api.GET("/public/try/status");
  if (!data) throw new TryError("failed", "status");
  return data;
}

/** Client-side checks before any byte is sent (PRD E-12); the server repeats them. */
export async function checkClip(file: File, status: TryStatus): Promise<TryError | null> {
  if (!file.type.startsWith("video/")) return new TryError("notVideo", file.type);
  if (file.size > status.max_mb * 1024 * 1024) return new TryError("tooLarge", String(file.size));
  const seconds = await new Promise<number>((resolve) => {
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(video.duration);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(Number.NaN);
    };
    video.src = url;
  });
  if (Number.isNaN(seconds)) return new TryError("notVideo", file.name);
  return seconds > status.max_seconds ? new TryError("tooLong", String(seconds)) : null;
}

export async function uploadClip(file: File): Promise<TryJob> {
  const type = file.type as "video/mp4" | "video/quicktime" | "video/webm";
  const { data, response } = await api.POST("/public/try/jobs", {
    params: { query: { filename: file.name } },
    body: file as unknown as never,
    bodySerializer: (body: unknown) => body as BodyInit,
    headers: { "Content-Type": type },
  });
  if (data) return data;
  const kinds: Record<number, TryError["kind"]> = {
    413: "tooLarge",
    415: "notVideo",
    422: "tooLong",
    429: "rateLimited",
  };
  throw new TryError(kinds[response.status] ?? "failed", String(response.status));
}

export async function deleteJob(id: string): Promise<void> {
  await api.DELETE("/public/try/jobs/{job_id}", { params: { path: { job_id: id } } });
}

/** Progress of a job: `onJob` gets every update, the stream closes itself when it is final. */
export function followJob(id: string, onJob: (job: TryJob) => void, onGone: () => void) {
  const source = new EventSource(`/api/public/try/jobs/${id}/events`);
  source.addEventListener("job", (event) => {
    const job = JSON.parse((event as MessageEvent<string>).data) as TryJob;
    onJob(job);
    if (isFinal(job)) source.close();
  });
  source.addEventListener("gone", () => {
    source.close();
    onGone();
  });
  return () => source.close();
}

export async function createSession(): Promise<TrySession> {
  const { data, response } = await api.POST("/public/try/sessions");
  if (!data) throw new TryError(response.status === 429 ? "rateLimited" : "failed", "session");
  return data;
}

export async function fetchSession(id: string): Promise<TrySession | null> {
  const { data } = await api.GET("/public/try/sessions/{session_id}", {
    params: { path: { session_id: id } },
  });
  return data ?? null;
}

export async function pingSession(id: string): Promise<void> {
  await api.POST("/public/try/sessions/{session_id}/ping", {
    params: { path: { session_id: id } },
  });
}

export async function endSession(id: string): Promise<void> {
  await api.DELETE("/public/try/sessions/{session_id}", { params: { path: { session_id: id } } });
}

/** Publish a camera stream to MediaMTX over WHIP (RFC 9725). Returns a function to stop. */
export async function publishWhip(
  whipUrl: string,
  stream: MediaStream,
  token?: string | null,
): Promise<() => void> {
  const peer = new RTCPeerConnection();
  for (const track of stream.getTracks()) peer.addTrack(track, stream);
  const offer = await peer.createOffer();
  await peer.setLocalDescription(offer);
  await new Promise<void>((resolve) => {
    if (peer.iceGatheringState === "complete") return resolve();
    const done = () => {
      if (peer.iceGatheringState === "complete") {
        peer.removeEventListener("icegatheringstatechange", done);
        resolve();
      }
    };
    peer.addEventListener("icegatheringstatechange", done);
    setTimeout(resolve, 3_000);
  });
  const answer = await fetch(whipUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/sdp",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: peer.localDescription?.sdp ?? offer.sdp ?? "",
  });
  if (answer.status !== 201) throw new TryError("failed", `WHIP answered HTTP ${answer.status}`);
  await peer.setRemoteDescription({ type: "answer", sdp: await answer.text() });
  return () => peer.close();
}
