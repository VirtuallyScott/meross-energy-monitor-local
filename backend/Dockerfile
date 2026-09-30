# syntax=docker/dockerfile:1.7
# Energy Hub backend image: api, collector, worker, migrate, sim (ARC-001).
#
# Stages:
#   builder  - resolves locked dependencies into /opt/venv and installs the app as a wheel
#   test     - adds dev tools and runs lint, type checks and tests (docker build --target test)
#   runtime  - slim, non-root image with only the virtualenv (default target)

ARG PYTHON_VERSION=3.13

# ---------------------------------------------------------------- builder
FROM python:${PYTHON_VERSION}-slim AS builder
# uv comes from PyPI (pinned) so the build needs no extra registry.
ARG UV_VERSION=0.12.21
RUN --mount=type=cache,target=/root/.cache/pip pip install "uv==${UV_VERSION}"
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src

# Dependencies first, so source edits do not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY app ./app
# --reinstall-package: the version does not change between source edits, so without it uv
# would keep the previously built wheel and ship stale code.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --reinstall-package energy-hub

# ------------------------------------------------------------------- test
FROM builder AS test
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra dev --no-editable --reinstall-package energy-hub
COPY tests ./tests
ENV PATH=/opt/venv/bin:$PATH \
    EHUB_DB_PASSWORD=test
RUN ruff check app tests \
 && ruff format --check app tests \
 && mypy app \
 && pytest -q --cov=app --cov-report=term-missing:skip-covered

# ---------------------------------------------------------------- runtime
FROM python:${PYTHON_VERSION}-slim AS runtime
ARG APP_VERSION=0.1.0
LABEL org.opencontainers.image.title="energy-hub-backend" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.description="Local hub for Meross / Refoss EM16P energy monitors"

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder --chown=root:root /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /tmp
USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["energy-hub", "healthcheck"]

ENTRYPOINT ["energy-hub"]
CMD ["api"]
