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
    // A rejected token ends the session; a failed login attempt is not a rejected token.
    const isLogin = new URL(request.url).pathname.endsWith("/auth/login");
    if (response.status === 401 && !isLogin) authStore.logout();
    return response;
  },
});
