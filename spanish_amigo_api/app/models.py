from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, String, Integer, DateTime, ForeignKey, Text, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR
from app.database import Base


class User(Base):
    __tablename__ = "users"

    # Firebase UID is stored as a string ID
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    completed_lessons: Mapped[list["CompletedLesson"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    learner_skill_states: Mapped[list["LearnerSkillState"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    assessment_events: Mapped[list["AssessmentEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    practice_attempts: Mapped[list["PracticeAttempt"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class CompletedLesson(Base):
    __tablename__ = "completed_lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[str] = mapped_column(String(100), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="completed_lessons")

    # Prevent duplicate records for the same lesson
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_user_lesson"),
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="chat_messages")
    session: Mapped[Optional["ChatSession"]] = relationship(back_populates="messages")


class LessonSlide(Base):
    __tablename__ = "lesson_slides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lesson_id: Mapped[int] = mapped_column(Integer, nullable=False)
    slide_index: Mapped[int] = mapped_column(Integer, nullable=False)
    slide_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'context', 'reveal', 'practice'
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=True)
    embedding = mapped_column(Vector(768), nullable=True) # gemini-embedding-2 output vector optimized to 768 dimensions
    cefr_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    difficulty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    learning_objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    taxonomy_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    search_vector = mapped_column(TSVECTOR, nullable=True)
    skills: Mapped[list["Skill"]] = relationship(secondary="lesson_slide_skills", back_populates="slides")

    __table_args__ = (
        UniqueConstraint("lesson_id", "slide_index", name="uq_lesson_slides_lesson_slide_index"),
        CheckConstraint("difficulty IS NULL OR difficulty BETWEEN 1 AND 5", name="ck_lesson_slides_difficulty_range"),
    )


class Skill(Base):
    """Stable, curriculum-owned educational concept; its string ID is semantic identity."""
    __tablename__ = "skills"

    skill_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    cefr_level: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    learning_objective: Mapped[str] = mapped_column(Text, nullable=False)
    assessment_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    taxonomy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    slides: Mapped[list["LessonSlide"]] = relationship(secondary="lesson_slide_skills", back_populates="skills")

    __table_args__ = (
        CheckConstraint("category IN ('vocabulary', 'grammar', 'communication', 'pronunciation', 'culture')", name="ck_skills_category"),
        CheckConstraint("cefr_level IN ('A1', 'A2', 'B1', 'B2', 'C1', 'C2', 'UNKNOWN')", name="ck_skills_cefr"),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_skills_difficulty_range"),
        CheckConstraint("assessment_mode IN ('text', 'speech_required', 'contextual')", name="ck_skills_assessment_mode"),
    )


class LessonSlideSkill(Base):
    __tablename__ = "lesson_slide_skills"

    lesson_slide_id: Mapped[int] = mapped_column(Integer, ForeignKey("lesson_slides.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(100), ForeignKey("skills.skill_id", ondelete="RESTRICT"), primary_key=True)
    taxonomy_version: Mapped[str] = mapped_column(String(32), nullable=False)


class LearnerSkillState(Base):
    """Tenant-owned, deliberately non-authoritative-until-evidenced skill state."""
    __tablename__ = "learner_skill_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE", name="fk_learner_skill_states_user"), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(100), ForeignKey("skills.skill_id", ondelete="RESTRICT", name="fk_learner_skill_states_skill"), nullable=False)
    # NULL means unknown: no writer in Phase 4 may invent a mastery estimate.
    mastery_estimate: Mapped[Optional[float]] = mapped_column(nullable=True)
    estimate_confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    accepted_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    independent_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assisted_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_practiced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_evidence_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="learner_skill_states")
    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_learner_skill_states_user_skill"),
        CheckConstraint("mastery_estimate IS NULL OR mastery_estimate BETWEEN 0 AND 1", name="ck_learner_skill_states_mastery_range"),
        CheckConstraint("estimate_confidence IS NULL OR estimate_confidence BETWEEN 0 AND 1", name="ck_learner_skill_states_confidence_range"),
        CheckConstraint("accepted_evidence_count >= 0", name="ck_learner_skill_states_accepted_count"),
        CheckConstraint("independent_attempt_count >= 0", name="ck_learner_skill_states_independent_count"),
        CheckConstraint("assisted_attempt_count >= 0", name="ck_learner_skill_states_assisted_count"),
        CheckConstraint("state_version >= 1", name="ck_learner_skill_states_version"),
        Index("ix_learner_skill_states_user_id", "user_id"),
    )


class AssessmentEvent(Base):
    """Append-only structured assessment conclusion and its minimally necessary evidence."""
    __tablename__ = "assessment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE", name="fk_assessment_events_user"), nullable=False)
    skill_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("skills.skill_id", ondelete="RESTRICT", name="fk_assessment_events_skill"), nullable=True)
    chat_session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("chat_sessions.id", ondelete="SET NULL", name="fk_assessment_events_chat_session"), nullable=True)
    chat_message_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("chat_messages.id", ondelete="SET NULL", name="fk_assessment_events_chat_message"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    normalized_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_span_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    evidence_span_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    evidence_modality: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    proposed_result: Mapped[str] = mapped_column(String(32), nullable=False)
    error_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    severity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    proposal_confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    correction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    misconception_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    validator_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    taxonomy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    assessment_model_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_event_key: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    supersedes_event_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("assessment_events.id", ondelete="RESTRICT", name="fk_assessment_events_supersedes"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="assessment_events")
    __table_args__ = (
        UniqueConstraint("user_id", "source_event_key", name="uq_assessment_events_user_source_key"),
        CheckConstraint("source_type IN ('chat_message', 'practice_attempt', 'import', 'manual')", name="ck_assessment_events_source_type"),
        CheckConstraint("evidence_modality IN ('text', 'speech', 'mixed', 'none')", name="ck_assessment_events_modality"),
        CheckConstraint("proposed_result IN ('correct', 'incorrect', 'partial', 'unknown', 'not_applicable')", name="ck_assessment_events_result"),
        CheckConstraint("validation_status IN ('proposed', 'accepted', 'rejected', 'ambiguous', 'invalid', 'low_confidence')", name="ck_assessment_events_status"),
        CheckConstraint("severity IS NULL OR severity BETWEEN 1 AND 5", name="ck_assessment_events_severity"),
        CheckConstraint("proposal_confidence IS NULL OR proposal_confidence BETWEEN 0 AND 1", name="ck_assessment_events_confidence"),
        CheckConstraint("(evidence_span_start IS NULL AND evidence_span_end IS NULL) OR (evidence_span_start >= 0 AND evidence_span_end >= evidence_span_start)", name="ck_assessment_events_evidence_span"),
        Index("ix_assessment_events_user_created", "user_id", "created_at"),
    )


class PracticeAttempt(Base):
    """Stored practice input/outcome; it does not mutate mastery in Phase 4."""
    __tablename__ = "practice_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE", name="fk_practice_attempts_user"), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(100), ForeignKey("skills.skill_id", ondelete="RESTRICT", name="fk_practice_attempts_skill"), nullable=False)
    assessment_event_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("assessment_events.id", ondelete="RESTRICT", name="fk_practice_attempts_assessment_event"), nullable=True)
    chat_session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("chat_sessions.id", ondelete="SET NULL", name="fk_practice_attempts_chat_session"), nullable=True)
    chat_message_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("chat_messages.id", ondelete="SET NULL", name="fk_practice_attempts_chat_message"), nullable=True)
    exercise_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    exercise_type: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    learner_response_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    support_level: Mapped[str] = mapped_column(String(32), nullable=False, default="independent")
    hint_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    independent_recall: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processing_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    taxonomy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_event_key: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="practice_attempts")
    __table_args__ = (
        UniqueConstraint("user_id", "source_event_key", name="uq_practice_attempts_user_source_key"),
        CheckConstraint("outcome IN ('pending', 'correct', 'incorrect', 'partial', 'invalid', 'not_applicable')", name="ck_practice_attempts_outcome"),
        CheckConstraint("support_level IN ('independent', 'hinted', 'guided', 'exposure', 'failed')", name="ck_practice_attempts_support_level"),
        CheckConstraint("independent_recall = false OR (support_level = 'independent' AND hint_used = false)", name="ck_practice_attempts_independent_recall"),
        Index("ix_practice_attempts_user_created", "user_id", "created_at"),
    )


class SystemStatus(Base):
    __tablename__ = "system_status"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
