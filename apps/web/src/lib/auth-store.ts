import { useSyncExternalStore } from "react";

import type { components } from "@nadjet/api-client";

export type User = components["schemas"]["UserOut"];
export type Role = User["role"];
export type Surface = "ops" | "respond" | "hospital";

export type Session = { token: string; user: User; expiresAt: number };

const STORAGE_KEY = "nadjet.session";
const listeners = new Set<() => void>();

function isFresh(session: Session): boolean {
  return session.expiresAt > Date.now();
}

function load(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    return isFresh(session) ? session : null;
  } catch {
    return null;
  }
}

function persist(session: Session | null) {
  try {
    if (session) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage may be unavailable (private mode): the in-memory session still works.
  }
}

let session: Session | null = load();
let expiryTimer: ReturnType<typeof setTimeout> | undefined;

function emit() {
  listeners.forEach((listener) => listener());
}

/** Sign out exactly when the token expires, even if the app makes no request meanwhile. */
function scheduleExpiry() {
  clearTimeout(expiryTimer);
  if (session) expiryTimer = setTimeout(() => authStore.logout(), session.expiresAt - Date.now());
}

/** Token and user live in memory and in `sessionStorage` (cleared when the tab closes). */
export const authStore = {
  /** The current session, or `null` once it is missing or expired. Pure: safe as a snapshot. */
  current(): Session | null {
    return session && isFresh(session) ? session : null;
  },
  setSession(token: string, user: User, expiresInSeconds: number) {
    session = { token, user, expiresAt: Date.now() + expiresInSeconds * 1000 };
    persist(session);
    scheduleExpiry();
    emit();
  },
  logout() {
    clearTimeout(expiryTimer);
    if (!session) return;
    session = null;
    persist(null);
    emit();
  },
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

scheduleExpiry();

export function useSession(): Session | null {
  return useSyncExternalStore(authStore.subscribe, authStore.current);
}

const SURFACE_BY_ROLE: Record<Role, Surface> = {
  operator: "ops",
  supervisor: "ops",
  auditor: "ops",
  admin: "ops",
  responder: "respond",
  hospital: "hospital",
};

export function surfaceFor(role: Role): Surface {
  return SURFACE_BY_ROLE[role];
}

/** Landing path of a role after login. */
export function homeFor(role: Role): "/ops" | "/respond" | "/hospital" {
  return `/${surfaceFor(role)}`;
}
