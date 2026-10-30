# Deployment runbook (VPS + Dokploy, GPU workers on Brev)

Covers PRD FR-SEC-007, NFR-SEC-001, NFR-FLEX-001; decisions TD-17, TD-18, TD-19, TD-40 (docs/11).
Topology: `docs/10-live-deployment-and-models.md` §2. Everything here is free-tier (PRD C-01).

Names used below: `$DOMAIN` = the team's domain (Q-01, confirm with the team), `$VPS_IP` = VPS public IP.

## 1. Prerequisites

- VPS ≥ 4 vCPU, 8 GB RAM, 60 GB disk, Ubuntu 24.04, public IPv4.
- DNS **A records** → `$VPS_IP`: `app.`, `respond.`, `hospital.`, `try.`, `api.`, `stream.`, `hls.`, `sms.` (`$DOMAIN`).
  `stream.` must be **DNS only**; if the DNS host is Cloudflare, switch the proxy (orange cloud) off for it
  (WebRTC/RTSP are not HTTP, TD-17).
- Firewall (ufw or provider panel): allow `22/tcp`, `80/tcp`, `443/tcp`, `443/udp`, `3000/tcp` (Dokploy, first
  setup only), **`8554/tcp`** (RTSP), **`8189/udp` and `8189/tcp`** (WebRTC media). Nothing else.
- GHCR images `ghcr.io/nadjeet/nadjet-{api,web,vision}` exist for the tag you deploy (CI, §7). If the packages
  are private, add a registry in Dokploy (Settings → Registry) with a read-only token.

## 2. First deploy

1. Install Dokploy: `curl -sSL https://dokploy.com/install.sh | sh`, open `http://$VPS_IP:3000`, create the admin.
2. Dokploy → Project `nadjet` → **Create Service → Compose**. Source: Git, repo `Nadjeet/nadjet`, branch `main`,
   compose path `deploy/vps/compose.yml`, **Compose Type: Docker Compose** (not Stack).
3. Environment tab: paste `deploy/vps/.env.example` and fill every value (generate secrets with
   `openssl rand -hex 32`; `NADJET_SIGNING_KEY` with `docker run --rm ghcr.io/nadjeet/nadjet-api:demo-v1 gen-signing-key`).
   Set `NADJET_TAG=demo-v1`. Never commit these values.
4. Domains tab (Dokploy injects the Traefik labels and Let's Encrypt, HTTPS on):

   | Host | Service | Port |
   |---|---|---|
   | `app.`, `respond.`, `hospital.`, `try.` `$DOMAIN` | `web` | 80 |
   | `api.$DOMAIN` | `api` | 8000 |
   | `stream.$DOMAIN` | `mediamtx` | 8889 (WHEP/WHIP) |
   | `hls.$DOMAIN` | `mediamtx` | 8888 (LL-HLS fallback) |
   | `sms.$DOMAIN` | `sms-server` | 3000 |
5. Seed data once (§3), then **Deploy**. Redeploy after every Domains change (Dokploy rewrites the labels).

## 3. One-time data

Copy into the named volumes (volume names are prefixed with the compose project, check `docker volume ls`):

```bash
# OSRM graph, pre-built on a laptop: make routing-data (docs/ONBOARDING.md), then
docker run --rm -v nadjet-core_osrmdata:/d -v "$PWD/data/map-osrm":/src alpine cp -r /src/. /d/
# Offline basemap and demo clips (held-out list only, AGENTS.md integrity rules)
docker run --rm -v nadjet-core_mapdata:/d -v "$PWD/data/map":/src alpine cp /src/algeria.pmtiles /d/
docker run --rm -v nadjet-core_videos:/d -v "$PWD/data/videos":/src alpine cp -r /src/. /d/
```

Then create the first admin and seed the registry from the API container:

```bash
docker compose -p nadjet-core exec api nadjet-api seed-cameras
docker compose -p nadjet-core exec api nadjet-api seed-geo
# users: copy a users.yaml (not in git, see data/seed/users.example.yaml) into the container, then
docker compose -p nadjet-core exec api nadjet-api seed-users data/seed/users.yaml
```

Restart `mediamtx-config` and `mediamtx` after adding videos: `docker compose -p nadjet-core up -d --force-recreate mediamtx-config mediamtx`.

## 4. Stream security (FR-SEC-007)

MediaMTX runs with `authMethod: http`; every publish/read/API request is checked by the API
(`POST /internal/mediamtx-auth`):

| Caller | How it authenticates | Allowed |
|---|---|---|
| camsim publishers (inside MediaMTX), Brev workers | user `NADJET_STREAM_SERVICE_USER`, password `NADJET_INGEST_TOKEN` | publish, read, control API |
| Console user (operator, supervisor, admin) | Bearer stream token from `POST /auth/stream-token` (5 min, renewed by the player) | read |
| Try-it phone (WHIP) | publish token limited to its own path, minted by the try-it session | publish that path only |
| Anyone else | — | rejected (401) |

Check from outside the VPS (must fail, then succeed):

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://stream.$DOMAIN/cam-a1-pk42/whep \
  -H 'Content-Type: application/sdp' -d 'v=0'                       # expect 401
ffprobe -rtsp_transport tcp rtsp://stream.$DOMAIN:8554/cam-a1-pk42   # expect 401 Unauthorized
ffprobe -rtsp_transport tcp "rtsp://nadjet-worker:$NADJET_INGEST_TOKEN@stream.$DOMAIN:8554/cam-a1-pk42"  # streams
```

## 5. Brev workers (outbound only, TD-18)

On the Brev instance nothing listens publicly (vLLM stays on loopback; open no ports in the Brev panel).
Start the workers with production endpoints (instance start/stop and credits need explicit team approval):

```bash
cd nadjet/deploy/gpu
export NADJET_VISION_IMAGE=ghcr.io/nadjeet/nadjet-vision:demo-v1
export NADJET_RTSP_BASE="rtsp://nadjet-worker:${NADJET_INGEST_TOKEN}@stream.${DOMAIN}:8554"
export NADJET_API_URL="https://api.${DOMAIN}"
export NADJET_INGEST_TOKEN=...   # same value as on the VPS
docker compose --profile workers up -d
```

Workers pull RTSP from `stream.$DOMAIN:8554`, push `<cam>_ai` back to it, and POST candidates and health to
`https://api.$DOMAIN/internal/*` with the ingest token. Verify: `/system/cameras` in the console shows FPS and the
annotated stream plays. Never paste the token into chat or logs.

## 6. Operations

- **Backups (free).** Dokploy → the compose service → *Volume Backups*: add `nadjet-core_pgdata`, destination =
  any S3-compatible free tier (e.g. Cloudflare R2 or Backblaze B2 free quota) or *Local*; daily schedule, keep 7.
  Also `evidence` weekly. Fallback with no destination:
  `docker compose -p nadjet-core exec -T db pg_dump -U nadjet nadjet | gzip > nadjet-$(date +%F).sql.gz`.
  Restore: `gunzip -c file.sql.gz | docker compose -p nadjet-core exec -T db psql -U nadjet nadjet`.
- **Uptime.** UptimeRobot free plan (no card): HTTPS monitor on `https://api.$DOMAIN/health` (5 min) and one on
  `https://app.$DOMAIN/healthz`. `/ready` reports Redis and PostGIS.
- **Logs.** Dokploy → service → Logs; Traefik errors under the `dokploy-traefik` container.

## 7. Update, rollback, secrets

- **Release.** Merge to `main`, then `git tag demo-v2 && git push origin demo-v2`. CI (`app-images` job) builds and
  pushes `ghcr.io/nadjeet/nadjet-{api,web}:demo-v2` (and vision). Check `gh run watch` is green.
- **Update.** Dokploy Environment: `NADJET_TAG=demo-v2` → **Deploy**. `migrate` runs `alembic upgrade head` first;
  `api` starts only after it succeeds.
- **Rollback.** Set `NADJET_TAG` back to the previous tag (e.g. `demo-v1`) → **Deploy**. Migrations are
  forward-only on stage: before deploying a release that changes the schema, take a `pg_dump` (§6) and restore it
  if the old tag cannot run on the new schema.
- **Secrets rotation.** Change the value in Dokploy Environment and redeploy.
  `NADJET_INGEST_TOKEN` → also update the Brev workers (§5) and restart them. `NADJET_JWT_SECRET` signs out
  every user and invalidates stream tokens. `NADJET_DB_PASSWORD` must also be changed in Postgres:
  `ALTER USER nadjet PASSWORD '...'`, then redeploy.

## 8. Troubleshooting

| Symptom | Check |
|---|---|
| Certificate not issued | DNS A record points to `$VPS_IP`; ports 80/443 open; Domains tab saved and redeployed |
| Console video black, WHEP 401 | `/auth/stream-token` returns 403 for non-console roles; check the user's role; clock skew on VPS |
| WebRTC connects but no video | 8189/udp **and** tcp open; `NADJET_PUBLIC_HOST` is the public IP; `stream.` not proxied |
| Workers cannot publish `_ai` | wrong `NADJET_INGEST_TOKEN` / user in `NADJET_RTSP_BASE`; MediaMTX logs show `authentication failed` |
| `api` never healthy | `docker compose -p nadjet-core logs migrate api` (missing secret → production settings validation error) |
