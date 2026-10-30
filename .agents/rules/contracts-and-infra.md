---
paths:
  - "contracts/**"
  - "deploy/**"
  - "data/**"
  - "Makefile"
  - ".github/**"
---

# Contracts, infrastructure and CI

- `contracts/` is generated (`make gen`); never edit it by hand. CI runs `make check-contracts`.
- `deploy/local/compose.yml` must stay runnable on macOS (arm64) and Linux (amd64): use
  multi-arch images with pinned tags and healthchecks; keep host ports off common defaults.
- `deploy/gpu/compose.yml` runs on the Brev instance only; keep vLLM bound to loopback.
- Never commit media, model weights, `.env` or generated MediaMTX config.
- Makefile targets must keep working with GNU make 3.81 and stay documented with `## help`.
- CI must not call Brev or any AI provider and must not run frontend tests.
