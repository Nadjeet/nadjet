import { BriefcaseMedicalIcon, HouseIcon, UserIcon, WaypointsIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ResponderRuntime } from "@/pages/respond/responder-runtime";

import { PhoneShell } from "./phone-shell";

/** Responder app with the Figma tab bar: Home, Progress, Triage, Profile. */
export function RespondLayout() {
  const { t } = useTranslation();
  return (
    <ResponderRuntime>
      <PhoneShell
        surfaceKey="surface.respond"
        home="/respond"
        nav={[
          { to: "/respond", icon: HouseIcon, label: t("respond.nav.home"), exact: true },
          { to: "/respond/progress", icon: WaypointsIcon, label: t("respond.nav.progress") },
          { to: "/respond/triage", icon: BriefcaseMedicalIcon, label: t("respond.nav.triage") },
          { to: "/respond/profile", icon: UserIcon, label: t("respond.nav.profile") },
        ]}
      />
    </ResponderRuntime>
  );
}
