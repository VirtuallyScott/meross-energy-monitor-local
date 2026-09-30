# syntax=docker/dockerfile:1.7
# Energy Hub web UI: static SPA served by unprivileged nginx.
#
# Stages:
#   deps     - npm ci from the lockfile
#   test     - lint, format check, type check and unit tests (docker build --target test)
#   build    - production bundle
#   runtime  - nginx serving /usr/share/nginx/html on port 8080 (default target)

ARG NODE_VERSION=24
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.29-alpine

FROM node:${NODE_VERSION}-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

FROM deps AS test
COPY . .
RUN npx eslint src \
 && npx prettier --check src \
 && npx tsc --noEmit \
 && npx vitest run

FROM deps AS build
COPY . .
RUN npx vite build

FROM ${NGINX_IMAGE} AS runtime
ARG APP_VERSION=0.1.0
LABEL org.opencontainers.image.title="energy-hub-web" \
      org.opencontainers.image.version="${APP_VERSION}"
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
