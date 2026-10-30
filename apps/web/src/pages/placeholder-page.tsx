import { useTranslation } from "react-i18next";

import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export type PageKey =
  | "ops.overview"
  | "ops.incidents"
  | "ops.cameras"
  | "ops.system"
  | "respond.incidents"
  | "respond.profile"
  | "hospital.incoming"
  | "public.report"
  | "public.try"
  | "public.privacy";

/** Placeholder screen so feature issues can plug into an existing route and shell. */
export function PlaceholderPage({ pageKey }: { pageKey: PageKey }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-display-sm font-bold text-balance">{t(`pages.${pageKey}.title`)}</h1>
      <Card>
        <CardHeader>
          <CardTitle>{t(`pages.${pageKey}.body`)}</CardTitle>
          <CardDescription>{t("pages.soon")}</CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
