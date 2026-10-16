# syntax=docker/dockerfile:1.7
# Build giao diện tĩnh rồi phục vụ bằng Caddy (Caddyfile mount từ deploy/Caddyfile).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
