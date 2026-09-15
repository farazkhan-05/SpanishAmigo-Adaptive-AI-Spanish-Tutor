"""add tenant-safe adaptive learner/evidence/practice storage

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("learner_skill_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False), sa.Column("skill_id", sa.String(100), nullable=False),
        sa.Column("mastery_estimate", sa.Float(), nullable=True), sa.Column("estimate_confidence", sa.Float(), nullable=True),
        sa.Column("accepted_evidence_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("independent_attempt_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("assisted_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_practiced_at", sa.DateTime(), nullable=True), sa.Column("last_evidence_at", sa.DateTime(), nullable=True), sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_learner_skill_states"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_learner_skill_states_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.skill_id"], name="fk_learner_skill_states_skill", ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_learner_skill_states_user_skill"),
        sa.CheckConstraint("mastery_estimate IS NULL OR mastery_estimate BETWEEN 0 AND 1", name="ck_learner_skill_states_mastery_range"),
        sa.CheckConstraint("estimate_confidence IS NULL OR estimate_confidence BETWEEN 0 AND 1", name="ck_learner_skill_states_confidence_range"),
        sa.CheckConstraint("accepted_evidence_count >= 0", name="ck_learner_skill_states_accepted_count"), sa.CheckConstraint("independent_attempt_count >= 0", name="ck_learner_skill_states_independent_count"), sa.CheckConstraint("assisted_attempt_count >= 0", name="ck_learner_skill_states_assisted_count"), sa.CheckConstraint("state_version >= 1", name="ck_learner_skill_states_version"))
    op.create_index("ix_learner_skill_states_user_id", "learner_skill_states", ["user_id"])

    op.create_table("assessment_events",
        sa.Column("id", sa.String(36), nullable=False), sa.Column("user_id", sa.String(128), nullable=False), sa.Column("skill_id", sa.String(100), nullable=True),
        sa.Column("chat_session_id", sa.Integer(), nullable=True), sa.Column("chat_message_id", sa.Integer(), nullable=True), sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("evidence_snapshot", sa.Text(), nullable=True), sa.Column("normalized_evidence", sa.Text(), nullable=True), sa.Column("evidence_span_start", sa.Integer(), nullable=True), sa.Column("evidence_span_end", sa.Integer(), nullable=True), sa.Column("evidence_modality", sa.String(32), nullable=False, server_default="text"),
        sa.Column("proposed_result", sa.String(32), nullable=False), sa.Column("error_type", sa.String(100), nullable=True), sa.Column("severity", sa.Integer(), nullable=True), sa.Column("proposal_confidence", sa.Float(), nullable=True), sa.Column("correction", sa.Text(), nullable=True), sa.Column("misconception_id", sa.String(100), nullable=True),
        sa.Column("validation_status", sa.String(32), nullable=False), sa.Column("rejection_reason", sa.String(255), nullable=True), sa.Column("validator_version", sa.String(100), nullable=True), sa.Column("taxonomy_version", sa.String(32), nullable=False), sa.Column("assessment_model_version", sa.String(100), nullable=True), sa.Column("source_event_key", sa.String(160), nullable=True), sa.Column("supersedes_event_id", sa.String(36), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_assessment_events"), sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_assessment_events_user", ondelete="CASCADE"), sa.ForeignKeyConstraint(["skill_id"], ["skills.skill_id"], name="fk_assessment_events_skill", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], name="fk_assessment_events_chat_session", ondelete="SET NULL"), sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], name="fk_assessment_events_chat_message", ondelete="SET NULL"), sa.ForeignKeyConstraint(["supersedes_event_id"], ["assessment_events.id"], name="fk_assessment_events_supersedes", ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "source_event_key", name="uq_assessment_events_user_source_key"), sa.CheckConstraint("source_type IN ('chat_message', 'practice_attempt', 'import', 'manual')", name="ck_assessment_events_source_type"), sa.CheckConstraint("evidence_modality IN ('text', 'speech', 'mixed', 'none')", name="ck_assessment_events_modality"), sa.CheckConstraint("proposed_result IN ('correct', 'incorrect', 'partial', 'unknown', 'not_applicable')", name="ck_assessment_events_result"), sa.CheckConstraint("validation_status IN ('proposed', 'accepted', 'rejected', 'ambiguous', 'invalid', 'low_confidence')", name="ck_assessment_events_status"), sa.CheckConstraint("severity IS NULL OR severity BETWEEN 1 AND 5", name="ck_assessment_events_severity"), sa.CheckConstraint("proposal_confidence IS NULL OR proposal_confidence BETWEEN 0 AND 1", name="ck_assessment_events_confidence"), sa.CheckConstraint("(evidence_span_start IS NULL AND evidence_span_end IS NULL) OR (evidence_span_start >= 0 AND evidence_span_end >= evidence_span_start)", name="ck_assessment_events_evidence_span"))
    op.create_index("ix_assessment_events_user_created", "assessment_events", ["user_id", "created_at"])

    op.create_table("practice_attempts",
        sa.Column("id", sa.String(36), nullable=False), sa.Column("user_id", sa.String(128), nullable=False), sa.Column("skill_id", sa.String(100), nullable=False), sa.Column("assessment_event_id", sa.String(36), nullable=True), sa.Column("chat_session_id", sa.Integer(), nullable=True), sa.Column("chat_message_id", sa.Integer(), nullable=True),
        sa.Column("exercise_id", sa.String(160), nullable=True), sa.Column("exercise_type", sa.String(64), nullable=False), sa.Column("prompt_snapshot", sa.Text(), nullable=True), sa.Column("learner_response_snapshot", sa.Text(), nullable=True), sa.Column("outcome", sa.String(32), nullable=False, server_default="pending"), sa.Column("support_level", sa.String(32), nullable=False, server_default="independent"), sa.Column("hint_used", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("independent_recall", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("processing_version", sa.String(100), nullable=True), sa.Column("taxonomy_version", sa.String(32), nullable=False), sa.Column("source_event_key", sa.String(160), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_practice_attempts"), sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_practice_attempts_user", ondelete="CASCADE"), sa.ForeignKeyConstraint(["skill_id"], ["skills.skill_id"], name="fk_practice_attempts_skill", ondelete="RESTRICT"), sa.ForeignKeyConstraint(["assessment_event_id"], ["assessment_events.id"], name="fk_practice_attempts_assessment_event", ondelete="RESTRICT"), sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], name="fk_practice_attempts_chat_session", ondelete="SET NULL"), sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], name="fk_practice_attempts_chat_message", ondelete="SET NULL"), sa.UniqueConstraint("user_id", "source_event_key", name="uq_practice_attempts_user_source_key"), sa.CheckConstraint("outcome IN ('pending', 'correct', 'incorrect', 'partial', 'invalid', 'not_applicable')", name="ck_practice_attempts_outcome"), sa.CheckConstraint("support_level IN ('independent', 'hinted', 'guided', 'exposure', 'failed')", name="ck_practice_attempts_support_level"), sa.CheckConstraint("independent_recall = false OR (support_level = 'independent' AND hint_used = false)", name="ck_practice_attempts_independent_recall"))
    op.create_index("ix_practice_attempts_user_created", "practice_attempts", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_practice_attempts_user_created", table_name="practice_attempts")
    op.drop_table("practice_attempts")
    op.drop_index("ix_assessment_events_user_created", table_name="assessment_events")
    op.drop_table("assessment_events")
    op.drop_index("ix_learner_skill_states_user_id", table_name="learner_skill_states")
    op.drop_table("learner_skill_states")
