import { Link } from "@tanstack/react-router";
import {
  ArrowRightIcon,
  CameraIcon,
  MessageSquareTextIcon,
  ShieldCheckIcon,
  SirenIcon,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type PublicPath = "/public/report" | "/public/try" | "/public/privacy";

function Pillar({ icon: Icon, title, to }: { icon: LucideIcon; title: string; to: PublicPath }) {
  return (
    <li>
      <Link
        to={to}
        className="flex items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-card transition-colors hover:border-brand-200 focus-visible:shadow-focus"
      >
        <span
          aria-hidden
          className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-400 text-white"
        >
          <Icon className="size-5" />
        </span>
        <span className="text-body-sm font-medium text-ink">{title}</span>
        <ArrowRightIcon aria-hidden className="ms-auto size-4 text-primary rtl:-scale-x-100" />
      </Link>
    </li>
  );
}

/** Public landing in the Figma style: a blue hero card with the two public actions. */
export function PublicHome() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-6">
      <section className="relative overflow-hidden rounded-[18.6px] bg-[linear-gradient(112deg,#3568f5_7.6%,#80beff_95.5%)] px-6 py-12 text-white shadow-card sm:px-12 sm:py-16">
        <div className="relative flex max-w-3xl flex-col gap-5">
          <h1 className="text-display-xs font-semibold text-balance sm:text-display-md">
            {t("pages.public.home.title")}
          </h1>
          <p className="max-w-2xl text-body-lg text-white/90">{t("pages.public.home.body")}</p>
          <div className="flex flex-wrap gap-3">
            <Link
              to="/public/report"
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "border-white bg-white shadow-float hover:bg-brand-50",
              )}
            >
              <SirenIcon aria-hidden />
              {t("pages.public.cta")}
              <ArrowRightIcon aria-hidden className="rtl:-scale-x-100" />
            </Link>
            <Link
              to="/public/try"
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "border-white/70 bg-transparent text-white hover:bg-white/15",
              )}
            >
              {t("pages.public.learn")}
            </Link>
          </div>
        </div>
      </section>
      <ul className="grid gap-4 sm:grid-cols-3">
        <Pillar icon={MessageSquareTextIcon} title={t("nav.report")} to="/public/report" />
        <Pillar icon={CameraIcon} title={t("nav.try")} to="/public/try" />
        <Pillar icon={ShieldCheckIcon} title={t("nav.privacy")} to="/public/privacy" />
      </ul>
    </div>
  );
}
