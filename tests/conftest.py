from __future__ import annotations

import os

import pytest

os.environ.setdefault("OPEN_MODEL_SKIP_MODEL_LOAD", "true")


@pytest.fixture(scope="session")
def postgres_container():
    configured_url = os.getenv("OPEN_MODEL_DATABASE_URL")
    if configured_url:
        yield configured_url
        return
    if os.getenv("OPEN_MODEL_USE_TESTCONTAINERS") != "1":
        pytest.skip("Set OPEN_MODEL_DATABASE_URL or OPEN_MODEL_USE_TESTCONTAINERS=1.")

    try:
        from testcontainers.postgres import PostgresContainer
    except Exception as exc:
        pytest.skip(f"testcontainers-postgres is unavailable: {exc}")

    try:
        with PostgresContainer("postgres:16.4-alpine") as postgres:
            yield postgres.get_connection_url().replace("postgresql://", "postgresql+psycopg://", 1)
    except Exception as exc:
        pytest.skip(f"Postgres container is unavailable: {exc}")
