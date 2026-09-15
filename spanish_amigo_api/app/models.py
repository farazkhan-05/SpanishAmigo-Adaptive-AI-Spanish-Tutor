from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, UniqueConstraint, CheckConstraint
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


class SystemStatus(Base):
    __tablename__ = "system_status"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

