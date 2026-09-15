"""add non-destructive adaptive curriculum metadata

Revision ID: a3b4c5d6e7f8
Revises: f1a2c3d4e5f6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "f1a2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("skills",
        sa.Column("skill_id", sa.String(100), primary_key=True), sa.Column("display_label", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("category", sa.String(40), nullable=False),
        sa.Column("cefr_level", sa.String(16), nullable=False), sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("learning_objective", sa.Text(), nullable=False), sa.Column("assessment_mode", sa.String(32), nullable=False, server_default="text"), sa.Column("taxonomy_version", sa.String(32), nullable=False),
        sa.CheckConstraint("category IN ('vocabulary', 'grammar', 'communication', 'pronunciation', 'culture')", name="ck_skills_category"),
        sa.CheckConstraint("cefr_level IN ('A1', 'A2', 'B1', 'B2', 'C1', 'C2', 'UNKNOWN')", name="ck_skills_cefr"), sa.CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_skills_difficulty_range"), sa.CheckConstraint("assessment_mode IN ('text', 'speech_required', 'contextual')", name="ck_skills_assessment_mode"))
    op.add_column("lesson_slides", sa.Column("cefr_level", sa.String(16), nullable=True))
    op.add_column("lesson_slides", sa.Column("difficulty", sa.Integer(), nullable=True))
    op.add_column("lesson_slides", sa.Column("learning_objective", sa.Text(), nullable=True))
    op.add_column("lesson_slides", sa.Column("taxonomy_version", sa.String(32), nullable=True))
    op.create_check_constraint("ck_lesson_slides_difficulty_range", "lesson_slides", "difficulty IS NULL OR difficulty BETWEEN 1 AND 5")
    op.create_table("lesson_slide_skills", sa.Column("lesson_slide_id", sa.Integer(), nullable=False), sa.Column("skill_id", sa.String(100), nullable=False), sa.Column("taxonomy_version", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["lesson_slide_id"], ["lesson_slides.id"], name="fk_lesson_slide_skills_slide", ondelete="CASCADE"), sa.ForeignKeyConstraint(["skill_id"], ["skills.skill_id"], name="fk_lesson_slide_skills_skill", ondelete="RESTRICT"), sa.PrimaryKeyConstraint("lesson_slide_id", "skill_id", name="pk_lesson_slide_skills"))
    # `simple` is deliberately language-neutral: curriculum text mixes English prompts and Spanish answers.
    op.execute("ALTER TABLE lesson_slides ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content_text, '') || ' ' || coalesce(explanation, ''))) STORED")
    op.create_index("ix_lesson_slides_search_vector", "lesson_slides", ["search_vector"], postgresql_using="gin")
    # Existing rows are preserved. Abort rather than deleting data if legacy duplicates exist.
    duplicate = op.get_bind().execute(sa.text("SELECT 1 FROM lesson_slides GROUP BY lesson_id, slide_index HAVING count(*) > 1 LIMIT 1")).first()
    if duplicate:
        raise RuntimeError("cannot add uq_lesson_slides_lesson_slide_index: duplicate curriculum rows require manual resolution")
    op.create_unique_constraint("uq_lesson_slides_lesson_slide_index", "lesson_slides", ["lesson_id", "slide_index"])


def downgrade() -> None:
    op.drop_constraint("uq_lesson_slides_lesson_slide_index", "lesson_slides", type_="unique")
    op.drop_index("ix_lesson_slides_search_vector", table_name="lesson_slides")
    op.drop_column("lesson_slides", "search_vector")
    op.drop_table("lesson_slide_skills")
    op.drop_constraint("ck_lesson_slides_difficulty_range", "lesson_slides", type_="check")
    op.drop_column("lesson_slides", "taxonomy_version"); op.drop_column("lesson_slides", "learning_objective"); op.drop_column("lesson_slides", "difficulty"); op.drop_column("lesson_slides", "cefr_level")
    op.drop_table("skills")
