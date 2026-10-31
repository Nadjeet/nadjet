import { Link, Outlet } from "@tanstack/react-router";
import {
  ActivityIcon,
  BarChart3Icon,
  FlaskConicalIcon,
  PaletteIcon,
  SirenIcon,
  UsersIcon,
  VideoIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { Logo } from "@/components/brand/logo";
import { authStore } from "@/lib/auth-store";
import { LiveEventsProvider } from "@/live/live-events-provider";

import { AccountActions } from "./account-actions";
import { SkipLink } from "./skip-link";

const link =
  "flex min-h-11 items-center gap-3 rounded-full px-4 py-2 text-body-sm font-medium whitespace-nowrap text-sidebar-foreground transition-colors hover:bg-sidebar-accent data-[status=active]:bg-sidebar-primary data-[status=active]:text-sidebar-primary-foreground";

/** Operator console shell (operator, supervisor, auditor, admin): dark theme, side navigation. */
export function OpsLayout() {
  const { t } = useTranslation();
  const role = authStore.current()?.user.role;
  const analyst = role === "supervisor" || role === "admin";
  return (
    <LiveEventsProvider>
      <SkipLink />
      <div className="flex min-h-dvh flex-col lg:flex-row">
        <aside className="flex flex-col gap-4 border-b border-sidebar-border bg-sidebar p-4 lg:sticky lg:top-0 lg:h-dvh lg:w-64 lg:shrink-0 lg:border-e lg:border-b-0">
          <Link to="/ops" className="rounded-full" aria-label={t("surface.ops")}>
            <Logo />
          </Link>
          <nav aria-label={t("common.mainNavigation")} className="-mx-1 overflow-x-auto px-1">
            <ul className="flex gap-1 lg:flex-col">
              <li>
                <Link to="/ops" activeOptions={{ exact: true }} className={link}>
                  <SirenIcon aria-hidden className="size-5" />
                  {t("nav.overview")}
                </Link>
              </li>
              <li>
                <Link to="/ops/cameras" className={link}>
                  <VideoIcon aria-hidden className="size-5" />
                  {t("nav.cameras")}
                </Link>
              </li>
              <li>
                <Link to="/ops/system" className={link}>
                  <ActivityIcon aria-hidden className="size-5" />
                  {t("nav.system")}
                </Link>
              </li>
              {analyst ? (
                <>
                  <li>
                    <Link to="/ops/kpis" className={link}>
                      <BarChart3Icon aria-hidden className="size-5" />
                      {t("nav.kpis")}
                    </Link>
                  </li>
                  <li>
                    <Link to="/ops/evaluation" className={link}>
                      <FlaskConicalIcon aria-hidden className="size-5" />
                      {t("nav.evaluation")}
                    </Link>
                  </li>
                </>
              ) : null}
              {role === "admin" ? (
                <li>
                  <Link to="/ops/admin" className={link}>
                    <UsersIcon aria-hidden className="size-5" />
                    {t("nav.admin")}
                  </Link>
                </li>
              ) : null}
              <li>
                <Link to="/ops/design" className={link}>
                  <PaletteIcon aria-hidden className="size-5" />
                  {t("nav.design")}
                </Link>
              </li>
            </ul>
          </nav>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-6">
            <span className="text-body-sm font-medium text-muted-foreground">
              {t("surface.ops")}
            </span>
            <AccountActions />
          </header>
          <main id="main" className="flex flex-1 flex-col gap-6 p-4 sm:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </LiveEventsProvider>
  );
}
