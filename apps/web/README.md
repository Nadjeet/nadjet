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
("control" dashboard, "app" home, mission and progress). The file is the source of truth and
its values are used exactly (TD-55, superseding the contrast tweaks of TD-54). The Figma
components use a purple tertiary; Nadjet maps it to the brand blue, as the designer's screens
do. **Light mode only**: there is no dark theme. Tokens live in `src/index.css`.

- **Brand blue** `brand-50…900`, Figma primary `brand-500` `#007dfe`, indigo `#3568f5`.
- **Buttons** (node 10:2097): primary `#55a8fe` at rest, the 112° `#3568f5 → #80beff` gradient
  on hover and pressed (`variant="gradient"` keeps it at rest, for the main call to action of a
  screen); secondary green outline `#22c55e`, filled on hover, `#16a34a` pressed; tertiary
  `brand-50` with indigo text; disabled `#e8ecf3` with `#899cc9` text. Sizes 48/44/40/36 px.
- **Status colours**: success `#22c55e` (chip `#4ade80`, text `#059669`, soft `#dcfce7`),
  warning `#f59e0b` (soft `#fef3c7`), error `#ef4444` (strong `#e11d48`, soft `#fee2e2`).
- **Surfaces and text** (slate scale): page `#f2f4f5`, app page `#fafafa`, cards white,
  border `#e2e8f0`, ink `#0f172a`, body `#334155`, muted `#64748b`, subtle `#94a3b8`.
- **Layouts**: the operator console and the hospital view follow the "control" dashboard
  (node 75:7915: sidebar, KPI ribbon, bento cards); the responder PWA follows the "app"
  screens (node 75:7914: avatar header, hero mission cards, glass pill tab bar Home ·
  Progress · Triage · Profile, mission card, progress stepper, Incidents Map card).
- **Type**: DM Sans (Latin) with Noto Sans Arabic as the Arabic fallback, both self-hosted
  through Fontsource (OFL). Arabic uses no negative letter spacing.
- **Shape and shadow**: radii 6 (chips), 8, 12 (buttons, inputs), 14, 16 px (cards);
  `shadow-card` = `0 6px 20px rgb(112 144 176 / 12%)`, `shadow-soft` = Figma "drop shadow".
- **Map**: the offline protomaps basemap restyled to the Figma map (`src/map/style.ts`: land
  `#f0f0f0`, white roads, parks `#b4e7c7`, water `#85d5eb`), the Figma pin and unit markers
  (`src/map/assets/`), `#13a9ff` routes, the camera chip and hospital card overlays, and white
  zoom / recenter controls. No online tile service is used (FR-MAP-001).
- **Icons**: lucide (the Figma icon set is a line icon family of the same style).
- **Logo**: `src/assets/brand/nadjet-logo.svg` (node 75:6347) for `Logo`, and the icon
  `nadjet-mark.svg` (node 75:6348) for `LogoMark`, the favicon and the PWA icons
  (`pwa-192x192.png`, `pwa-512x512.png`, `maskable-512x512.png`, `apple-touch-icon.png`,
  rasterised with resvg). Regenerate them the same way when the logo changes.

### Priority is never colour only (NFR-INT-002)

`PriorityBadge` always shows an icon (different shape per level), `P1…P4` and the level name.
Status and live indicators pair the colour with a word or an icon.

### Contrast of the exact Figma colours (WCAG 2.2 AA: text 4.5:1, large text and UI 3:1)

Computed with the WCAG relative-luminance formula. Pairs below AA are kept because the design
is the source of truth (TD-55); they are listed so they can be raised with the designer.

| Pair | Colours | Ratio | AA |
|---|---|---|---|
| text on page | `#0f172a` on `#f2f4f5` | 16.18:1 | pass |
| body text on card | `#334155` on `#ffffff` | 10.35:1 | pass |
| muted text on card / page | `#64748b` on `#ffffff` / `#f2f4f5` | 4.76:1 / 4.31:1 | pass / large only |
| subtle labels | `#94a3b8` on `#ffffff` | 2.56:1 | fail |
| brand text, KPI figures | `#007dfe` on `#ffffff` | 3.91:1 | large only |
| primary button at rest | `#ffffff` on `#55a8fe` | 2.49:1 | fail |
| gradient button (start / end) | `#ffffff` on `#3568f5` / `#80beff` | 4.72:1 / 1.96:1 | mixed |
| P1 chip, destructive | `#ffffff` on `#ef4444` | 3.76:1 | large only |
| success solid | `#ffffff` on `#16a34a` | 3.30:1 | large only |
| success chip | `#ffffff` on `#4ade80` | 1.74:1 | fail |
| disabled button | `#899cc9` on `#e8ecf3` | 2.31:1 | exempt (disabled) |
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
