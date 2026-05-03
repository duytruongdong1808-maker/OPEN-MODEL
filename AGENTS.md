# Repository Guidelines

## Project Structure & Module Organization

This repository combines Python model tooling, a FastAPI backend, and a Next.js frontend. `src/` contains data preparation, LoRA training, evaluation, agent logic, tools, and backend services. `tests/` contains the pytest suite. `web/` contains routes in `web/app`, features in `web/features`, helpers in `web/lib`, unit tests beside source, and Playwright specs in `web/e2e`. `data/` holds raw, curated, and eval JSONL datasets; avoid committing large generated outputs. `configs/` stores training configs, `alembic/` stores migrations, and `docs/`, `observability/`, `scripts/`, and `secrets/*.example` support operations.

## Build, Test, and Development Commands

- `pip install -r requirements-dev.txt`: install Python dev dependencies.
- `pytest -q`: run Python tests.
- `pytest -q --cov=src --cov-fail-under=70`: match backend CI coverage gate.
- `ruff check .`, `ruff format --check .`, `black --check .`: verify Python style.
- `alembic upgrade head`: apply and validate database migrations.
- `.\.venv\Scripts\python.exe -m uvicorn src.server.app:app --reload`: run the backend locally.
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`: start the local stack.
- `cd web && npm ci`: install frontend dependencies from lockfile.
- `cd web && npm run dev`: run Next.js locally.
- `cd web && npm test`, `npm run e2e`, `npm run build`: run Vitest, Playwright, and build.

## Coding Style & Naming Conventions

Use Python 3.11, 4-space indentation, Black, and Ruff. `pyproject.toml` sets line length to 100. Prefer typed, small modules with snake_case files, functions, and variables; classes use PascalCase.

Frontend code uses TypeScript, React, and Next.js conventions. Components use PascalCase, for example `ChatShell.tsx`; tests use `*.test.ts` or `*.test.tsx`; domain code belongs under `web/features/<domain>`.

## Testing Guidelines

Place Python tests under `tests/` as `test_*.py`. Use declared markers such as `integration` and `postgres` for tests requiring services or credentials. Keep model-heavy tests compatible with `OPEN_MODEL_SKIP_MODEL_LOAD=true` when possible.

Frontend unit tests run with Vitest and live beside source. End-to-end tests live in `web/e2e`; install browsers with `npm run e2e:install` when needed.

## Commit & Pull Request Guidelines

Recent history uses short, imperative subjects, for example `Avoid extra mail navigation in e2e login` and `Prevent model loading during backend tests`. Keep commits focused and behavior-oriented.

Pull requests should include a clear summary, test commands run, linked issues when applicable, migration or environment notes, and screenshots for visible UI changes.

## Security & Configuration Tips

Do not commit real secrets or `.env` values. Use `.env.example` and `secrets/*.example` as templates. Pre-commit and CI run Gitleaks; rotate exposed tokens immediately.
