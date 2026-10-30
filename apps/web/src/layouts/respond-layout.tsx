import { SirenIcon, UserRoundIcon } from "lucide-react";

import { PhoneShell } from "./phone-shell";

export function RespondLayout() {
  return (
    <PhoneShell
      surfaceKey="surface.respond"
      home="/respond"
      nav={[
        { to: "/respond", icon: SirenIcon, labelKey: "nav.myIncidents", exact: true },
        { to: "/respond/profile", icon: UserRoundIcon, labelKey: "nav.profile" },
      ]}
    />
  );
}
