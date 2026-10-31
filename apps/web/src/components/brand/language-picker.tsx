import { GlobeIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LANGUAGES, i18n, type Language } from "@/i18n";

/** Native names: each language is always readable by its own speakers. */
const NAMES: Record<Language, string> = { ar: "العربية", fr: "Français", en: "English" };

export function LanguagePicker({ className }: { className?: string }) {
  const { t, i18n: instance } = useTranslation();
  return (
    <Select value={instance.language} onValueChange={(value) => void i18n.changeLanguage(value)}>
      <SelectTrigger size="sm" aria-label={t("common.language")} className={className}>
        <GlobeIcon aria-hidden />
        <SelectValue />
      </SelectTrigger>
      <SelectContent position="popper">
        {LANGUAGES.map((language) => (
          <SelectItem key={language} value={language} lang={language}>
            {NAMES[language]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
