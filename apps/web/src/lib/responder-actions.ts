import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { api } from "@/api";
import { useSession } from "@/lib/auth-store";
import { incidentKey, incidentsKey } from "@/live/keys";

import type { CasualtyIn } from "./incident-queries";
import { enqueue, loadQueue, remove, snapshot, update, type QueuedAction } from "./offline-queue";
import type { ResponderStatus } from "./sms-codes";

export type ActionInput =
  { kind: "status"; status: ResponderStatus } | { kind: "triage"; casualty: CasualtyIn };
type Target = { incidentId: string; shortCode: string; userId: string };

/** `sent`: applied. `retry`: no answer or a temporary fault. `failed`: refused for good. */
type Attempt = { result: "sent" } | { result: "retry" } | { result: "failed"; error: string };

const RETRYABLE = new Set([401, 408, 425, 429]);

async function attempt(action: QueuedAction): Promise<Attempt> {
  try {
    const params = {
      path: { incident_id: action.incidentId },
      header: { "Idempotency-Key": action.id },
    };
    const { response } =
      action.kind === "status"
        ? await api.POST("/incidents/{incident_id}/status", {
            params,
            body: { status: action.status },
          })
        : await api.POST("/incidents/{incident_id}/casualties", {
            params,
            body: action.casualty,
          });
    if (response.ok) return { result: "sent" };
    if (response.status >= 500 || RETRYABLE.has(response.status)) return { result: "retry" };
    return { result: "failed", error: `HTTP ${response.status}` };
  } catch {
    return { result: "retry" }; // network error: the request may or may not have arrived
  }
}

function refresh(queryClient: QueryClient, incidentId: string) {
  void queryClient.invalidateQueries({ queryKey: incidentsKey });
  void queryClient.invalidateQueries({ queryKey: incidentKey(incidentId) });
}

/**
 * Send an action now, or queue it when there is no connection. It is queued under the same
 * idempotency key it was tried with, so a request that reached the API but lost its answer is
 * not applied twice when the queue replays it (AC-RSP-004.1).
 */
export async function submitAction(
  queryClient: QueryClient,
  target: Target,
  input: ActionInput,
): Promise<"sent" | "queued" | { error: string }> {
  const action = {
    ...input,
    ...target,
    id: crypto.randomUUID(),
    createdAt: Date.now(),
    state: "pending" as const,
  } as QueuedAction;
  if (navigator.onLine) {
    const outcome = await attempt(action);
    if (outcome.result === "sent") {
      refresh(queryClient, action.incidentId);
      return "sent";
    }
    if (outcome.result === "failed") return { error: outcome.error };
  }
  await enqueue(action);
  return "queued";
}

let syncing = false;

/** Replay the signed-in user's queued actions in order; stops at the first one still offline. */
export async function syncQueue(queryClient: QueryClient, userId: string): Promise<void> {
  if (syncing || !navigator.onLine) return;
  syncing = true;
  try {
    await loadQueue();
    for (const action of snapshot()) {
      if (action.userId !== userId || action.state !== "pending") continue;
      const outcome = await attempt(action);
      if (outcome.result === "retry") return;
      if (outcome.result === "sent") {
        await remove(action.id);
        refresh(queryClient, action.incidentId);
      } else {
        await update(action.id, { state: "failed", error: outcome.error });
      }
    }
  } finally {
    syncing = false;
  }
}

/** Sync when the app opens, when the connection returns and every 20 s while actions wait. */
export function useQueueSync() {
  const queryClient = useQueryClient();
  const userId = useSession()?.user.id;
  useEffect(() => {
    if (!userId) return;
    const run = () => void syncQueue(queryClient, userId);
    run();
    window.addEventListener("online", run);
    const timer = setInterval(run, 20_000);
    return () => {
      window.removeEventListener("online", run);
      clearInterval(timer);
    };
  }, [queryClient, userId]);
}
