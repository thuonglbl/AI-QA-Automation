# syntax=docker/dockerfile:1

ARG NODE_VERSION=26.4.0
ARG NGINX_VERSION=1.31.2

FROM node:${NODE_VERSION}-slim AS builder

# The version badge (AppVersion.tsx) reads DOCKER_IMAGE_VERSION at build time via
# vite.config.ts. The build context is ./frontend, so ../.env is NOT available
# here — the version must be injected as a build arg, otherwise vite falls back
# to package.json (0.1.0). Pass it with: --build-arg DOCKER_IMAGE_VERSION=<ver>.
ARG DOCKER_IMAGE_VERSION
ENV DOCKER_IMAGE_VERSION=${DOCKER_IMAGE_VERSION}

WORKDIR /app

COPY package*.json ./
RUN npm ci --legacy-peer-deps

COPY . ./
RUN npm run build

FROM nginx:${NGINX_VERSION}-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
