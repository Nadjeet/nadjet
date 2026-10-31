# Nadjet web app

React 19 + Vite + Tailwind 4. One app, four surfaces (PRD §13):

| Path | Surface | Roles | Theme |
|---|---|---|---|
| `/ops/*` | Operator console | operator, supervisor, auditor, admin | light |
| `/respond/*` | Responder app (installable) | responder | light, phone first |
| `/hospital/*` | Hospital view | hospital | light, phone first |
| `/public/*` | Report, try it, privacy (no login, installable) | everyone | light |
| `/login` | Sign in, then redirect by role | everyone | light |

Signed-out users go to `/login`. A signed-in user who opens another surface is redirected to
their own. Sign-out clears the token (kept in memory and `sessionStorage`).

```bash
make dev                                   # API + web, then http://localhost:5173
pnpm --filter @nadjet/web build            # production build (also generates the service worker)
```

Local users: copy `data/seed/users.example.yaml` to `data/seed/users.yaml` and run
`nadjet-api seed-users` (see `docs/ONBOARDING.md`). **No frontend tests** exist or are allowed
(`AGENTS.md`); validate with `make lint`, `make typecheck` and `pnpm --filter @nadjet/web build`.

## Layout

```
src/
  api.ts                  @nadjet/api-client + bearer middleware (401 signs out)
  router.tsx              TanStack Router, code-based, role guards in beforeLoad
  lib/auth-store.ts       token + user, role to surface mapping
  live/                   useLiveEvents: live events stream with reconnect (see below)
  i18n/, locales/         i18next, ar (default, RTL), fr, en
  layouts/                one shell per surface
  pages/                  placeholder pages feature issues replace
  components/ui/          shadcn/ui components, styled to the Figma design system
  components/incident/    PriorityBadge, AiSourceTag, SimulatedLabel, StatusTimeline
```

Feature issues add a screen by replacing a placeholder in `src/router.tsx` (or adding a route
under a surface). Strings go in `src/locales/{ar,fr,en}.json`; use `ms-*`, `me-*`, `ps-*`,
`text-start` and the other logical utilities so Arabic (RTL) needs no extra CSS.

## Live updates

`LiveEventsProvider` (mounted in every signed-in shell) keeps one stream open on `GET /events`
through `@nadjet/api-client`, so the bearer middleware adds the token (a browser `EventSource`
cannot send headers). Each `incident.created|updated|status_changed` event invalidates the
`["incidents"]` and `["incident", id]` queries. On error or end of stream it reconnects with
exponential back-off (1 s to 15 s, with jitter) and refetches the queue once connected. A
silent connection (no heartbeat for 35 s) is treated as lost. `LiveIndicator` shows
live, connecting or reconnecting with text and an icon.

## Design system

Source: the Nadjet Figma file "najat": the design-system page (Colors, Typography, Effects,
buttons, Inputs, check box, Cards, Modals, Dropdowns, icons) and the designer's screens
("control" dashboard, "app" mission, progress and home). The Figma components use a purple
primary; Nadjet uses the brand blue everywhere, as the designer's screens do. **Light mode
only**: there is no dark theme. Tokens live in `src/index.css`. Decisions: `docs/11-technical-decisions.md` TD-54.

- **Brand blue** `brand-100…900`: `#aad4ff #80beff #55a8fe #2a93fe #007dfe #006be0 #003f7f #002a55 #00152a`.
  `brand-500` `#007dfe` is the Figma primary; white on it is only 3.9:1, so it is kept for the
  logo, icons and large figures (KPI values). Text, links, the active navigation item and
  filled controls use `brand-600` `#006be0` (5.0:1), which reads as the same blue.
- **Primary button**: the Figma gradient from `#3568f5`, ending on `#0f7ae8` instead of
  `#80beff` so the white label stays readable (4.5:1 where the label sits). Secondary is the
  Figma green (outline, filled on hover), tertiary the light blue fill, disabled grey.
- **Surfaces and text** (Figma dashboard, slate scale): page `#f2f4f5`, cards white with a
  `#e2e8f0` border, ink `#0f172a`, body `#334155`, muted `#596a80` (slightly darker than the
  Figma `#64748b` so it passes on the page background).
- **Type**: DM Sans (Latin) with Noto Sans Arabic as the Arabic fallback, both self-hosted
  through Fontsource (OFL). Sizes follow the Figma scale (`text-display-xl…xs`,
  `text-body-xl…xs`). Arabic uses no negative letter spacing.
- **Shape and shadow**: radii 6 (chips), 8, 12 (buttons, inputs), 14 (navigation items),
  16 px (cards); `shadow-card` = `0 6px 20px rgb(112 144 176 / 12%)` (Figma dashboard),
  `shadow-soft` = the Figma "drop shadow" effect.
- **Map**: the offline protomaps basemap with a Nadjet flavor (`src/map/style.ts`: grey land,
  white roads, light blue sea) and white rounded controls in the style of mapcn. No online
  tile service is used (FR-MAP-001).
- **Icons**: lucide (the Figma icon set is a line icon family of the same style).
- **Logo**: `src/assets/brand/nadjet-logo.svg`, exported from Figma (node 75:6347), used by
  `Logo` on every surface. `public/favicon.svg`, `logo-mark.svg` and
  `logo-mark-maskable.svg` crop that SVG to the mark; the PNG icons (`pwa-192x192.png`,
  `pwa-512x512.png`, `maskable-512x512.png`, `apple-touch-icon.png`) were rasterised from them
  with resvg. Regenerate them the same way when the logo changes.

### Priority is never colour only (NFR-INT-002)

`PriorityBadge` always shows an icon (different shape per level), `P1…P4` and the level name.
Status and live indicators follow the same rule.

### Contrast (WCAG 2.2 AA: text 4.5:1, large text and UI 3:1)

Computed with the WCAG relative-luminance formula.

| Pair | Colours | Ratio |
|---|---|---|
| text on page | `#0f172a` on `#f2f4f5` | 16.18:1 |
| text on card | `#0f172a` on `#ffffff` | 17.85:1 |
| body text on card | `#334155` on `#ffffff` | 10.35:1 |
| muted text on card | `#596a80` on `#ffffff` | 5.53:1 |
| muted text on page | `#596a80` on `#f2f4f5` | 5.01:1 |
| muted text, placeholder on input | `#596a80` on `#f8fafc` | 5.28:1 |
| primary text, links, tertiary button | `#006be0` on `#ffffff` / `#eff6ff` | 5.02:1 / 4.62:1 |
| active navigation item | `#ffffff` on `#006be0` | 5.02:1 |
| primary button text (gradient centre) | `#ffffff` on `#2271ee` | 4.50:1 |
| queue Review chip | `#003f7f` on `#a6d1ff` | 6.54:1 |
| KPI figures (large text) | `#007dfe` on `#ffffff` | 3.91:1 |
| P1 badge, destructive | `#ffffff` on `#dc2626` | 4.83:1 |
| P2 badge | `#ffffff` on `#c2410c` | 5.18:1 |
| P3 badge | `#ffffff` on `#92400e` | 7.09:1 |
| P4 badge | `#ffffff` on `#475569` | 7.58:1 |
| success button / soft chip | `#ffffff` on `#15803d` / `#15803d` on `#dcfce7` | 5.02:1 / 4.57:1 |
| warning banner | `#0f172a` on `#fef3c7` | 16.03:1 |
| focus ring (UI) | `#007dfe` on `#ffffff` | 3.91:1 |

Focus is shown as an opaque `--ring` ring with a 2 px gap in the background colour (`--shadow-focus`), so the ratios above hold on every control. Disabled controls are exempt from the contrast rule.

## PWA

`vite-plugin-pwa` generates the manifest and a service worker that precaches the app shell
(`/api` and the live stream are never cached). The staff manifest opens `/` (redirect by role
or to login); on public pages the shell swaps in `public/manifest-public.webmanifest`, so
installing from `/public` opens `/public`. Updates use `registerType: "prompt"` with no prompt:
a new version waits until every tab is closed, so nobody is reloaded mid-task. Check
installability in Chrome DevTools > Application > Manifest and Service workers, using
`pnpm --filter @nadjet/web build` then `pnpm --filter @nadjet/web preview`. Offline queues belong to the responder and citizen issues.
