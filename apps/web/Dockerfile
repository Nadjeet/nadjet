# syntax=docker/dockerfile:1
# Web image: static build served by nginx; /api is proxied to the API (same origin, no CORS).
#   docker build -f apps/web/Dockerfile -t nadjet-web .
FROM node:24-slim AS build
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
RUN --mount=type=cache,target=/pnpm/store pnpm install --frozen-lockfile
COPY packages/api-client packages/api-client
COPY apps/web apps/web
ARG VITE_SMS_GATEWAY_NUMBER=""
ENV VITE_SMS_GATEWAY_NUMBER=$VITE_SMS_GATEWAY_NUMBER
RUN pnpm --filter ./apps/web build

FROM nginx:1.29-alpine
COPY apps/web/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
ENV NADJET_API_UPSTREAM=http://api:8000
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
