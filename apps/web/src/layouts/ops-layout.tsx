import { Link, Outlet } from "@tanstack/react-router";
import {
  ActivityIcon,
  BarChart3Icon,
  FlaskConicalIcon,
  LayoutDashboardIcon,
  UsersIcon,
  VideoIcon,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { Logo } from "@/components/brand/logo";
import { authStore } from "@/lib/auth-store";
import { cn } from "@/lib/utils";
import { LiveEventsProvider } from "@/live/live-events-provider";

import { IncidentSearch } from "./incident-search";
import { OpsAccount } from "./ops-account";
import { SkipLink } from "./skip-link";

type NavTarget =
  "/ops" | "/ops/cameras" | "/ops/system" | "/ops/kpis" | "/ops/evaluation" | "/ops/admin";

type NavItem = { to: NavTarget; label: string; icon: LucideIcon; exact?: boolean };

/**
 * Figma "control" sidebar: the active item is a solid blue 14 px pill, the others are blue-tinted
 * text on the page background. On small screens the items become a scrollable row.
 */
const link = cn(
  "flex min-h-11 items-center gap-3 rounded-xl px-4 text-body-md font-medium whitespace-nowrap text-ink-body transition-colors",
  "hover:bg-card hover:text-primary [&_svg]:text-brand-400 hover:[&_svg]:text-primary",
  "data-[status=active]:bg-primary data-[status=active]:text-white data-[status=active]:shadow-[0_8px_20px_-8px_rgb(0_107_224/0.6)] data-[status=active]:[&_svg]:text-white",
);

function NavSection({ title, items }: { title: string; items: NavItem[] }) {
  return (
    <div className="flex shrink-0 items-center gap-1 lg:flex-col lg:items-stretch lg:gap-2">
      <p className="hidden px-4 pt-2 text-body-xs font-medium tracking-[0.5px] text-ink-muted uppercase lg:block">
        {title}
      </p>
      <ul className="flex gap-1 lg:flex-col lg:gap-1.5">
        {items.map(({ to, label, icon: Icon, exact }) => (
          <li key={to}>
            <Link to={to} activeOptions={{ exact: exact ?? false }} className={link}>
              <Icon aria-hidden className="size-[18px]" />
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Operator console shell (operator, supervisor, auditor, admin), Figma "control" layout. */
export function OpsLayout() {
  const { t } = useTranslation();
  const role = authStore.current()?.user.role;
  const analyst = role === "supervisor" || role === "admin";

  const operations: NavItem[] = [
    { to: "/ops", label: t("nav.overview"), icon: LayoutDashboardIcon, exact: true },
    { to: "/ops/cameras", label: t("nav.cameras"), icon: VideoIcon },
  ];
  const analytics: NavItem[] = analyst
    ? [
        { to: "/ops/kpis", label: t("nav.kpis"), icon: BarChart3Icon },
        { to: "/ops/evaluation", label: t("nav.evaluation"), icon: FlaskConicalIcon },
      ]
    : [];
  const platform: NavItem[] = [
    { to: "/ops/system", label: t("nav.system"), icon: ActivityIcon },
    ...(role === "admin"
      ? [{ to: "/ops/admin", label: t("nav.admin"), icon: UsersIcon } as NavItem]
      : []),
  ];

  return (
    <LiveEventsProvider>
      <SkipLink />
      <div className="flex min-h-dvh flex-col bg-background lg:flex-row">
        <aside className="flex flex-col gap-6 px-4 pt-5 lg:sticky lg:top-0 lg:h-dvh lg:w-72 lg:shrink-0 lg:overflow-y-auto lg:px-6 lg:py-8">
          <Link to="/ops" className="w-fit rounded-lg px-2" aria-label={t("surface.ops")}>
            <Logo className="h-11 lg:h-12" />
          </Link>
          <nav
            aria-label={t("common.mainNavigation")}
            className="-mx-4 flex gap-1 overflow-x-auto px-4 pb-1 lg:mx-0 lg:flex-col lg:gap-6 lg:overflow-visible lg:px-0"
          >
            <NavSection title={t("nav.sections.operations")} items={operations} />
            {analytics.length ? (
              <NavSection title={t("nav.sections.analytics")} items={analytics} />
            ) : null}
            <NavSection title={t("nav.sections.platform")} items={platform} />
          </nav>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col gap-6 p-4 sm:p-6 lg:ps-2 lg:pe-8 lg:pt-8">
          <header className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-card sm:px-5">
            <IncidentSearch />
            <OpsAccount />
          </header>
          <main id="main" className="flex flex-1 flex-col gap-6 pb-6">
            <Outlet />
          </main>
        </div>
      </div>
    </LiveEventsProvider>
  );
}
