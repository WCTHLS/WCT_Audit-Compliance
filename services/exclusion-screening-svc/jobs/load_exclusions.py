"""
Loader job to import OIG LEIE and synthetic exclusion datasets into PostgreSQL.
Usage:
    python jobs/load_exclusions.py --file seed/UPDATED.csv --source LEIE
    python jobs/load_exclusions.py --file seed/leie_synthetic_overlay.csv --source SYNTHETIC
"""

import sys
import os
import argparse
import csv
from datetime import datetime, date, timezone
from pathlib import Path

# Add service root to path
service_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_root))

from src.db import engine, SessionLocal, Base
from src.models import ExclusionRecord
from src.matcher import normalize_text, clean_npi


def parse_date(val: str) -> date | None:
    """Parses YYYYMMDD string into date, handling 00000000 or blanks."""
    if not val:
        return None
    val = val.strip().replace("-", "")
    if len(val) != 8 or val == "00000000" or not val.isdigit():
        return None
    try:
        return datetime.strptime(val, "%Y%m%d").date()
    except ValueError:
        return None


def load_file(file_path: str, source: str):
    """
    Replaces all records for the given source with contents from file_path.
    """
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    print(f"--- Starting loader for source '{source}' from '{file_path}' ---")
    
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    session = SessionLocal()
    try:
        # Step 1: Delete existing records for this source (Atomic Replace)
        deleted_count = session.query(ExclusionRecord).filter(ExclusionRecord.source == source).delete()
        session.commit()
        print(f"Purged {deleted_count} existing records for source '{source}'.")

        # Step 2: Read and parse CSV records
        records_to_insert = []
        batch_size = 5000
        inserted_total = 0
        loaded_timestamp = datetime.now(timezone.utc)

        with open(path, mode="r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            # Standardize header names
            for row in reader:
                # Handle keys regardless of casing
                r = {k.strip().upper(): (v.strip() if v else "") for k, v in row.items() if k}
                
                npi_val = clean_npi(r.get("NPI", ""))
                last_n = normalize_text(r.get("LASTNAME", "")) or None
                first_n = normalize_text(r.get("FIRSTNAME", "")) or None
                mid_n = normalize_text(r.get("MIDNAME", "")) or None
                bus_n = normalize_text(r.get("BUSNAME", "")) or None
                
                # If both personal names and bus_name are empty and no NPI, skip malformed line
                if not last_n and not bus_n and not npi_val:
                    continue

                rec = {
                    "source": source,
                    "last_name": last_n,
                    "first_name": first_n,
                    "mid_name": mid_n,
                    "bus_name": bus_n,
                    "npi": npi_val,
                    "general": r.get("GENERAL") or None,
                    "specialty": r.get("SPECIALTY") or None,
                    "upin": r.get("UPIN") or None,
                    "dob": parse_date(r.get("DOB", "")),
                    "address": r.get("ADDRESS") or None,
                    "city": r.get("CITY") or None,
                    "state": r.get("STATE") or None,
                    "zip": r.get("ZIP") or None,
                    "excl_type": r.get("EXCLTYPE") or None,
                    "excl_date": parse_date(r.get("EXCLDATE", "")),
                    "rein_date": parse_date(r.get("REINDATE", "")),
                    "waiver_date": parse_date(r.get("WAIVERDATE", "")),
                    "waiver_state": r.get("WVRSTATE") or None,
                    "loaded_at": loaded_timestamp,
                }
                records_to_insert.append(rec)

                if len(records_to_insert) >= batch_size:
                    session.bulk_insert_mappings(ExclusionRecord, records_to_insert)
                    session.commit()
                    inserted_total += len(records_to_insert)
                    records_to_insert = []
                    print(f"Inserted {inserted_total} rows...")

        if records_to_insert:
            session.bulk_insert_mappings(ExclusionRecord, records_to_insert)
            session.commit()
            inserted_total += len(records_to_insert)

        print(f"Successfully loaded {inserted_total} records for source '{source}'.")
    except Exception as e:
        session.rollback()
        print(f"Failed to load exclusion records: {e}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk load OIG LEIE exclusion datasets.")
    parser.add_argument("--file", required=True, help="Path to the CSV file to load")
    parser.add_argument("--source", default="LEIE", choices=["LEIE", "SYNTHETIC", "SAM"], help="Data source tag")
    args = parser.parse_args()

    load_file(args.file, args.source)
