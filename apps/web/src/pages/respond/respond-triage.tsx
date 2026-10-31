import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import { useIncident } from "@/lib/incident-queries";

import { OfflineBanner } from "./app-controls";
import { MissionCard, MissionHeader, NoMission } from "./mission";
import { useActiveMission } from "./use-active-mission";
import { TriageForm } from "./triage-form";

/** Figma "triage" tab: the current mission summary over the START triage form (FR-RSP-003). */
export function RespondTriage() {
  const { t } = useTranslation();
  const active = useActiveMission();
  const query = useIncident(active.incident?.id ?? "");
  if (active.isPending || (active.incident && query.isPending)) {
    return <Skeleton className="h-64 w-full rounded-xl" />;
  }
  const incident = query.data;
  return (
    <div className="flex flex-col gap-6">
      <MissionHeader
        back={false}
        title={
          incident
            ? t("respond.detail.mission", { code: incident.short_code })
            : t("respond.nav.triage")
        }
      />
      <OfflineBanner />
      {incident ? (
        <>
          <MissionCard incident={incident} actions={false} />
          <TriageForm incident={incident} />
        </>
      ) : (
        <NoMission />
      )}
    </div>
  );
}
