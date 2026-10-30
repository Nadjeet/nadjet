import { useSyncExternalStore } from "react";

import type { CasualtyIn } from "./incident-queries";
import type { ResponderStatus } from "./sms-codes";

/**
 * Actions a responder took without a connection (FR-RSP-004). Each one carries the idempotency
 * key sent with every attempt, so the API applies it once however often it is retried.
 */
type Base = {
  /** Idempotency key. */
  id: string;
  incidentId: string;
  shortCode: string;
  userId: string;
  createdAt: number;
  /** `failed`: the API refused it for good; kept so the responder can see and discard it. */
  state: "pending" | "failed";
  error?: string;
};
export type QueuedAction =
  | (Base & { kind: "status"; status: ResponderStatus })
  | (Base & { kind: "triage"; casualty: CasualtyIn });

const DB_NAME = "nadjet-responder";
const STORE = "actions";

let actions: QueuedAction[] = [];
const listeners = new Set<() => void>();
let loaded: Promise<void> | null = null;
let database: Promise<IDBDatabase | null> | null = null;

function emit() {
  actions = [...actions].sort((a, b) => a.createdAt - b.createdAt);
  listeners.forEach((listener) => listener());
}

/** IndexedDB, or `null` when the browser refuses it (the queue then lives for the session). */
function open(): Promise<IDBDatabase | null> {
  database ??= new Promise((resolve) => {
    try {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "id" });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
  return database;
}

async function run<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>) {
  const db = await open();
  if (!db) return undefined;
  return new Promise<T | undefined>((resolve) => {
    try {
      const request = work(db.transaction(STORE, mode).objectStore(STORE));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(undefined);
    } catch {
      resolve(undefined);
    }
  });
}

/** Read the stored actions once (and again after a tab restart). */
export function loadQueue(): Promise<void> {
  loaded ??= run<QueuedAction[]>("readonly", (store) => store.getAll()).then((stored) => {
    const known = new Set(actions.map((a) => a.id));
    actions = [...actions, ...(stored ?? []).filter((a) => !known.has(a.id))];
    emit();
  });
  return loaded;
}

export async function enqueue(action: QueuedAction): Promise<void> {
  actions = [...actions.filter((a) => a.id !== action.id), action];
  emit();
  await run("readwrite", (store) => store.put(action));
}

export async function update(id: string, patch: Partial<QueuedAction>): Promise<void> {
  const current = actions.find((a) => a.id === id);
  if (!current) return;
  const next = { ...current, ...patch } as QueuedAction;
  actions = actions.map((a) => (a.id === id ? next : a));
  emit();
  await run("readwrite", (store) => store.put(next));
}

export async function remove(id: string): Promise<void> {
  actions = actions.filter((a) => a.id !== id);
  emit();
  await run("readwrite", (store) => store.delete(id));
}

export function snapshot(): QueuedAction[] {
  return actions;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  void loadQueue();
  return () => listeners.delete(listener);
}

/** Every queued action (all users); filter with `userId` before showing or sending. */
export function useQueuedActions(): QueuedAction[] {
  return useSyncExternalStore(subscribe, snapshot);
}
