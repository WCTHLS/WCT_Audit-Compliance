"""002_add_exclusion_screening

Revision ID: 002_add_exclusion_screening
Revises: 001_create_cases
Create Date: 2026-10-02 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_add_exclusion_screening"
down_revision: Union[str, None] = "001_create_cases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add exclusion screening columns to cases table
    op.add_column(
        "cases",
        sa.Column(
            "exclusion_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Flag indicating whether physician or facility is on the federal exclusion list",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "exclusion_result",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
            comment="Detailed multi-entity exclusion screening payload and match records",
        ),
    )
    op.create_index("ix_cases_exclusion_flag", "cases", ["exclusion_flag"], unique=False)

    # 2. Create exclusion_records table for OIG LEIE and synthetic datasets
    op.create_table(
        "exclusion_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="LEIE"),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("mid_name", sa.String(length=255), nullable=True),
        sa.Column("bus_name", sa.String(length=255), nullable=True),
        sa.Column("npi", sa.String(length=10), nullable=True),
        sa.Column("general", sa.String(length=255), nullable=True),
        sa.Column("specialty", sa.String(length=255), nullable=True),
        sa.Column("upin", sa.String(length=32), nullable=True),
        sa.Column("dob", sa.Date(), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=True),
        sa.Column("zip", sa.String(length=32), nullable=True),
        sa.Column("excl_type", sa.String(length=32), nullable=True),
        sa.Column("excl_date", sa.Date(), nullable=True),
        sa.Column("rein_date", sa.Date(), nullable=True),
        sa.Column("waiver_date", sa.Date(), nullable=True),
        sa.Column("waiver_state", sa.String(length=32), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_exclusion_records_npi", "exclusion_records", ["npi"], unique=False)
    op.create_index("idx_exclusion_records_names", "exclusion_records", ["last_name", "first_name"], unique=False)
    op.create_index("idx_exclusion_records_bus_name", "exclusion_records", ["bus_name"], unique=False)
    op.create_index("idx_exclusion_records_source", "exclusion_records", ["source"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_exclusion_records_source", table_name="exclusion_records")
    op.drop_index("idx_exclusion_records_bus_name", table_name="exclusion_records")
    op.drop_index("idx_exclusion_records_names", table_name="exclusion_records")
    op.drop_index("idx_exclusion_records_npi", table_name="exclusion_records")
    op.drop_table("exclusion_records")

    op.drop_index("ix_cases_exclusion_flag", table_name="cases")
    op.drop_column("cases", "exclusion_result")
    op.drop_column("cases", "exclusion_flag")