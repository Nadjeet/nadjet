# syntax=docker/dockerfile:1
# API image: one image, several commands (TD-19). Build from the repository root:
#   docker build -f services/api/Dockerfile -t nadjet-api .
# serve (default) · consume · worker · seed-*; see deploy/vps/compose.yml.
FROM python:3.12-slim-bookworm

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    NADJET_ENV=production

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/shared/pyproject.toml packages/shared/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/vision/pyproject.toml services/vision/pyproject.toml
COPY services/camsim/pyproject.toml services/camsim/pyproject.toml
RUN mkdir -p packages/shared/src/nadjet_shared services/api/src/nadjet_api \
        services/vision/src/nadjet_vision services/camsim/src/nadjet_camsim \
    && touch packages/shared/src/nadjet_shared/__init__.py services/api/src/nadjet_api/__init__.py \
        services/vision/src/nadjet_vision/__init__.py services/camsim/src/nadjet_camsim/__init__.py
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package nadjet-api --package nadjet-camsim --no-install-workspace

COPY packages/shared packages/shared
COPY services/api services/api
COPY services/camsim services/camsim
COPY data data
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package nadjet-api --package nadjet-camsim

RUN useradd --system --uid 10001 --home-dir /app nadjet \
    && mkdir -p /app/evidence && chown nadjet /app/evidence
USER nadjet
WORKDIR /app/services/api

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD curl -fs http://127.0.0.1:8000/health || exit 1
ENTRYPOINT ["nadjet-api"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
