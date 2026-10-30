import { createApiClient } from "@nadjet/api-client";

/** Single API client for the app. Requests go through the Vite `/api` proxy in development. */
export const api = createApiClient("/api");
