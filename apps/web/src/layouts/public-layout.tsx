import { Link, Outlet } from "@tanstack/react-router";
import { LogInIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Logo } from "@/components/brand/logo";
import { LanguagePicker } from "@/components/brand/language-picker";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { SkipLink } from "./skip-link";
import { usePublicManifest } from "./use-public-manifest";

const link =
  "rounded-xl px-4 py-2 text-body-sm font-medium text-ink-body transition-colors hover:bg-accent hover:text-primary data-[status=active]:bg-primary data-[status=active]:text-white";

/** Public pages (no login): report, try it, privacy. Installable like the responder app. */
export function PublicLayout() {
  const { t } = useTranslation();
  usePublicManifest();
  return (
    <>
      <SkipLink />
      <div className="mx-auto flex min-h-dvh w-full max-w-6xl flex-col gap-6 px-4 pt-4 sm:px-6 sm:pt-6">
        <header className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-card sm:px-5">
          <Link to="/public" aria-label={t("surface.public")} className="rounded-lg">
            <Logo className="h-10" />
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
            <Link to="/login" className={cn(buttonVariants({ variant: "neutral", size: "sm" }))}>
              <LogInIcon aria-hidden className="rtl:-scale-x-100" />
              {t("login.submit")}
            </Link>
          </div>
        </header>
        <main id="main" className="flex flex-1 flex-col gap-6 pb-12">
          <Outlet />
        </main>
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border py-6 text-body-sm text-ink-muted">
          <Logo className="h-8" />
          <span>{t("app.tagline")}</span>
        </footer>
      </div>
    </>
  );
}
