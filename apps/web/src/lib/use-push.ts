import { useCallback, useEffect, useState } from "react";

import { api } from "@/api";
import { useSession } from "@/lib/auth-store";

export type PushState = "unsupported" | "denied" | "prompt" | "subscribed" | "error";

function toKey(base64Url: string): Uint8Array<ArrayBuffer> {
  const padded = base64Url
    .replace(/-/g, "+")
    .replace(/_/g, "/")
    .padEnd(Math.ceil(base64Url.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (char) => char.charCodeAt(0));
}

function supported(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

/** The service worker, or `null` when none becomes active (development server, blocked). */
async function registration(): Promise<ServiceWorkerRegistration | null> {
  const timeout = new Promise<null>((resolve) => setTimeout(() => resolve(null), 4_000));
  return Promise.race([navigator.serviceWorker.ready, timeout]);
}

async function subscribe(): Promise<void> {
  const worker = await registration();
  if (!worker) throw new Error("no service worker");
  const { data } = await api.GET("/push/public-key");
  if (!data) throw new Error("web push is not configured");
  const subscription =
    (await worker.pushManager.getSubscription()) ??
    (await worker.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: toKey(data.public_key),
    }));
  const json = subscription.toJSON();
  const keys = json.keys;
  if (!json.endpoint || !keys?.p256dh || !keys.auth) throw new Error("incomplete subscription");
  const { response } = await api.POST("/push/subscriptions", {
    body: { endpoint: json.endpoint, keys: { p256dh: keys.p256dh, auth: keys.auth } },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}

/**
 * Web push for the signed-in responder (FR-RSP-005). When the permission is already granted the
 * browser is (re)subscribed at once, so the API always holds a current endpoint; otherwise the
 * user enables alerts with one tap (`enable`).
 */
export function usePush(): { state: PushState; enable: () => Promise<void> } {
  const userId = useSession()?.user.id;
  const [state, setState] = useState<PushState>(() =>
    !supported() ? "unsupported" : Notification.permission === "denied" ? "denied" : "prompt",
  );

  useEffect(() => {
    if (!userId || !supported() || Notification.permission !== "granted") return;
    let live = true;
    subscribe().then(
      () => live && setState("subscribed"),
      () => live && setState("error"),
    );
    return () => {
      live = false;
    };
  }, [userId]);

  const enable = useCallback(async () => {
    if (!supported()) return;
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      setState(permission === "denied" ? "denied" : "prompt");
      return;
    }
    try {
      await subscribe();
      setState("subscribed");
    } catch {
      setState("error");
    }
  }, []);

  return { state, enable };
}
