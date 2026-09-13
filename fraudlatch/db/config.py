"""Database configuration validation."""

from __future__ import annotations

import os


class DatabaseConfigurationError(ValueError):
    """Raised when the configured database URL is missing or incompatible."""


def get_database_url() -> str:
    """Return an async PostgreSQL URL from the environment."""

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseConfigurationError("DATABASE_URL must be set")
    if not url.startswith("postgresql+asyncpg://"):
        raise DatabaseConfigurationError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
    return url
