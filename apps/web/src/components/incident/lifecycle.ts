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

/** Steps reached so far, from the signed event chain: creation, then every status change. */
export function stepsFromEvents(
  events: { kind: string; ts: string; payload: unknown }[],
): TimelineStep[] {
  const steps: TimelineStep[] = [];
  for (const event of events) {
    const to = (event.payload as { to?: unknown } | null)?.to;
    if (event.kind === "created") steps.push({ status: "candidate", at: event.ts });
    if (event.kind === "status_changed" && typeof to === "string") {
      if ((LIFECYCLE as readonly string[]).includes(to)) {
        steps.push({ status: to as TimelineStatus, at: event.ts });
      }
    }
  }
  return steps;
}
