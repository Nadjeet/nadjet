import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { components } from "@nadjet/api-client";

import { api } from "@/api";
import { camerasKey, incidentKey, incidentsKey } from "@/live/keys";
import { useLiveEvents } from "@/live/live-events-context";

export type Incident = components["schemas"]["IncidentOut"];
export type IncidentDetail = components["schemas"]["IncidentDetail"];
export type IncidentStatus = components["schemas"]["IncidentStatus"];
export type RejectReason = components["schemas"]["RejectReason"];
export type ManualIncident = components["schemas"]["ManualIncidentIn"];
export type Camera = components["schemas"]["CameraOut"];
export type MapResources = components["schemas"]["MapResources"];
export type Integrity = components["schemas"]["IntegrityOut"];
export type CandidateSource = components["schemas"]["CandidateSource"];
export type Recommendations = components["schemas"]["IncidentRecommendations"];
export type RankedResource = components["schemas"]["RankedResource"];
export type DispatchRow = components["schemas"]["DispatchOut"];

export type QueueFilters = {
  /** `open` is every incident that is not rejected, merged or closed. */
  status: "open" | IncidentStatus;
  priority?: 1 | 2 | 3 | 4;
  source?: CandidateSource;
};

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number) {
    super(`API answered HTTP ${status}`);
    this.status = status;
  }
}

/** While the live stream is down the data is refetched on a timer (FR-MAP-002). */
function useFallbackPolling(): number | false {
  return useLiveEvents() === "live" ? false : 5_000;
}

export function useIncidents(filters: QueueFilters) {
  const refetchInterval = useFallbackPolling();
  return useQuery({
    queryKey: [...incidentsKey, filters],
    refetchInterval,
    queryFn: async () => {
      const { data, response } = await api.GET("/incidents", {
        params: {
          query: {
            open_only: filters.status === "open" ? true : undefined,
            status: filters.status === "open" ? undefined : filters.status,
            priority: filters.priority,
            source: filters.source,
            limit: 200,
          },
        },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
  });
}

export function useIncident(id: string) {
  const refetchInterval = useFallbackPolling();
  return useQuery({
    queryKey: incidentKey(id),
    refetchInterval,
    queryFn: async () => {
      const { data, response } = await api.GET("/incidents/{incident_id}", {
        params: { path: { incident_id: id } },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
  });
}

export function useCameras() {
  return useQuery({
    queryKey: camerasKey,
    queryFn: async () => {
      const { data, response } = await api.GET("/cameras");
      if (!data) throw new ApiError(response.status);
      return data;
    },
  });
}

export function useMapResources() {
  return useQuery({
    queryKey: ["map", "resources"],
    refetchInterval: 30_000,
    queryFn: async () => {
      const { data, response } = await api.GET("/map/resources");
      if (!data) throw new ApiError(response.status);
      return data;
    },
  });
}

/** Refresh the queue and the touched incidents without waiting for the live event. */
function useRefresh() {
  const queryClient = useQueryClient();
  return (...ids: string[]) => {
    void queryClient.invalidateQueries({ queryKey: incidentsKey });
    for (const id of ids) void queryClient.invalidateQueries({ queryKey: incidentKey(id) });
  };
}

export function useVerify(id: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async () => {
      const { data, response } = await api.POST("/incidents/{incident_id}/verify", {
        params: { path: { incident_id: id } },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
    onSuccess: () => refresh(id),
  });
}

export function useReject(id: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (reason: RejectReason) => {
      const { data, response } = await api.POST("/incidents/{incident_id}/reject", {
        params: { path: { incident_id: id } },
        body: { reason },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
    onSuccess: () => refresh(id),
  });
}

export function useMerge(id: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (into: string) => {
      const { data, response } = await api.POST("/incidents/{incident_id}/merge", {
        params: { path: { incident_id: id } },
        body: { into },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
    onSuccess: (target) => refresh(id, target.id),
  });
}

export function useCreateIncident() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (body: ManualIncident) => {
      const { data, response } = await api.POST("/incidents", { body });
      if (!data) throw new ApiError(response.status);
      return data;
    },
    onSuccess: (created) => refresh(created.id),
  });
}

export function useIntegrity(id: string) {
  return useMutation({
    mutationFn: async () => {
      const { data, response } = await api.GET("/incidents/{incident_id}/integrity", {
        params: { path: { incident_id: id } },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
  });
}

/** Fetch an evidence file with the session token; every call is audited by the API. */
export async function fetchEvidence(incidentId: string, evidenceId: string): Promise<Blob> {
  const { data, response } = await api.GET("/incidents/{incident_id}/evidence/{evidence_id}", {
    params: { path: { incident_id: incidentId, evidence_id: evidenceId } },
    parseAs: "blob",
  });
  if (!data) throw new ApiError(response.status);
  return data;
}

/** Ranked units and hospitals with routes; ranking is the server's (FR-DSP-001/002). */
export function useRecommendations(id: string, enabled: boolean) {
  return useQuery({
    queryKey: [...incidentKey(id), "recommendations"],
    enabled,
    queryFn: async () => {
      const { data, response } = await api.GET("/incidents/{incident_id}/recommendations", {
        params: { path: { incident_id: id } },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
  });
}

/** Dispatches with the delivery status of each notification (refetched with the incident). */
export function useDispatches(id: string, enabled: boolean) {
  const refetchInterval = useFallbackPolling();
  return useQuery({
    queryKey: [...incidentKey(id), "dispatches"],
    enabled,
    refetchInterval,
    queryFn: async () => {
      const { data, response } = await api.GET("/incidents/{incident_id}/dispatches", {
        params: { path: { incident_id: id } },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
  });
}

export function useDispatch(id: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (body: { unit_ids: string[]; hospital_id: string }) => {
      const { data, response } = await api.POST("/incidents/{incident_id}/dispatch", {
        params: { path: { incident_id: id } },
        body,
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
    onSuccess: () => refresh(id),
  });
}

export function useChangeHospital(id: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (hospitalId: string) => {
      const { data, response } = await api.POST("/incidents/{incident_id}/hospital", {
        params: { path: { incident_id: id } },
        body: { hospital_id: hospitalId },
      });
      if (!data) throw new ApiError(response.status);
      return data;
    },
    onSuccess: () => refresh(id),
  });
}
