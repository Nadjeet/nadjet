import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardDescription, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function NotFound() {
  const { t } = useTranslation();
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center p-4">
      <Card>
        <CardHeader>
          <h1 className="text-display-xs font-bold">{t("common.notFoundTitle")}</h1>
          <CardDescription>{t("common.notFoundBody")}</CardDescription>
        </CardHeader>
        <Link to="/" className={cn(buttonVariants(), "self-start")}>
          {t("common.backHome")}
        </Link>
      </Card>
    </main>
  );
}
