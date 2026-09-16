"""add privacy-safe AI telemetry events

Revision ID: d2e3f4a5b6c7
Revises: c6d7e8f9a0b1
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("ai_telemetry_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operation_id", sa.String(36), nullable=False), sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False), sa.Column("total_duration_ms", sa.Float()), sa.Column("ttft_ms", sa.Float()),
        sa.Column("model_duration_ms", sa.Float()), sa.Column("retrieval_duration_ms", sa.Float()), sa.Column("assessment_duration_ms", sa.Float()), sa.Column("embedding_duration_ms", sa.Float()),
        sa.Column("model_name", sa.String(128)), sa.Column("fallback_used", sa.Boolean(), nullable=False), sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer()), sa.Column("output_tokens", sa.Integer()), sa.Column("total_tokens", sa.Integer()),
        sa.Column("structured_output_failure", sa.String(100)), sa.Column("assessment_rejection_reason", sa.String(255)),
        sa.Column("adaptive_update_failure", sa.String(100)), sa.Column("review_scheduling_failure", sa.String(100)), sa.Column("error_category", sa.String(100)))
    op.create_index("ix_ai_telemetry_events_occurred_operation", "ai_telemetry_events", ["occurred_at", "operation"])

def downgrade() -> None:
    op.drop_index("ix_ai_telemetry_events_occurred_operation", table_name="ai_telemetry_events")
    op.drop_table("ai_telemetry_events")
