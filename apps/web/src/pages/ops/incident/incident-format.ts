import type { Incident } from "./incident-queries";

export function locationText(incident: Incident): string {
  const road = [incident.road, incident.pk_km !== null ? `PK ${incident.pk_km}` : null]
    .filter(Boolean)
    .join(" ");
  return [road, incident.wilaya].filter(Boolean).join(", ") || incident.location_text || "—";
}
