"""
Unit tests for text normalizer and matcher logic.
"""

from src.matcher import (
    normalize_text,
    normalize_business_name,
    parse_and_normalize_person_name,
    match_entity,
)


def test_normalizer_rules():
    # Suffixes, titles, punctuation stripping
    assert normalize_text("Dr. Leonard Hask, MD") == "DR LEONARD HASK MD"
    first, last = parse_and_normalize_person_name("Dr. Leonard Hask, MD")
    assert first == "LEONARD"
    assert last == "HASK"

    first, last = parse_and_normalize_person_name("Hask, Leonard")
    assert first == "LEONARD"
    assert last == "HASK"

    first, last = parse_and_normalize_person_name("Samuel Okafor")
    assert first == "SAMUEL"
    assert last == "OKAFOR"

    bus_norm = normalize_business_name("Evergreen Mobility Supply LLC")
    assert bus_norm == "EVERGREEN MOBILITY SUPPLY"


def test_npi_match(test_db):
    outcome, basis, rec = match_entity(
        db=test_db,
        role="ordering_provider",
        name="Dr. Leonard Hask, MD",
        npi="1245093876",
        is_organization=False,
    )
    assert outcome == "MATCH"
    assert basis == "npi"
    assert rec.last_name == "HASK"
    assert rec.excl_type == "1128a1"


def test_business_name_fallback_match(test_db):
    outcome, basis, rec = match_entity(
        db=test_db,
        role="facility",
        name="Evergreen Mobility Supply LLC",
        npi="9999999999",  # NPI not in db, falls back to business name
        is_organization=True,
    )
    assert outcome == "POSSIBLE_MATCH"
    assert basis == "business_name"
    assert rec.bus_name == "EVERGREEN MOBILITY SUPPLY LLC"


def test_individual_name_fallback_match(test_db):
    outcome, basis, rec = match_entity(
        db=test_db,
        role="doctor",
        name="Samuel Okafor",
        npi=None,
        is_organization=False,
    )
    assert outcome == "POSSIBLE_MATCH"
    assert basis == "individual_name"
    assert rec.last_name == "OKAFOR"


def test_reinstated_record_no_match(test_db):
    # Robert Vance was reinstated on 2022-03-01 -> MUST be NO_MATCH
    outcome, basis, rec = match_entity(
        db=test_db,
        role="doctor",
        name="Dr. Robert Vance, MD",
        npi=None,
        is_organization=False,
    )
    assert outcome == "NO_MATCH"
    assert rec is None


def test_near_miss_spelling_no_match(test_db):
    # Arthur Pendelton (misspelled) vs PENDLETON in DB -> MUST be NO_MATCH (exact match only)
    outcome, basis, rec = match_entity(
        db=test_db,
        role="doctor",
        name="Arthur Pendelton",
        npi=None,
        is_organization=False,
    )
    assert outcome == "NO_MATCH"
    assert rec is None
