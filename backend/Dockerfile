# DEEPTERMINAL API. Build from the repository root:  docker build -f backend/Dockerfile .
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
# The Playwright driver needs libatomic before it can install browser dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY deepterminal ./deepterminal
RUN pip install --no-cache-dir .
COPY backend/pyproject.toml ./backend/
COPY backend/deepterminal_api ./backend/deepterminal_api
COPY backend/alembic ./backend/alembic
COPY backend/alembic.ini ./backend/
COPY scripts/seed_demo.py ./scripts/seed_demo.py
# PDF export uses Playwright's Chromium (optional; ~400 MB). Set INSTALL_PDF=0 to skip.
ARG INSTALL_PDF=1
# Paid AI SDKs are not installed by default (zero-cost); local AI uses Ollama over plain HTTP.
ARG INSTALL_PAID_SDKS=0
RUN pip install --no-cache-dir "./backend" \
 && if [ "$INSTALL_PAID_SDKS" = "1" ]; then pip install --no-cache-dir "./backend[llm]"; fi \
 && if [ "$INSTALL_PDF" = "1" ]; then pip install --no-cache-dir "./backend[pdf]" && playwright install --with-deps chromium; fi
RUN useradd --create-home app && mkdir -p /app/backend/.cache && chown -R app /app/backend/.cache
USER app
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn deepterminal_api.main:app --host 0.0.0.0 --port 8000"]
