import { Link } from "@tanstack/react-router";
import { ArrowRightIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function PublicHome() {
  const { t } = useTranslation();
  return (
    <section className="flex flex-col gap-6 py-8 sm:py-16">
      <h1 className="max-w-3xl text-display-xs font-semibold text-ink text-balance sm:text-display-lg">
        {t("pages.public.home.title")}
      </h1>
      <p className="max-w-2xl text-body-lg text-ink-muted">{t("pages.public.home.body")}</p>
      <div className="flex flex-wrap gap-3">
        <Link to="/public/report" className={cn(buttonVariants({ size: "lg" }))}>
          {t("pages.public.cta")}
          <ArrowRightIcon aria-hidden className="rtl:-scale-x-100" />
        </Link>
        <Link to="/public/try" className={cn(buttonVariants({ variant: "outline", size: "lg" }))}>
          {t("pages.public.learn")}
        </Link>
      </div>
    </section>
  );
}
