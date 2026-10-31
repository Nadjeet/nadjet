import { createContext, useContext } from "react";

/** `live`: stream open. `connecting`: first attempt. `reconnecting`: lost, retrying with back-off. */
export type LiveStatus = "connecting" | "live" | "reconnecting";

export const LiveEventsContext = createContext<LiveStatus>("connecting");

export function useLiveEvents(): LiveStatus {
  return useContext(LiveEventsContext);
}
