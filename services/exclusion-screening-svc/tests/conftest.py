"""
Pytest configuration and test database fixture.
"""

import sys
from pathlib import Path

service_dir = Path(__file__).resolve().parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))

# Also ensure repo root is in sys.path for evidence_lookup and mock-data
repo_root = service_dir.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import pytest
from datetime import date, datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from src.db import Base, get_db
import src.models
from src.models import ExclusionRecord
from src.main import app

# Shared in-memory SQLite with StaticPool so all sessions share the tables
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_db():
    """Provides a fresh test database with synthetic exclusion records."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    # Seed synthetic records
    records = [
        ExclusionRecord(
            source="SYNTHETIC",
            last_name="HASK",
            first_name="LEONARD",
            npi="1245093876",
            general="IND- LIC HC SERV PRO",
            specialty="FAMILY MEDICINE",
            excl_type="1128a1",
            excl_date=date(2025, 6, 18),
            rein_date=None,
            loaded_at=datetime.now(timezone.utc),
        ),
        ExclusionRecord(
            source="SYNTHETIC",
            bus_name="EVERGREEN MOBILITY SUPPLY LLC",
            npi=None,
            general="DME COMPANY",
            specialty="MEDICAL EQUIPMENT",
            excl_type="1128b7",
            excl_date=date(2026, 5, 12),
            rein_date=None,
            loaded_at=datetime.now(timezone.utc),
        ),
        ExclusionRecord(
            source="SYNTHETIC",
            last_name="OKAFOR",
            first_name="SAMUEL",
            npi=None,
            general="IND- LIC HC SERV PRO",
            specialty="PSYCHOLOGIST",
            excl_type="1128b4",
            excl_date=date(2024, 2, 20),
            rein_date=None,
            loaded_at=datetime.now(timezone.utc),
        ),
        ExclusionRecord(
            source="SYNTHETIC",
            last_name="PENDLETON",
            first_name="ARTHUR",
            mid_name="J",
            npi=None,
            general="IND- LIC HC SERV PRO",
            specialty="ORTHOPEDIC SURGERY",
            excl_type="1128b8",
            excl_date=date(2023, 1, 5),
            rein_date=None,
            loaded_at=datetime.now(timezone.utc),
        ),
        ExclusionRecord(
            source="SYNTHETIC",
            last_name="VANCE",
            first_name="ROBERT",
            npi=None,
            general="IND- LIC HC SERV PRO",
            specialty="CARDIOLOGY",
            excl_type="1128a1",
            excl_date=date(2019, 8, 14),
            rein_date=date(2022, 3, 1),  # Reinstated!
            loaded_at=datetime.now(timezone.utc),
        ),
    ]
    db.add_all(records)
    db.commit()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield db
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    """Provides a TestClient wired to the test database session."""
    with TestClient(app) as c:
        yield c