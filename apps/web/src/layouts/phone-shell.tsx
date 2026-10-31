import { Link, Outlet } from "@tanstack/react-router";
import { LogOutIcon, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LanguagePicker } from "@/components/brand/language-picker";
import { LiveIndicator } from "@/components/brand/live-indicator";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { authStore, useSession } from "@/lib/auth-store";
import { initials } from "@/lib/initials";
import { cn } from "@/lib/utils";
import { LiveEventsProvider } from "@/live/live-events-provider";

import { SkipLink } from "./skip-link";

export type PhoneNavItem = {
  to: "/respond" | "/respond/profile" | "/hospital";
  icon: LucideIcon;
  labelKey: "nav.myIncidents" | "nav.profile" | "nav.incoming";
  exact?: boolean;
};

/**
 * Figma "app" shell for the responder app and the hospital view: a "Welcome back" header with
 * the user's initials, and a floating pill navigation at the bottom with 56 px targets (every
 * main action is within 2 taps on a 5-inch phone, NFR-INT-001).
 */
export function PhoneShell({
  surfaceKey,
  home,
  nav,
  wide = false,
}: {
  surfaceKey: "surface.respond" | "surface.hospital";
  home: "/respond" | "/hospital";
  nav: PhoneNavItem[];
  /** Tablet layout: use the whole width (the hospital view is read at arm's length). */
  wide?: boolean;
}) {
  const { t } = useTranslation();
  const session = useSession();
  return (
    <LiveEventsProvider>
      <SkipLink />
      <div
        className={cn(
          "mx-auto flex min-h-dvh w-full flex-col bg-background",
          wide ? "max-w-6xl" : "max-w-xl",
        )}
      >
        <header className="sticky top-0 z-20 flex flex-col gap-3 bg-background/90 px-4 pt-4 pb-3 backdrop-blur sm:px-6">
          <div className="flex items-center justify-between gap-3">
            {session ? (
              <Link
                to={home}
                aria-label={t(surfaceKey)}
                className="flex min-w-0 items-center gap-3 rounded-full focus-visible:shadow-focus"
              >
                <span
                  aria-hidden
                  className="grid size-11 shrink-0 place-items-center rounded-full bg-[linear-gradient(135deg,#3568f5,#55a8fe)] text-body-sm font-semibold text-white"
                >
                  {initials(session.user.display_name)}
                </span>
                <span className="flex min-w-0 flex-col leading-tight">
                  <span className="text-body-xs text-ink-muted">
                    {t("common.welcomeBack")} 👋
                  </span>
                  <span className="truncate text-body-md font-semibold text-ink">
                    {session.user.display_name}
                  </span>
                </span>
              </Link>
            ) : (
              <Link to={home} aria-label={t(surfaceKey)}>
                <Logo className="h-9" />
              </Link>
            )}
            {session ? (
              <Button
                variant="neutral"
                size="icon"
                className="rounded-full"
                onClick={() => authStore.logout()}
                aria-label={t("common.logout")}
                title={t("common.logout")}
              >
                <LogOutIcon aria-hidden className="rtl:-scale-x-100" />
              </Button>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-body-xs font-medium tracking-[0.5px] text-ink-muted uppercase">
              {t(surfaceKey)}
            </span>
            <div className="flex items-center gap-2">
              <LiveIndicator />
              <LanguagePicker />
            </div>
          </div>
        </header>
        <main id="main" className="flex flex-1 flex-col gap-5 px-4 pt-2 pb-32 sm:px-6">
          <Outlet />
        </main>
        {nav.length > 1 ? (
          <nav
            aria-label={t("common.mainNavigation")}
            className="fixed inset-x-0 bottom-0 z-20 px-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
          >
            <ul
              className={cn(
                "mx-auto flex gap-1 rounded-full border border-border bg-card p-1.5 shadow-float",
                wide ? "max-w-md" : "max-w-sm",
              )}
            >
              {nav.map(({ to, icon: Icon, labelKey, exact }) => (
                <li key={to} className="flex-1">
                  <Link
                    to={to}
                    activeOptions={{ exact }}
                    className="flex min-h-14 flex-col items-center justify-center gap-0.5 rounded-full px-2 text-body-xs font-medium text-ink-body transition-colors hover:text-primary data-[status=active]:bg-accent data-[status=active]:text-primary"
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
