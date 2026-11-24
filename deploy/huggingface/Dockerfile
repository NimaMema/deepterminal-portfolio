# DEEPTERMINAL public demo: one container (PostgreSQL + FastAPI + Next.js) for a free
# Hugging Face Docker Space. Serves a recorded SEC EDGAR snapshot read-only, with no network
# access and no paid APIs. Assembled by .github/workflows/deploy-demo.yml.
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1 DEEPTERMINAL_BACKEND_URL=http://127.0.0.1:8000
RUN npm run build && npm prune --omit=dev

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers NEXT_TELEMETRY_DISABLED=1
# The recorded snapshot was created by PostgreSQL 16 (archive format 1.15).
# Debian bookworm's default PostgreSQL 15 cannot restore that archive.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg libatomic1 \
 && install -d -m 0755 /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update && apt-get install -y --no-install-recommends postgresql-16 postgresql-client-16 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY pyproject.toml README.md ./
COPY deepterminal ./deepterminal
COPY backend ./backend
RUN pip install --no-cache-dir . && pip install --no-cache-dir "./backend[pdf]" \
 && playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
COPY --from=web /web/package.json /web/next.config.mjs ./frontend/
COPY --from=web /web/node_modules ./frontend/node_modules
COPY --from=web /web/.next ./frontend/.next
COPY snapshot ./snapshot
RUN mkdir -p backend/.cache && tar -xzf snapshot/cache.tar.gz -C backend/.cache && rm snapshot/cache.tar.gz
COPY start.sh warm.py ./
# Hugging Face runs Spaces as uid 1000.
RUN useradd -m -u 1000 user && chmod +x start.sh && chown -R user /app/backend/.cache
USER user
ENV DEEPTERMINAL_PUBLIC_DEMO=true \
    DEEPTERMINAL_DATA_MODE=live \
    DEEPTERMINAL_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/deepterminal \
    DEEPTERMINAL_DEMO_SHOWCASE_PATH=/app/snapshot/showcase.json \
    DEEPTERMINAL_DEMO_RESPONSES_PATH=/app/snapshot/responses.json.gz \
    DEEPTERMINAL_RATE_LIMIT_PER_MINUTE=180 \
    DEEPTERMINAL_PROXY_HOPS=2 \
    DEEPTERMINAL_CORS_ORIGINS="" \
    DEEPTERMINAL_LOG_LEVEL=WARNING
EXPOSE 7860
CMD ["./start.sh"]
