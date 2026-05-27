# syntax=docker/dockerfile:1

ARG NODE_VERSION=26.1.0
ARG NGINX_VERSION=1.27

FROM node:${NODE_VERSION}-slim AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . ./
RUN npm run build

FROM nginx:${NGINX_VERSION}-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
