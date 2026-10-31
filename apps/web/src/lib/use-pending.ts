import { useSession } from "@/lib/auth-store";
import { useQueuedActions, type QueuedAction } from "@/lib/offline-queue";

/** The signed-in user's queued actions, optionally of one incident. */
export function usePendingActions(incidentId?: string): QueuedAction[] {
  const userId = useSession()?.user.id;
  return useQueuedActions().filter(
    (a) => a.userId === userId && (incidentId === undefined || a.incidentId === incidentId),
  );
}
