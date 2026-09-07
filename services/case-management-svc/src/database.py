"""
Database engine and session management for Case Management Service.
Provides SQLAlchemy Base, SessionLocal factory, and get_db session dependency.
"""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from src.config import settings

# SQLAlchemy Engine with connection pool and pre-ping liveness checks
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Session factory for isolated database transactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative Base for ORM models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency generator for database sessions.
    Guarantees session closure to prevent connection leaks.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
