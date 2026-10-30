import { SirenIcon, UserRoundIcon } from "lucide-react";

import { ResponderRuntime } from "@/pages/respond/responder-runtime";

import { PhoneShell } from "./phone-shell";

export function RespondLayout() {
  return (
    <ResponderRuntime>
      <PhoneShell
        surfaceKey="surface.respond"
        home="/respond"
        nav={[
          { to: "/respond", icon: SirenIcon, labelKey: "nav.myIncidents", exact: true },
          { to: "/respond/profile", icon: UserRoundIcon, labelKey: "nav.profile" },
        ]}
      />
    </ResponderRuntime>
  );
}
