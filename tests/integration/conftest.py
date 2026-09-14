"""Disposable service fixtures for integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer


@pytest.fixture(scope="session", autouse=True)
def disposable_services() -> Iterator[None]:
    """Start isolated PostgreSQL/Redis containers and run migrations once."""

    with PostgresContainer("postgres:16") as postgres, RedisContainer("redis:7") as redis:
        database_url = (
            f"postgresql+asyncpg://test:test@{postgres.get_container_host_ip()}"
            f":{postgres.get_exposed_port(5432)}/test"
        )
        redis_url = f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"
        environment = os.environ.copy()
        environment.update({"DATABASE_URL": database_url, "REDIS_URL": redis_url})
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            cwd=Path(__file__).parents[2],
            env=environment,
        )
        old_database = os.environ.get("DATABASE_URL")
        old_redis = os.environ.get("REDIS_URL")
        os.environ.update({"DATABASE_URL": database_url, "REDIS_URL": redis_url})
        try:
            yield
        finally:
            if old_database is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old_database
            if old_redis is None:
                os.environ.pop("REDIS_URL", None)
            else:
                os.environ["REDIS_URL"] = old_redis
