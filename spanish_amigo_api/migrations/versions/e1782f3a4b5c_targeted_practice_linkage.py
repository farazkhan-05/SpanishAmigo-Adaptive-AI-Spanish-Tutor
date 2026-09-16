"""link server-owned targeted practice to its accepted chat evidence

Revision ID: e1782f3a4b5c
Revises: d2e3f4a5b6c7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1782f3a4b5c"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("practice_attempts", sa.Column("source_assessment_event_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_practice_attempts_source_event",
        "practice_attempts",
        "assessment_events",
        ["source_assessment_event_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_practice_attempts_source_assessment_event",
        "practice_attempts",
        ["source_assessment_event_id"],
        unique=True,
        postgresql_where=sa.text("source_assessment_event_id IS NOT NULL"),
        sqlite_where=sa.text("source_assessment_event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_practice_attempts_source_assessment_event", table_name="practice_attempts")
    op.drop_constraint("fk_practice_attempts_source_event", "practice_attempts", type_="foreignkey")
    op.drop_column("practice_attempts", "source_assessment_event_id")
