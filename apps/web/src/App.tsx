import type { ReactNode } from "react";
import { Direction } from "radix-ui";
import { useTranslation } from "react-i18next";

/** Gives Radix primitives (select, slider, dialog…) the text direction of the active language. */
export function App({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  return <Direction.Provider dir={i18n.dir(i18n.language)}>{children}</Direction.Provider>;
}
