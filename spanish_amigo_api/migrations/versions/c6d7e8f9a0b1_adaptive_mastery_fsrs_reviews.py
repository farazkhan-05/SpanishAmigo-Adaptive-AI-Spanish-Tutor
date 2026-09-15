"""add phase 6 mastery FSRS review state

Revision ID: c6d7e8f9a0b1
Revises: b4c5d6e7f8a9
"""
from alembic import op
import sqlalchemy as sa

revision = "c6d7e8f9a0b1"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("review_items",
        sa.Column("id", sa.String(36), nullable=False), sa.Column("user_id", sa.String(128), nullable=False), sa.Column("skill_id", sa.String(100), nullable=False),
        sa.Column("card_state", sa.Integer(), nullable=False), sa.Column("card_step", sa.Integer(), nullable=True), sa.Column("stability", sa.Float(), nullable=True), sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=True), sa.Column("fsrs_version", sa.String(32), nullable=False), sa.Column("scheduler_version", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_review_items"), sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_review_items_user", ondelete="CASCADE"), sa.ForeignKeyConstraint(["skill_id"], ["skills.skill_id"], name="fk_review_items_skill", ondelete="RESTRICT"), sa.UniqueConstraint("user_id", "skill_id", name="uq_review_items_user_skill"), sa.CheckConstraint("card_state BETWEEN 1 AND 4", name="ck_review_items_card_state"))
    op.create_index("ix_review_items_user_due", "review_items", ["user_id", "due_at"])
    op.add_column("practice_attempts", sa.Column("review_item_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_practice_attempts_review_item", "practice_attempts", "review_items", ["review_item_id"], ["id"], ondelete="SET NULL")
    op.create_table("review_history",
        sa.Column("id", sa.String(36), nullable=False), sa.Column("user_id", sa.String(128), nullable=False), sa.Column("review_item_id", sa.String(36), nullable=False), sa.Column("skill_id", sa.String(100), nullable=False), sa.Column("practice_attempt_id", sa.String(36), nullable=True), sa.Column("assessment_event_id", sa.String(36), nullable=False), sa.Column("rating", sa.Integer(), nullable=False), sa.Column("previous_card", sa.Text(), nullable=False), sa.Column("new_card", sa.Text(), nullable=False), sa.Column("due_at", sa.DateTime(timezone=True), nullable=False), sa.Column("mastery_algorithm_version", sa.String(64), nullable=False), sa.Column("fsrs_version", sa.String(32), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_review_history"), sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_review_history_user", ondelete="CASCADE"), sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"], name="fk_review_history_item", ondelete="CASCADE"), sa.ForeignKeyConstraint(["skill_id"], ["skills.skill_id"], name="fk_review_history_skill", ondelete="RESTRICT"), sa.ForeignKeyConstraint(["practice_attempt_id"], ["practice_attempts.id"], name="fk_review_history_attempt", ondelete="SET NULL"), sa.ForeignKeyConstraint(["assessment_event_id"], ["assessment_events.id"], name="fk_review_history_event", ondelete="RESTRICT"), sa.UniqueConstraint("assessment_event_id", name="uq_review_history_event"), sa.CheckConstraint("rating BETWEEN 1 AND 4", name="ck_review_history_rating"))
    op.create_index("ix_review_history_user_created", "review_history", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_review_history_user_created", table_name="review_history")
    op.drop_table("review_history")
    op.drop_index("ix_review_items_user_due", table_name="review_items")
    op.drop_constraint("fk_practice_attempts_review_item", "practice_attempts", type_="foreignkey")
    op.drop_column("practice_attempts", "review_item_id")
    op.drop_table("review_items")
