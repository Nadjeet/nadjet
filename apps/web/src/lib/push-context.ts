import { createContext, useContext } from "react";

import type { PushState } from "./use-push";

export type PushValue = { state: PushState; enable: () => Promise<void> };

export const PushContext = createContext<PushValue>({
  state: "unsupported",
  enable: () => Promise.resolve(),
});

/** Push state of the responder app; one subscription attempt for the whole surface. */
export function usePushState(): PushValue {
  return useContext(PushContext);
}
