import { HospitalIcon } from "lucide-react";

import { PhoneShell } from "./phone-shell";

export function HospitalLayout() {
  return (
    <PhoneShell
      wide
      surfaceKey="surface.hospital"
      home="/hospital"
      nav={[{ to: "/hospital", icon: HospitalIcon, label: "", exact: true }]}
    />
  );
}
