# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A supervised fine-tuning pipeline for small open-weight LLMs (defaulting to `Qwen/Qwen2.5-3B-Instruct`) combined with a full-stack web app for chat and mail triage. The repo has three main layers: a Python data/training pipeline (`src/`), a FastAPI backend with async DB and streaming inference (`src/server/`), and a Next.js frontend (`web/`).

## Commands

### Backend
```bash
pip install -r requirements-dev.txt
pytest -q                                    # all Python tests
pytest -q --cov=src --cov-fail-under=70     # match CI coverage gate
pytest tests/test_api.py::test_name -v      # single test
OPEN_MODEL_SKIP_MODEL_LOAD=true pytest -q   # skip heavy model loads
pytest -q -m postgres                        # requires OPEN_MODEL_DATABASE_URL
ruff check . && ruff format --check . && black --check .
alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn src.server.app:app --reload
```

### Frontend
```bash
cd web && npm ci
cd web && npm run dev
cd web && npm test         # Vitest unit tests
cd web && npm run e2e      # Playwright (run npm run e2e:install first if needed)
cd web && npm run build
```

### Full stack
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### Training workflow
```bash
python src/download_sample_data.py
python src/curate_data.py
python src/build_dataset.py
python src/prepare_data.py
python src/train_lora.py --config configs/rtx4060ti_8gb.yaml
python src/merge_adapter.py
python src/eval.py --eval_path data/eval/mail_triage_gold.jsonl
python src/chat.py   # terminal REPL
```

## Architecture

### Data pipeline (`src/`)
Linear stages: raw JSONL → `curate_data.py` (adds `task_type`, `language`, `quality_score`, `flags`, `source`, `action`) → `build_dataset.py` (balances multilingual datasets) → `prepare_data.py` (tokenizes to SFT format with `prompt`/`completion` fields).

### Model training (`src/train_lora.py`, `src/merge_adapter.py`)
LoRA/QLoRA via `peft` + `trl`, with `bitsandbytes` for 4-bit quantization. Config presets in `configs/` (RTX 4060 Ti 8 GB, A100 40 GB). Outputs checkpoints and a final adapter that can be merged back into the base model.

### FastAPI backend (`src/server/`)
- **Inference** — `src/server/inference/local.py` (in-process transformers) and `vllm.py` (OpenAI-compatible GPU server)
- **Agent loop** — `src/agent/loop.py` drives agentic tool use; schemas in `src/agent/`
- **Email tools** — `src/tools/`: Gmail OAuth, async IMAP (`aioimaplib`), async SMTP (`aiosmtplib`), send ledger
- **Database** — SQLAlchemy async (SQLite dev / PostgreSQL prod); tables: conversations, messages, message_sources, gmail_credentials, audit_log, send_ledger; migrations in `alembic/`
- **Observability** — Prometheus metrics, OpenTelemetry tracing, Sentry; dashboards in `observability/`

### Next.js frontend (`web/`)
- App router; domain features under `web/features/chat` and `web/features/mail`
- Auth via NextAuth (username/password + Google OAuth)
- Rate limiting: Redis-backed with in-memory fallback
- Unit tests (Vitest) live beside source; E2E tests in `web/e2e/`

## Testing notes

- Use `OPEN_MODEL_SKIP_MODEL_LOAD=true` for tests that don't need the model loaded — required for CI speed
- Mark tests needing a real Postgres instance with `@pytest.mark.postgres`; mark external-service tests with `@pytest.mark.integration`
- Backend CI gate is 70% coverage (`--cov-fail-under=70`)

## Code style

- Python 3.11, Black + Ruff, 100-char line length (`pyproject.toml`), snake_case modules/functions/variables, PascalCase classes
- TypeScript/React, PascalCase components (e.g. `ChatShell.tsx`), domain code under `web/features/<domain>`
- Do not commit real secrets or `.env` values — use `.env.example` and `secrets/*.example`; pre-commit and CI run Gitleaks
