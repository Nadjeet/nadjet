import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { registerSW } from "virtual:pwa-register";

import { App } from "./App";
import "./i18n";
import "./index.css";
import { authStore } from "./lib/auth-store";
import { queryClient } from "./lib/query-client";
import { createAppRouter } from "./router";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

const router = createAppRouter(queryClient);

// Sign in, sign out and token expiry re-run the route guards (redirect to /login or to the home).
authStore.subscribe(() => {
  queryClient.clear();
  void router.invalidate();
});

registerSW({ immediate: true });

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App>
        <RouterProvider router={router} />
      </App>
    </QueryClientProvider>
  </StrictMode>,
);
