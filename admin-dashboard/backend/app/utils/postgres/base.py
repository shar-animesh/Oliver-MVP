"""Read-only SQLAlchemy connection used by the admin backend."""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL.get_secret_value(),
    pool_pre_ping=True,
)

SessionFactory = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Provide one SQLAlchemy session for a read-only API request."""
    database = SessionFactory()
    try:
        yield database
    finally:
        database.close()
