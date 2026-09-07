"""001_create_cases_table

Revision ID: 001_create_cases
Revises: 
Create Date: 2026-09-07 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_create_cases"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create cases table
    op.create_table(
        "cases",
        sa.Column("case_id", sa.String(length=64), nullable=False, doc="Unique case ID"),
        sa.Column("claim_ref", sa.String(length=64), nullable=False, doc="Claim reference ID"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="NEW", doc="Case status"),
        sa.Column("risk_score", sa.Integer(), nullable=False, doc="Risk score (100-1000)"),
        sa.Column("flagged_reason", sa.Text(), nullable=False, doc="Reason flagged"),
        sa.Column("source_module", sa.String(length=32), nullable=False, server_default="fwa_detection"),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        
        # Clinical & Facility Context
        sa.Column("facility_npi", sa.String(length=10), nullable=False),
        sa.Column("facility_name", sa.String(length=255), nullable=False),
        sa.Column("doctor_npi", sa.String(length=10), nullable=False),
        sa.Column("doctor_name", sa.String(length=255), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=True),
        sa.Column("service_date", sa.Date(), nullable=True),
        sa.Column("total_claim_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        
        # Evidence Pointers (JSONB on Postgres, JSON generic)
        sa.Column(
            "evidence_pointers",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        
        # Auditor & SLA
        sa.Column("assigned_auditor", sa.String(length=128), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_type", sa.String(length=32), nullable=False, server_default="INITIAL_REVIEW"),
        sa.Column("sla_breached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        
        # Decision & Compliance
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("decision_rationale", sa.Text(), nullable=True),
        sa.Column("regulatory_basis", sa.String(length=255), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        
        sa.PrimaryKeyConstraint("case_id"),
    )

    # 2. Create Indexes for fast querying
    op.create_index("ix_cases_case_id", "cases", ["case_id"], unique=True)
    op.create_index("ix_cases_claim_ref", "cases", ["claim_ref"], unique=False)
    op.create_index("ix_cases_status", "cases", ["status"], unique=False)
    op.create_index("ix_cases_assigned_auditor", "cases", ["assigned_auditor"], unique=False)
    op.create_index("ix_cases_sla_due_at", "cases", ["sla_due_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cases_sla_due_at", table_name="cases")
    op.drop_index("ix_cases_assigned_auditor", table_name="cases")
    op.drop_index("ix_cases_status", table_name="cases")
    op.drop_index("ix_cases_claim_ref", table_name="cases")
    op.drop_index("ix_cases_case_id", table_name="cases")
    op.drop_table("cases")
