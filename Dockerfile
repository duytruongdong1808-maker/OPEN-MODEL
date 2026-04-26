FROM python:3.11-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src ./src
COPY alembic ./alembic
COPY configs ./configs
COPY data ./data
COPY scripts ./scripts
COPY alembic.ini ./
COPY pyproject.toml README.md ./

RUN mkdir -p outputs/app

EXPOSE 8000

CMD ["uvicorn", "src.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
