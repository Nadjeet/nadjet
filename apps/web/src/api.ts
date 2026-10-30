import { createApiClient } from "@nadjet/api-client";

import { authStore } from "@/lib/auth-store";

/** Single API client for the app. Requests go through the Vite `/api` proxy in development. */
export const api = createApiClient("/api");

api.use({
  onRequest({ request }) {
    const session = authStore.current();
    if (session) request.headers.set("Authorization", `Bearer ${session.token}`);
    return request;
  },
  onResponse({ request, response }) {
    // Only the token that was rejected ends the session: a late 401 for an older token
    // must not sign out a session opened since. A failed login is not a rejected token.
    const isLogin = new URL(request.url).pathname.endsWith("/auth/login");
    const current = authStore.current();
    const sentCurrentToken =
      current !== null && request.headers.get("Authorization") === `Bearer ${current.token}`;
    if (response.status === 401 && !isLogin && sentCurrentToken) authStore.logout();
    return response;
  },
});
