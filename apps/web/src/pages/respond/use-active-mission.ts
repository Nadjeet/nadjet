import { useIncidents, type Incident } from "@/lib/incident-queries";

/** The responder's current mission: the most urgent open incident of the agency (FR-RSP-001). */
export function useActiveMission(): { incident: Incident | null; isPending: boolean } {
  const incidents = useIncidents({ status: "open" });
  return { incident: incidents.data?.items[0] ?? null, isPending: incidents.isPending };
}
