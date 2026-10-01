"""
SQLAlchemy ORM models for Exclusion Screening Service.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Index,
)
from src.db import Base


class ExclusionRecord(Base):
    """
    Exclusion record representing federal (OIG LEIE) or synthetic exclusion entries.
    """

    __tablename__ = "exclusion_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False, default="LEIE")  # LEIE, SYNTHETIC, SAM
    last_name = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    mid_name = Column(String(255), nullable=True)
    bus_name = Column(String(255), nullable=True)
    npi = Column(String(10), nullable=True)
    general = Column(String(255), nullable=True)
    specialty = Column(String(255), nullable=True)
    upin = Column(String(32), nullable=True)
    dob = Column(Date, nullable=True)
    address = Column(String(255), nullable=True)
    city = Column(String(128), nullable=True)
    state = Column(String(32), nullable=True)
    zip = Column(String(32), nullable=True)
    excl_type = Column(String(32), nullable=True)
    excl_date = Column(Date, nullable=True)
    rein_date = Column(Date, nullable=True)
    waiver_date = Column(Date, nullable=True)
    waiver_state = Column(String(32), nullable=True)
    loaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_exclusion_records_npi", "npi"),
        Index("idx_exclusion_records_names", "last_name", "first_name"),
        Index("idx_exclusion_records_bus_name", "bus_name"),
        Index("idx_exclusion_records_source", "source"),
    )

    def is_reinstated(self) -> bool:
        """Returns True if the exclusion has been revoked/reinstated."""
        return self.rein_date is not None
