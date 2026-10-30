/** Query keys the live events invalidate: the queue and the changed incident. */
export const incidentsKey = ["incidents"] as const;
export const incidentKey = (id: string) => ["incident", id] as const;
