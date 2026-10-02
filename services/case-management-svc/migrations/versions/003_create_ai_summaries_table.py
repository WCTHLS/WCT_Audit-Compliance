"""003_create_ai_summaries_table

Revision ID: 003_create_ai_summaries
Revises: 002_add_exclusion_screening
Create Date: 2026-10-02 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_create_ai_summaries"
down_revision: Union[str, None] = "002_add_exclusion_screening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop ai_summary column from cases if it was added earlier
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("cases")]
    if "ai_summary" in columns:
        op.drop_column("cases", "ai_summary")

    # 2. Create dedicated ai_summaries table for AI Summary Service
    op.create_table(
        "ai_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False, doc="Foreign reference to cases.case_id"),
        sa.Column("claim_ref", sa.String(length=64), nullable=False, doc="Upstream claim reference ID"),
        sa.Column("clinical_summary", sa.Text(), nullable=False, doc="Medical necessity and documentation gap review"),
        sa.Column("risk_factors_summary", sa.Text(), nullable=True, doc="SHAP ML risk drivers and anomaly breakdown"),
        sa.Column("peer_comparison_narrative", sa.Text(), nullable=True, doc="Specialty peer benchmark ranking narrative"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.95", doc="Model confidence score"),
        sa.Column("model_version", sa.String(length=64), nullable=False, server_default="ollama:llama3.2", doc="LLM model version identifier"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), doc="Timestamp of generation"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
    )

    op.create_index("idx_ai_summaries_case_id", "ai_summaries", ["case_id"], unique=False)
    op.create_index("idx_ai_summaries_claim_ref", "ai_summaries", ["claim_ref"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_ai_summaries_claim_ref", table_name="ai_summaries")
    op.drop_index("idx_ai_summaries_case_id", table_name="ai_summaries")
    op.drop_table("ai_summaries")