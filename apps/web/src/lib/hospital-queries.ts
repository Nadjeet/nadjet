import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { components } from "@nadjet/api-client";

import { api } from "@/api";
import { incidentsKey, mapResourcesKey } from "@/live/keys";

import { ApiError, useFallbackPolling } from "./incident-queries";

export type HospitalBoard = components["schemas"]["HospitalBoard"];
export type PreAlert = components["schemas"]["PreAlert"];
export type ReadyState = components["schemas"]["FacilityState"]["ready_state"];

/** Under `incidentsKey`: every incident event (a dispatch, a triage entry) refreshes the board. */
const boardKey = (facilityId: string) => [...incidentsKey, "prealerts", facilityId] as const;

/** Incoming pre-alerts and today's arrivals of one hospital (FR-HSP-001). */
export function useHospitalBoard(facilityId: string | null | undefined) {
  const refetchInterval = useFallbackPolling();
  return useQuery({
    queryKey: boardKey(facilityId ?? ""),
    enabled: Boolean(facilityId),
    refetchInterval,
    queryFn: async () => {
      const { data, response } = await api.GET("/facilities/{facility_id}/prealerts", {
        params: { path: { facility_id: facilityId ?? "" } },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
  });
}

function useRefresh(facilityId: string) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: boardKey(facilityId) });
    void queryClient.invalidateQueries({ queryKey: mapResourcesKey });
  };
}

/** Ready or Divert (FR-HSP-002); Divert raises the E-10 alert for the operators. */
export function useSetReadiness(facilityId: string) {
  const refresh = useRefresh(facilityId);
  return useMutation({
    mutationFn: async (state: ReadyState) => {
      const { data, response } = await api.POST("/facilities/{facility_id}/readiness", {
        params: { path: { facility_id: facilityId } },
        body: { state },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
    onSuccess: refresh,
  });
}

export function useAcknowledgePreAlert(facilityId: string) {
  const refresh = useRefresh(facilityId);
  return useMutation({
    mutationFn: async (incidentId: string) => {
      const { response } = await api.POST("/facilities/{facility_id}/prealerts/{incident_id}/ack", {
        params: { path: { facility_id: facilityId, incident_id: incidentId } },
      });
      if (!response.ok) throw new ApiError(response.status);
    },
    onSuccess: refresh,
  });
}
