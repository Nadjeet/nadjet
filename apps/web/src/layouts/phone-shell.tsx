import { Link, Outlet } from "@tanstack/react-router";
import { LogOutIcon, MenuIcon, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Avatar } from "@/components/brand/avatar";
import { LanguagePicker } from "@/components/brand/language-picker";
import { LiveIndicator } from "@/components/brand/live-indicator";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { authStore, useSession } from "@/lib/auth-store";
import { cn } from "@/lib/utils";
import { LiveEventsProvider } from "@/live/live-events-provider";

import { SkipLink } from "./skip-link";

export type PhoneNavItem = {
  to: "/respond" | "/respond/progress" | "/respond/triage" | "/respond/profile" | "/hospital";
  icon: LucideIcon;
  label: string;
  exact?: boolean;
};

/** Figma glass circle (app "search" button, node 74:4442): frosted grey, soft inner light. */
export const glassButton =
  "grid size-12 shrink-0 place-items-center rounded-full bg-[#e6e6e6]/90 text-ink shadow-glass backdrop-blur-md transition-colors hover:bg-[#dcdcdc] focus-visible:shadow-focus";

/**
 * Figma "app" shell (home, mission, progress): `#fafafa` page, the avatar with "Welcome back"
 * and the name, a glass button on the other side, and the glass pill tab bar at the bottom
 * (Home, Progress, Triage, Profile) with 54 px targets: every main action is within 2 taps on
 * a 5-inch phone (NFR-INT-001). The glass button opens the language, live status and sign-out.
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
  const [menu, setMenu] = useState(false);
  return (
    <LiveEventsProvider>
      <SkipLink />
      <div
        className={cn(
          "mx-auto flex min-h-dvh w-full flex-col bg-surface-app",
          wide ? "max-w-6xl" : "max-w-[30rem]",
        )}
      >
        <header className="sticky top-0 z-20 flex items-center justify-between gap-4 bg-surface-app/90 px-6 pt-5 pb-3 backdrop-blur">
          {session ? (
            <Link
              to={home}
              aria-label={t(surfaceKey)}
              className="flex min-w-0 items-center gap-3 rounded-full focus-visible:shadow-focus"
            >
              <Avatar />
              <span className="flex min-w-0 flex-col leading-5">
                <span className="text-body-xs font-medium text-ink-muted">
                  {t("common.welcomeBack")} 👋
                </span>
                <span className="truncate text-body-sm font-medium text-[#081021]">
                  {session.user.display_name}
                </span>
              </span>
            </Link>
          ) : (
            <Link to={home} aria-label={t(surfaceKey)}>
              <Logo className="h-9" />
            </Link>
          )}
          <button
            type="button"
            className={glassButton}
            onClick={() => setMenu(true)}
            aria-label={t("respond.menu")}
            title={t("respond.menu")}
          >
            <MenuIcon aria-hidden className="size-6" />
          </button>
        </header>
        <main id="main" className="flex flex-1 flex-col gap-6 px-6 pt-2 pb-36">
          <Outlet />
        </main>
        {nav.length > 1 ? (
          <nav
            aria-label={t("common.mainNavigation")}
            className="fixed inset-x-0 bottom-0 z-20 flex justify-center px-4 pb-[max(2.375rem,env(safe-area-inset-bottom))]"
          >
            <ul className="flex h-[62px] w-full max-w-[23rem] items-center justify-between rounded-[60px] bg-[linear-gradient(rgb(255_255_255/0.6),rgb(255_255_255/0.6)),linear-gradient(#e6e6e6,#e6e6e6)] p-1 shadow-glass backdrop-blur-md">
              {nav.map(({ to, icon: Icon, label, exact }) => (
                <li key={to}>
                  <Link
                    to={to}
                    activeOptions={{ exact }}
                    className="flex h-[54px] w-[72px] flex-col items-center justify-center gap-px rounded-[27px] text-[0.625rem] leading-3 font-medium text-black transition-colors focus-visible:shadow-focus data-[status=active]:bg-white/70 data-[status=active]:text-brand-500"
                  >
                    <Icon aria-hidden className="size-6" />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ) : null}
      </div>

      <Dialog open={menu} onOpenChange={setMenu}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t(surfaceKey)}</DialogTitle>
            <DialogDescription className="sr-only">{t("respond.menu")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <Logo className="h-10 self-start" />
            <div className="flex flex-wrap items-center gap-2">
              <LiveIndicator />
              <LanguagePicker />
            </div>
            {session ? (
              <Button variant="neutral" onClick={() => authStore.logout()}>
                <LogOutIcon aria-hidden className="rtl:-scale-x-100" />
                {t("common.logout")}
              </Button>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </LiveEventsProvider>
  );
}
