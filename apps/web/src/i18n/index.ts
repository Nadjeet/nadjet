import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import ar from "../locales/ar.json";
import en from "../locales/en.json";
import fr from "../locales/fr.json";

export const LANGUAGES = ["ar", "fr", "en"] as const;
export type Language = (typeof LANGUAGES)[number];
export const DEFAULT_LANGUAGE: Language = "ar";

const STORAGE_KEY = "nadjet.language";

export const resources = {
  ar: { translation: ar },
  fr: { translation: fr },
  en: { translation: en },
} as const;

function isLanguage(value: unknown): value is Language {
  return LANGUAGES.includes(value as Language);
}

function storedLanguage(): Language {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (isLanguage(value)) return value;
  } catch {
    // Storage may be unavailable: fall back to the default language.
  }
  return DEFAULT_LANGUAGE;
}

/** Keep `<html lang dir>` in sync so the whole layout flips to RTL for Arabic. */
function applyDocumentLanguage(language: string) {
  document.documentElement.lang = language;
  document.documentElement.dir = i18n.dir(language);
}

void i18n.use(initReactI18next).init({
  resources,
  lng: storedLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: LANGUAGES,
  interpolation: { escapeValue: false },
});

applyDocumentLanguage(i18n.language);
i18n.on("languageChanged", (language) => {
  applyDocumentLanguage(language);
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Not persisted; the choice still applies for this visit.
  }
});

export { i18n };
export function currentLanguage(): Language {
  return isLanguage(i18n.language) ? i18n.language : DEFAULT_LANGUAGE;
}
