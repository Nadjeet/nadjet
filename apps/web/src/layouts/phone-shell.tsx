import { Link, Outlet } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Logo } from "@/components/brand/logo";
import { LiveEventsProvider } from "@/live/live-events-provider";

import { AccountActions } from "./account-actions";
import { SkipLink } from "./skip-link";
import { useSurfaceTheme } from "./use-surface-theme";

export type PhoneNavItem = {
  to: "/respond" | "/respond/profile" | "/hospital";
  icon: LucideIcon;
  labelKey: "nav.myIncidents" | "nav.profile" | "nav.incoming";
  exact?: boolean;
};

/**
 * Light, single-column shell for the responder app and hospital view. Built for a 5-inch phone:
 * bottom navigation with 56 px targets (every main action is within 2 taps, NFR-INT-001).
 */
export function PhoneShell({
  surfaceKey,
  home,
  nav,
}: {
  surfaceKey: "surface.respond" | "surface.hospital";
  home: "/respond" | "/hospital";
  nav: PhoneNavItem[];
}) {
  const { t } = useTranslation();
  useSurfaceTheme("light");
  return (
    <LiveEventsProvider>
      <SkipLink />
      <div className="mx-auto flex min-h-dvh max-w-3xl flex-col">
        <header className="sticky top-0 z-20 flex flex-col gap-2 border-b border-border bg-background/95 px-4 py-3 backdrop-blur">
          <div className="flex items-center justify-between gap-3">
            <Link to={home} aria-label={t(surfaceKey)} className="rounded-full">
              <Logo />
            </Link>
            <span className="text-body-sm font-medium text-muted-foreground">{t(surfaceKey)}</span>
          </div>
          <AccountActions />
        </header>
        <main id="main" className="flex flex-1 flex-col gap-4 p-4 pb-28">
          <Outlet />
        </main>
        {nav.length > 1 ? (
          <nav
            aria-label={t("common.mainNavigation")}
            className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-card pb-[env(safe-area-inset-bottom)] shadow-soft"
          >
            <ul className="mx-auto flex max-w-3xl">
              {nav.map(({ to, icon: Icon, labelKey, exact }) => (
                <li key={to} className="flex-1">
                  <Link
                    to={to}
                    activeOptions={{ exact }}
                    className="flex min-h-14 flex-col items-center justify-center gap-1 px-2 py-2 text-body-xs font-medium text-muted-foreground data-[status=active]:text-primary"
                  >
                    <Icon aria-hidden className="size-6" />
                    {t(labelKey)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ) : null}
      </div>
    </LiveEventsProvider>
  );
}
