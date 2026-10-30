import type { ParseKeys } from "i18next";
import { useTranslation } from "react-i18next";

/** Algeria writes Arabic with Latin digits: `ar-DZ`, not `ar`. */
const DATE_LOCALES: Record<string, string> = { ar: "ar-DZ", fr: "fr-DZ", en: "en-GB" };

export function dateLocale(language: string): string {
  return DATE_LOCALES[language] ?? language;
}

export function formatTime(iso: string, language: string): string {
  return new Intl.DateTimeFormat(dateLocale(language), { timeStyle: "short" }).format(
    new Date(iso),
  );
}

export function formatDateTime(iso: string, language: string): string {
  return new Intl.DateTimeFormat(dateLocale(language), {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(iso));
}

/** Age as a short relative phrase ("5 min ago"), from the event time. */
export function formatAge(iso: string, language: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  const formatter = new Intl.RelativeTimeFormat(dateLocale(language), {
    numeric: "always",
    style: "narrow",
  });
  if (seconds < 60) return formatter.format(-seconds, "second");
  if (seconds < 3600) return formatter.format(-Math.floor(seconds / 60), "minute");
  if (seconds < 86_400) return formatter.format(-Math.floor(seconds / 3600), "hour");
  return formatter.format(-Math.floor(seconds / 86_400), "day");
}

/** Translate a key built from API data; unknown values fall back to the raw value. */
export function useLabel(): (key: string, fallback: string) => string {
  const { t, i18n } = useTranslation();
  return (key, fallback) => (i18n.exists(key) ? t(key as ParseKeys) : fallback);
}
