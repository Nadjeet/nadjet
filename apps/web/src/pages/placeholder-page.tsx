import { useTranslation } from "react-i18next";

import { Card, CardDescription, CardHeader } from "@/components/ui/card";

export type PageKey = "ops.cameras" | "ops.system" | "public.try" | "public.privacy";

/** Placeholder screen so feature issues can plug into an existing route and shell. */
export function PlaceholderPage({ pageKey }: { pageKey: PageKey }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-display-xs font-semibold text-ink text-balance">{t(`pages.${pageKey}.title`)}</h1>
      <Card>
        <CardHeader>
          <p className="text-body-lg font-medium">{t(`pages.${pageKey}.body`)}</p>
          <CardDescription>{t("pages.soon")}</CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
