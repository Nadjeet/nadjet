import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import { useIncident } from "@/lib/incident-queries";

import { OfflineBanner } from "./app-controls";
import { MissionCard, MissionHeader, MissionMap, MissionProgress, NoMission } from "./mission";
import { useActiveMission } from "./use-active-mission";
import { PendingActions } from "./pending-actions";

/**
 * Figma "progress" tab: the current mission card with its next status, the signed progress
 * stepper and the map to the hospital, one tap from the tab bar (FR-RSP-002, NFR-INT-001).
 */
export function RespondProgress() {
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
            : t("respond.detail.progressTitle")
        }
      />
      <OfflineBanner />
      {incident ? (
        <>
          <MissionCard incident={incident} />
          <PendingActions incidentId={incident.id} />
          <MissionProgress incident={incident} />
          <MissionMap incident={incident} />
        </>
      ) : (
        <NoMission />
      )}
    </div>
  );
}
