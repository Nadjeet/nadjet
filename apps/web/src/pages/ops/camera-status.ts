import type { components } from "@nadjet/api-client";

import type { StreamUrls } from "@/components/stream/live-stream";

export type Camera = components["schemas"]["CameraOut"];
export type View = "raw" | "annotated";
export type TileStatus = "live" | "degraded" | "offline";

/** The vision workers republish the annotated stream of `<cam>` as `<cam>_ai` (FR-VIS-014). */
export function streamUrls(stream: Camera["stream"], view: View): StreamUrls {
  const swap = (url: string) =>
    view === "raw" ? url : url.replace(`/${stream.path}/`, `/${stream.path}_ai/`);
  return { whepUrl: swap(stream.whep_url), hlsUrl: swap(stream.hls_url) };
}

/** A silent worker means no analysis even if the video still flows, so it is never "live". */
export function tileStatus(status: Camera["status"], stale: boolean): TileStatus {
  if (status === "degraded") return "degraded";
  if (status === "online") return stale ? "degraded" : "live";
  return "offline";
}
