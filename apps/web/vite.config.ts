import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const apiTarget = process.env.NADJET_API_URL ?? "http://127.0.0.1:8080";

export default defineConfig({
  // `VITE_*` variables live in the repository's `.env` (see `.env.example`).
  envDir: path.resolve(import.meta.dirname, "../.."),
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // "prompt" without a prompt UI: a new version waits until every tab is closed, so an
      // operator or responder is never reloaded mid-task.
      registerType: "prompt",
      includeAssets: [
        "favicon.svg",
        "logo-mark.svg",
        "apple-touch-icon.png",
        "manifest-public.webmanifest",
        "push-sw.js",
      ],
      manifest: {
        name: "Nadjet — نجاة",
        short_name: "Nadjet",
        description: "Road-crash detection and emergency coordination",
        // Opens the right surface: the app redirects by role, or to the login page.
        start_url: "/",
        scope: "/",
        display: "standalone",
        lang: "ar",
        theme_color: "#0053a9",
        background_color: "#f4f7fe",
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
          { src: "maskable-512x512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // Precache the app shell only. API calls and the live stream are never cached.
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        // Push alerts and the tap that opens the incident (FR-RSP-005).
        importScripts: ["push-sw.js"],
      },
    }),
  ],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: apiTarget, rewrite: (path) => path.replace(/^\/api/, "") },
    },
  },
});
