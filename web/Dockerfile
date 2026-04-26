# Refreshed 2026-04-27 via:
# docker pull node:22-bookworm-slim && docker inspect --format='{{.RepoDigests}}' node:22-bookworm-slim
FROM node:22-bookworm-slim@sha256:d415caac2f1f77b98caaf9415c5f807e14bc8d7bdea62561ea2fef4fbd08a73c AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-bookworm-slim@sha256:d415caac2f1f77b98caaf9415c5f807e14bc8d7bdea62561ea2fef4fbd08a73c AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-bookworm-slim@sha256:d415caac2f1f77b98caaf9415c5f807e14bc8d7bdea62561ea2fef4fbd08a73c AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

LABEL org.opencontainers.image.source="https://github.com/duytruongdong1808-maker/OPEN-MODEL" \
      org.opencontainers.image.title="open-model-web" \
      org.opencontainers.image.description="Next.js web app for open-model-v1" \
      org.opencontainers.image.licenses="MIT"

# The Next.js standalone server runs `node server.js` directly - npm and npx are
# never invoked at runtime. Their bundled copy of picomatch ships a known ReDoS
# CVE, so strip the entire npm install from the runner image.
RUN rm -rf /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx

RUN groupadd --system --gid 10001 web \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --shell /sbin/nologin web

# Next.js standalone output ships only the production deps required at runtime,
# so dev tools (vite, vitest, esbuild, picomatch, ...) are not baked into the image.
COPY --from=builder --chown=web:web /app/.next/standalone ./
COPY --from=builder --chown=web:web /app/.next/static ./.next/static

USER web

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD node -e "fetch('http://localhost:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
