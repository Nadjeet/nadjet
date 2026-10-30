# Vision worker image for the NVIDIA Brev GPU host (linux/amd64). Build from the repository root:
#   docker build -f services/vision/Dockerfile -t nadjet-vision .
# Detection runs here; all VLM calls go to the vLLM server on the same Brev instance (TD-27).
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

# video: lets ffmpeg find libnvidia-encode (NVENC) from the host driver.
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,video \
    DEBIAN_FRONTEND=noninteractive \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
# Workspace manifests first so the dependency layer is cached across source changes.
COPY pyproject.toml uv.lock ./
COPY packages/shared/pyproject.toml packages/shared/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/vision/pyproject.toml services/vision/pyproject.toml
COPY services/camsim/pyproject.toml services/camsim/pyproject.toml
RUN mkdir -p packages/shared/src/nadjet_shared services/api/src/nadjet_api \
        services/vision/src/nadjet_vision services/camsim/src/nadjet_camsim \
    && touch packages/shared/src/nadjet_shared/__init__.py services/api/src/nadjet_api/__init__.py \
        services/vision/src/nadjet_vision/__init__.py services/camsim/src/nadjet_camsim/__init__.py \
    && uv python install 3.12 \
    && uv sync --frozen --no-dev --package nadjet-vision --extra gpu --no-install-workspace

COPY packages/shared packages/shared
COPY services/vision services/vision
COPY data/cameras.yaml data/cameras.yaml
COPY data/zones data/zones
RUN uv sync --frozen --no-dev --package nadjet-vision --extra gpu

ENTRYPOINT ["nadjet-vision"]
CMD ["--help"]
