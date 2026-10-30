# Nadjet web app

React 19 + Vite + Tailwind 4. One app, four surfaces (PRD §13):

| Path | Surface | Roles | Theme |
|---|---|---|---|
| `/ops/*` | Operator console | operator, supervisor, auditor, admin | dark |
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

Source: the Nadjet Figma file (Colors, Typography, Effects, Buttons, Inputs, Cards, Modals,
Dropdowns, icons). The Figma components use a purple primary (`#4318FF`); Nadjet replaces it
with the brand blue. Tokens live in `src/index.css`; `/ops/design` renders every component.

- **Brand blue** `brand-100…900`: `#aad4ff #80beff #55a8fe #2a93fe #007dfe #0053a9 #003f7f #002a55 #00152a`.
- **Primary** (buttons, active state): `brand-600` `#0053a9` in light, `brand-400` `#2a93fe` in
  dark. `brand-500` `#007dfe` is the Figma primary, but white on it is only 3.9:1, so it is
  used for the focus ring and large accents, not for filled buttons with text.
- **Surface** `#f4f7fe` (Figma Secondary/Grey 300), cards white, ink `brand-900`.
- **Type**: DM Sans (Latin) with Noto Sans Arabic as the Arabic fallback, both self-hosted
  through Fontsource (OFL). Sizes follow the Figma scale (`text-display-xl…xs`,
  `text-body-xl…xs`). Arabic uses no negative letter spacing.
- **Shape and shadow**: pill buttons, 16 px inputs, 20 px cards, 24 px dialogs,
  `shadow-soft` = `0 6px 40px rgb(112 144 176 / 12%)`.
- **Icons**: lucide (the Figma icon set is a line icon family of the same style).
- **Logo**: placeholder mark in `public/logo-mark.svg` (a map pin with a medical cross and a
  signal ripple on the brand gradient). The PNG icons (`pwa-192x192.png`, `pwa-512x512.png`,
  `maskable-512x512.png`, `apple-touch-icon.png`) were rasterised from `logo-mark.svg` and
  `logo-mark-maskable.svg`; regenerate them the same way when the logo changes.

### Priority is never colour only (NFR-INT-002)

`PriorityBadge` always shows an icon (different shape per level), `P1…P4` and the level name.
Status and live indicators follow the same rule.

### Contrast (WCAG 2.2 AA: text 4.5:1, UI 3:1)

Computed with the WCAG relative-luminance formula.

| Theme | Pair | Colours | Ratio |
|---|---|---|---|
| Light | text on page | `#00152a` on `#f4f7fe` | 17.17:1 |
| Light | text on card | `#00152a` on `#ffffff` | 18.41:1 |
| Light | muted text on card | `#51627f` on `#ffffff` | 6.17:1 |
| Light | muted text, placeholder on input | `#51627f` on `#eaf0fc` | 5.40:1 |
| Light | primary button text | `#ffffff` on `#0053a9` | 7.47:1 |
| Light | outline and text button | `#0053a9` on `#f4f7fe` | 6.97:1 |
| Light | subtle button text | `#003f7f` on `#dfeaff` | 8.60:1 |
| Light | P1 badge | `#ffffff` on `#b91c1c` | 6.47:1 |
| Light | P2 badge | `#ffffff` on `#c2410c` | 5.18:1 |
| Light | P3 badge | `#ffffff` on `#92400e` | 7.09:1 |
| Light | P4 badge | `#ffffff` on `#475569` | 7.58:1 |
| Light | success | `#ffffff` on `#15803d` | 5.02:1 |
| Light | error, destructive | `#ffffff` on `#dc2626` | 4.83:1 |
| Light | focus ring (UI, 3:1) | `#007dfe` on `#ffffff` | 3.91:1 |
| Dark | text on page | `#f4f7fe` on `#00152a` | 17.17:1 |
| Dark | text on card | `#f4f7fe` on `#002040` | 15.29:1 |
| Dark | muted text on page | `#9fb0cc` on `#00152a` | 8.38:1 |
| Dark | muted text, placeholder on input | `#9fb0cc` on `#002a55` | 6.53:1 |
| Dark | primary button text | `#00152a` on `#2a93fe` | 5.88:1 |
| Dark | outline and text button on card | `#2a93fe` on `#002040` | 5.23:1 |
| Dark | success text on card | `#34d399` on `#002040` | 8.53:1 |
| Dark | error text on card | `#f87171` on `#002040` | 5.93:1 |
| Dark | focus ring (UI, 3:1) | `#55a8fe` on `#002040` | 6.57:1 |

Disabled controls are exempt from the contrast rule.

## PWA

`vite-plugin-pwa` generates the manifest and a service worker that precaches the app shell
(`/api` and the live stream are never cached). One manifest covers `/respond` and `/public`
(`start_url: /` redirects by role or to login). Check installability in Chrome DevTools >
Application > Manifest and Service workers, using `pnpm --filter @nadjet/web build` then
`pnpm --filter @nadjet/web preview`. Offline queues belong to the responder and citizen issues.
