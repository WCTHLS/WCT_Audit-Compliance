"""
Normalization and matching logic for Exclusion Screening.
Complies with OIG LEIE guidelines and WCT Module 5 specifications.
"""

import re
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from src.models import ExclusionRecord


# Titles and suffixes to strip during normalization
TITLES_AND_SUFFIXES = {
    "DR", "DOCTOR", "MD", "DO", "PHD", "DDS", "DMD", "DPM", "DC", "OD",
    "JR", "SR", "II", "III", "IV", "V",
    "LLC", "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED",
    "PC", "PA", "LLP", "PLLC"
}

PUNCTUATION_REGEX = re.compile(r"[^\w\s,]")
WHITESPACE_REGEX = re.compile(r"\s+")


def normalize_text(text: Optional[str]) -> str:
    """
    Standard normalizer: upper-cases, strips punctuation, collapses whitespace.
    """
    if not text:
        return ""
    # Uppercase
    cleaned = text.upper()
    # Strip non-alphanumeric except whitespace and comma
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    # Collapse spaces
    cleaned = WHITESPACE_REGEX.sub(" ", cleaned).strip()
    return cleaned


def normalize_business_name(name: Optional[str]) -> str:
    """
    Normalizes business/entity name by removing punctuation, corporate suffixes, and whitespace.
    """
    cleaned = normalize_text(name)
    if not cleaned:
        return ""
    
    tokens = cleaned.split()
    # Filter out corporate suffixes
    filtered = [t for t in tokens if t not in TITLES_AND_SUFFIXES]
    return " ".join(filtered) if filtered else cleaned


def parse_and_normalize_person_name(full_name: Optional[str]) -> Tuple[str, str]:
    """
    Parses full personal name into (first_name, last_name) normalized.
    Handles formats like:
      - 'Dr. Leonard Hask, MD' -> ('LEONARD', 'HASK')
      - 'Hask, Leonard'        -> ('LEONARD', 'HASK')
      - 'Leonard Hask'         -> ('LEONARD', 'HASK')
      - 'Samuel Okafor'        -> ('SAMUEL', 'OKAFOR')
    """
    if not full_name:
        return "", ""
    
    # Split by comma if present
    raw_parts = [p.strip() for p in full_name.split(",") if p.strip()]
    cleaned_parts = []
    for part in raw_parts:
        tokens = [t for t in normalize_text(part).split() if t not in TITLES_AND_SUFFIXES]
        if tokens:
            cleaned_parts.append(tokens)
            
    if not cleaned_parts:
        return "", ""
        
    if len(cleaned_parts) == 1:
        tokens = cleaned_parts[0]
        if len(tokens) == 1:
            return "", tokens[0]
        return tokens[0], tokens[-1]
        
    # If 2 parts, check if first part is single word (likely "Last, First")
    if len(cleaned_parts) >= 2:
        part1 = cleaned_parts[0]
        part2 = cleaned_parts[1]
        if len(part1) == 1:
            # "Hask, Leonard" -> last_name = Hask, first_name = Leonard
            return part2[0], part1[0]
        else:
            # "Dr. Leonard Hask, MD" where MD was filtered or was 2nd part
            # part1 is ['LEONARD', 'HASK']
            return part1[0], part1[-1]

    return "", ""


def clean_npi(npi: Optional[str]) -> Optional[str]:
    """Returns valid 10-digit NPI or None."""
    if not npi:
        return None
    s = str(npi).strip()
    if s == "" or s == "0000000000" or s == "None" or s == "null":
        return None
    if len(s) == 10 and s.isdigit():
        return s
    return s if s else None


def match_entity(
    db: Session,
    role: str,
    name: Optional[str] = None,
    npi: Optional[str] = None,
    is_organization: bool = False,
) -> Tuple[str, str, Optional[ExclusionRecord]]:
    """
    Evaluates an entity against exclusion_records table.
    
    Returns:
      (result, match_basis, matched_record)
      where result is 'MATCH' | 'POSSIBLE_MATCH' | 'NO_MATCH'
    """
    cleaned_npi_val = clean_npi(npi)
    
    # Rule 1 & 2: Check NPI match (if NPI is available)
    if cleaned_npi_val:
        npi_records: List[ExclusionRecord] = (
            db.query(ExclusionRecord)
            .filter(ExclusionRecord.npi == cleaned_npi_val)
            .all()
        )
        for rec in npi_records:
            # Rule 1: Skip reinstated records
            if rec.is_reinstated():
                continue
            # Rule 2: NPI equal and active -> MATCH
            return "MATCH", "npi", rec

    # Rule 3: Check Name-based match (POSSIBLE_MATCH)
    if is_organization or not name:
        # Check Business Name
        norm_bus = normalize_business_name(name)
        if norm_bus:
            # Match against bus_name in DB
            bus_records = (
                db.query(ExclusionRecord)
                .filter(ExclusionRecord.bus_name.isnot(None))
                .all()
            )
            for rec in bus_records:
                if rec.is_reinstated():
                    continue
                rec_bus_norm = normalize_business_name(rec.bus_name)
                if rec_bus_norm and rec_bus_norm == norm_bus:
                    return "POSSIBLE_MATCH", "business_name", rec
    
    # Try individual personal name match if not already matched
    if name:
        first_name, last_name = parse_and_normalize_person_name(name)
        if last_name:
            query = db.query(ExclusionRecord).filter(
                ExclusionRecord.last_name.isnot(None)
            )
            if first_name:
                query = query.filter(ExclusionRecord.first_name.isnot(None))
            
            candidates = query.all()
            for rec in candidates:
                if rec.is_reinstated():
                    continue
                
                rec_last = normalize_text(rec.last_name)
                rec_first = normalize_text(rec.first_name)
                
                if first_name:
                    if rec_last == last_name and rec_first == first_name:
                        return "POSSIBLE_MATCH", "individual_name", rec
                else:
                    if rec_last == last_name:
                        return "POSSIBLE_MATCH", "last_name", rec

        # Also fallback to check if business name matches full name
        norm_bus = normalize_business_name(name)
        if norm_bus:
            bus_records = (
                db.query(ExclusionRecord)
                .filter(ExclusionRecord.bus_name.isnot(None))
                .all()
            )
            for rec in bus_records:
                if rec.is_reinstated():
                    continue
                rec_bus_norm = normalize_business_name(rec.bus_name)
                if rec_bus_norm and rec_bus_norm == norm_bus:
                    return "POSSIBLE_MATCH", "business_name", rec

    # Rule 4: NO_MATCH
    return "NO_MATCH", "none", None