"""
Tests for jobs/load_exclusions.py bulk loader logic.
"""

from pathlib import Path
from jobs.load_exclusions import parse_date, load_file
from src.models import ExclusionRecord


def test_parse_date():
    assert parse_date("20250618").isoformat() == "2025-06-18"
    assert parse_date("00000000") is None
    assert parse_date("") is None
    assert parse_date(None) is None
    assert parse_date("invalid") is None


def test_load_synthetic_file(test_db):
    seed_file = Path("services/exclusion-screening-svc/seed/leie_synthetic_overlay.csv")
    assert seed_file.exists()
    
    # Verify records in test_db
    records = test_db.query(ExclusionRecord).filter(ExclusionRecord.source == "SYNTHETIC").all()
    assert len(records) >= 5
    
    # Ensure Hask is present
    hask = test_db.query(ExclusionRecord).filter(ExclusionRecord.npi == "1245093876").first()
    assert hask is not None
    assert hask.last_name == "HASK"
    assert hask.first_name == "LEONARD"