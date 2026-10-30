import { Link, Outlet } from "@tanstack/react-router";
import { LogInIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Logo } from "@/components/brand/logo";
import { LanguagePicker } from "@/components/brand/language-picker";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { SkipLink } from "./skip-link";
import { usePublicManifest } from "./use-public-manifest";
import { useSurfaceTheme } from "./use-surface-theme";

const link =
  "rounded-full px-4 py-2 text-body-sm font-medium text-foreground transition-colors hover:bg-accent data-[status=active]:bg-accent data-[status=active]:text-accent-foreground";

/** Public pages (no login): report, try it, privacy. Installable like the responder app. */
export function PublicLayout() {
  const { t } = useTranslation();
  useSurfaceTheme("light");
  usePublicManifest();
  return (
    <>
      <SkipLink />
      <div className="mx-auto flex min-h-dvh max-w-5xl flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
          <Link to="/public" aria-label={t("surface.public")} className="rounded-full">
            <Logo />
          </Link>
          <nav aria-label={t("common.mainNavigation")}>
            <ul className="flex flex-wrap items-center gap-1">
              <li>
                <Link to="/public/report" className={link}>
                  {t("nav.report")}
                </Link>
              </li>
              <li>
                <Link to="/public/try" className={link}>
                  {t("nav.try")}
                </Link>
              </li>
              <li>
                <Link to="/public/privacy" className={link}>
                  {t("nav.privacy")}
                </Link>
              </li>
            </ul>
          </nav>
          <div className="flex items-center gap-2">
            <LanguagePicker />
            <Link to="/login" className={cn(buttonVariants({ variant: "outline", size: "xs" }))}>
              <LogInIcon aria-hidden className="rtl:-scale-x-100" />
              {t("login.submit")}
            </Link>
          </div>
        </header>
        <main id="main" className="flex flex-1 flex-col gap-6 px-4 pb-12">
          <Outlet />
        </main>
        <footer className="px-4 py-6 text-body-sm text-muted-foreground">{t("app.tagline")}</footer>
      </div>
    </>
  );
}
