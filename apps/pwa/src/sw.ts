/// <reference lib="webworker" />

import { clientsClaim } from "workbox-core";
import { cleanupOutdatedCaches, precacheAndRoute } from "workbox-precaching";

declare let self: ServiceWorkerGlobalScope;

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();
clientsClaim();
self.skipWaiting();

self.addEventListener("push", (event) => {
  let message = "You have a health reminder.";
  try {
    const parsed = event.data?.json() as { message?: string } | undefined;
    if (parsed?.message === "You have a health reminder.") message = parsed.message;
  } catch {
    // Never render provider-controlled or malformed clinical text.
  }
  event.waitUntil(
    self.registration.showNotification(message, {
      body: "Open the app to decrypt details and run the current safety check.",
      tag: "health-steward-generic-reminder",
      data: { url: "/" }
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const existing = windows.find((client) => new URL(client.url).origin === self.location.origin);
      if (existing) return existing.focus();
      return self.clients.openWindow("/");
    })
  );
});
