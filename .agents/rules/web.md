---
paths:
  - "apps/web/**"
  - "packages/api-client/**"
---

# Web app and TypeScript client

- **Do not create frontend tests of any kind** (no Vitest/Jest/Playwright/Cypress, no
  `*.test.*` / `*.spec.*`). CI rejects them. Validate with `make lint`, `make typecheck`
  and `pnpm --filter @nadjet/web build`.
- Call the backend only via `@nadjet/api-client` (generated). Never edit
  `packages/api-client/src/schema.d.ts` by hand: change the API, then `make gen`.
- UI: React 19 function components, Tailwind, shadcn/ui components when added
  (`pnpm dlx shadcn@latest add …` from `apps/web`). Arabic (RTL), French and English;
  WCAG 2.2 AA contrast; priority never shown by colour alone (PRD NFR-INT-001/002).
- Show the source of every AI value (rule or model id) and label simulated data.
