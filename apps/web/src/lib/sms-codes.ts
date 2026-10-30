import type { TriageTag } from "./incident-queries";

/** Compact SMS grammar the gateway parses (`contracts/sms-grammar.md`, FR-NTF-005). */
export const STATUS_SMS_CODES = {
  acknowledged: "OK",
  en_route: "ER",
  on_scene: "OS",
  transporting: "TR",
  at_hospital: "AH",
  closed: "CL",
} as const;

export type ResponderStatus = keyof typeof STATUS_SMS_CODES;

const TRIAGE_LETTERS: [TriageTag, string][] = [
  ["red", "R"],
  ["yellow", "Y"],
  ["green", "G"],
  ["black", "B"],
];
const MAX_PER_SMS = 99;

/** `OS 7F3`: the status of an incident. */
export function statusSms(status: ResponderStatus, shortCode: string): string {
  return `${STATUS_SMS_CODES[status]} ${shortCode}`;
}

/** `T 7F3 R1 Y2`: the victims per START tag, or `null` when there is none to report. */
export function triageSms(
  shortCode: string,
  counts: Partial<Record<TriageTag, number>>,
): string | null {
  const parts = TRIAGE_LETTERS.flatMap(([tag, letter]) => {
    const count = Math.min(counts[tag] ?? 0, MAX_PER_SMS);
    return count > 0 ? [`${letter}${count}`] : [];
  });
  return parts.length > 0 ? `T ${shortCode} ${parts.join(" ")}` : null;
}

/** An `sms:` link that opens the phone's SMS app addressed to the gateway, text pre-filled. */
export function smsUri(number: string, body: string): string {
  return `sms:${number.replace(/\s+/g, "")}?body=${encodeURIComponent(body)}`;
}

/** Google-free deep links to a position: the phone's map app, and OpenStreetMap. */
export function geoUri(lat: number, lon: number, label: string): string {
  return `geo:${lat},${lon}?q=${lat},${lon}(${encodeURIComponent(label)})`;
}

export function osmUrl(lat: number, lon: number): string {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`;
}
