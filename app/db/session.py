"""Database session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Create engine with connection pool limits
engine = create_engine(
    str(settings.postgres_url),
    echo=False,  # Set to True for SQL debugging
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=2,  # Limit to 2 connections per process
    max_overflow=1,  # Allow 1 extra connection max (total: 3 per process)
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
