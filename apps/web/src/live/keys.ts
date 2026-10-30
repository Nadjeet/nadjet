/** Query keys the live events invalidate: the queue and the changed incident. */
export const incidentsKey = ["incidents"] as const;
export const incidentKey = (id: string) => ["incident", id] as const;

/** Camera status and worker health (`/system/cameras`), refreshed on camera_fault / recovered. */
export const camerasKey = ["system", "cameras"] as const;
