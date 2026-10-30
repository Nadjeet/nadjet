import type { ReactNode } from "react";

import { PushContext } from "@/lib/push-context";
import { useQueueSync } from "@/lib/responder-actions";
import { usePush } from "@/lib/use-push";

/** Background work of the responder app: web push subscription and the offline queue sync. */
export function ResponderRuntime({ children }: { children: ReactNode }) {
  const push = usePush();
  useQueueSync();
  return <PushContext.Provider value={push}>{children}</PushContext.Provider>;
}
