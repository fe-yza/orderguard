"""Database engine/session setup. Connection string comes from an env var,
never hardcoded, per `docs/architecture.md`'s config-via-env-vars rule.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from orderguard.persistence.models import Base


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORDERGUARD_")

    database_url: str = "postgresql+psycopg://localhost:5432/orderguard_dev"


@lru_cache
def get_engine() -> Engine:
    return create_engine(DatabaseSettings().database_url)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine())


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, always closed after the request."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def create_all_tables() -> None:
    """Dev/test convenience — creates tables directly from the ORM models
    without going through Alembic. Real deployments use the Alembic
    migration in `alembic/versions/`; this exists so tests don't need a
    migration runner to stand up a throwaway schema."""
    Base.metadata.create_all(get_engine())


def drop_all_tables() -> None:
    Base.metadata.drop_all(get_engine())
