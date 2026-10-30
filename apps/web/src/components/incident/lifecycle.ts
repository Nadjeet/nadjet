/** Main path of the incident lifecycle (FR-INC-005). Rejected and merged end the path early. */
export const LIFECYCLE = [
  "candidate",
  "verified",
  "dispatched",
  "acknowledged",
  "en_route",
  "on_scene",
  "transporting",
  "at_hospital",
  "closed",
] as const;

export type TimelineStatus = (typeof LIFECYCLE)[number];
export type TimelineStep = { status: TimelineStatus; at?: string };
