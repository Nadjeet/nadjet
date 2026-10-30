// Web Push handlers, loaded by the generated service worker (`importScripts`).
// The API sends `{ incident_id, text }`; a tap opens that incident in the responder app.

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    // A malformed payload still deserves a visible alert.
  }
  event.waitUntil(
    self.registration.showNotification("Nadjet", {
      body: data.text || "",
      tag: data.incident_id || "nadjet",
      renotify: true,
      requireInteraction: true,
      icon: "/pwa-192x192.png",
      badge: "/pwa-192x192.png",
      data: { incidentId: data.incident_id || null },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const id = event.notification.data && event.notification.data.incidentId;
  const url = id ? `/respond/incidents/${id}` : "/respond";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if ("focus" in client && new URL(client.url).origin === self.location.origin) {
          if ("navigate" in client) client.navigate(url);
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
