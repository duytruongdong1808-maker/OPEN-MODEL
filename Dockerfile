# syntax=docker/dockerfile:1.7
# Refreshed 2026-04-27 via:
# docker pull python:3.11-slim-bookworm && docker inspect --format='{{.RepoDigests}}' python:3.11-slim-bookworm
FROM python:3.11-slim-bookworm@sha256:ee710afcfb733f4a750d9be683cf054b5cd247b6c5f5237a6849ea568b90ab15 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip "setuptools>=78" "wheel>=0.46.2"

COPY requirements.txt .
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

FROM python:3.11-slim-bookworm@sha256:ee710afcfb733f4a750d9be683cf054b5cd247b6c5f5237a6849ea568b90ab15 AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

LABEL org.opencontainers.image.source="https://github.com/duytruongdong1808-maker/OPEN-MODEL" \
      org.opencontainers.image.title="open-model-backend" \
      org.opencontainers.image.description="FastAPI backend for open-model-v1" \
      org.opencontainers.image.licenses="MIT"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --shell /sbin/nologin app

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels requirements.txt

COPY --chown=app:app src ./src
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app configs ./configs
COPY --chown=app:app scripts ./scripts

RUN install -d -o app -g app /app/outputs/app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "src.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
