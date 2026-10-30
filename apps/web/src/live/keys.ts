/** Query keys the live events invalidate: the queue, the changed incident and the cameras. */
export const incidentsKey = ["incidents"] as const;
export const incidentKey = (id: string) => ["incident", id] as const;
export const camerasKey = ["cameras"] as const;
/** Worker health (`/system/cameras`); under `camerasKey` so camera events refresh it too. */
export const systemCamerasKey = [...camerasKey, "system"] as const;
