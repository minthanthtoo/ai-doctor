FROM node:22-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json ./
COPY apps/pwa/package.json apps/pwa/package.json
COPY packages/clinical-kernel/package.json packages/clinical-kernel/package.json
RUN npm ci
COPY apps/pwa apps/pwa
COPY packages/clinical-kernel packages/clinical-kernel
COPY src/ai_doctor/knowledge/v3 src/ai_doctor/knowledge/v3
RUN npm --workspace @ai-doctor/pwa run build

FROM caddy:2.10-alpine
COPY deployment/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /workspace/apps/pwa/dist /srv
EXPOSE 443
