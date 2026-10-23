FROM node:24.19.0-bookworm-slim AS build
WORKDIR /app
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN npm install --global npm@11.17.0 --registry=${NPM_REGISTRY}
COPY apps/web/package.json apps/web/package-lock.json apps/web/.npmrc ./
RUN npm ci --registry=${NPM_REGISTRY} --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM caddy:2.11.7-alpine
COPY infra/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 80
