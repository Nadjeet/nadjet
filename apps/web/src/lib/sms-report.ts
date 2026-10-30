/** The `ACCIDENT` SMS the public report page falls back to (FR-CIT-006; grammar in contracts/sms-grammar.md). */

export type Point = { lat: number; lon: number };

const SMS_MAX_CHARS = 160;
/** Digits at most: the SMS is a single GSM-7 segment, so no accents, no Arabic. */
const NOT_GSM = /[^A-Za-z0-9 .,/-]/g;

/** Latin, GSM-safe version of a free-text place (the SMS has no room for anything else). */
function gsmText(value: string): string {
  const latin = value.normalize("NFD").replace(/\p{M}/gu, "");
  return latin.replace(NOT_GSM, " ").replace(/\s+/g, " ").trim();
}

/**
 * `ACCIDENT <lat>,<lon> P<n> C<0|1> <text>` with 5-decimal coordinates, or `ACCIDENT <place>`
 * when there is no position (the operator calls back). Always one SMS segment.
 */
export function buildAccidentSms(options: {
  point: Point | null;
  people: number | null;
  trapped: boolean;
  place?: string;
}): string {
  const parts = ["ACCIDENT"];
  const place = gsmText(options.place ?? "");
  if (options.point) {
    parts.push(`${options.point.lat.toFixed(5)},${options.point.lon.toFixed(5)}`);
    if (options.people !== null) parts.push(`P${options.people}`);
    parts.push(`C${options.trapped ? 1 : 0}`);
  }
  if (place) parts.push(place);
  return parts.join(" ").slice(0, SMS_MAX_CHARS);
}

/** `?&body=` is the form both Android and iOS accept. */
export function smsHref(number: string, body: string): string {
  return `sms:${number}?&body=${encodeURIComponent(body)}`;
}
