import createClient from "openapi-fetch";

import type { paths } from "./schema";

export type { components, paths } from "./schema";

/** Create a typed API client. In the web app the base URL is the Vite `/api` proxy. */
export function createApiClient(baseUrl: string) {
  return createClient<paths>({ baseUrl });
}
