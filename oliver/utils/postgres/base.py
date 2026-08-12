# Path: utils/postgres/base.py
# Description: Database client for Azure SQL.

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import get_settings

# Get the settings
settings = get_settings()

# Create the engine
engine = create_engine(
    settings.DATABASE_URL.get_secret_value(),
    pool_size=5,  # 5 permanent connections per worker
    max_overflow=195,  # 195 overflow connections per worker
    pool_pre_ping=True,  # Drop stale connections before use
    pool_timeout=0,  # Raise immediately if no connection is available
)

# Create the session factory
SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create the base class
DatabaseBase = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Get Database Session."""
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()
