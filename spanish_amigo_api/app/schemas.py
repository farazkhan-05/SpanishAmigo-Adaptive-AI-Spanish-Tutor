from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Literal, Optional, List

class UserCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(..., min_length=1, max_length=128)  # Firebase UID
    email: Optional[str] = Field(None, max_length=255)

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(..., min_length=1, max_length=128)
    email: Optional[str] = Field(None, max_length=255)
    created_at: datetime


class ProgressCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    user_id: str = Field(..., min_length=1, max_length=128)
    lesson_id: str = Field(..., min_length=1, max_length=128)

class ProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    lesson_id: str = Field(..., min_length=1, max_length=128)
    completed_at: datetime


class ChatRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    user_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=2000)
    user_name: Optional[str] = Field("Amigo", max_length=100)
    session_id: Optional[int] = None

class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    reply: str = Field(..., min_length=1)
    action_required: Optional[str] = None
    session_id: Optional[int] = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class SessionUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    title: str = Field(..., min_length=1, max_length=255)


class ExplainRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    spanish_sentence: str = Field(..., min_length=1, max_length=1000)
    english_translation: str = Field(..., min_length=1, max_length=1000)

class ExplainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    explanation: str = Field(..., min_length=1)


class AdaptiveStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    skill_id: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=160)
    assessment_mode: str = Field(..., pattern="^(text|speech_required|contextual)$")
    mastery_estimate: Optional[float] = Field(None, ge=0, le=1)
    estimate_confidence: Optional[float] = Field(None, ge=0, le=1)
    accepted_evidence_count: int = Field(..., ge=0)
    last_practiced_at: Optional[datetime] = None
    status: str = Field(..., pattern="^(not_assessed|evidence_insufficient|assessed)$")


class ReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str
    skill_id: str
    display_name: str
    due_at: datetime
    rationale: str


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str = Field(..., min_length=1, max_length=36)
    learner_answer: str = Field(..., min_length=1, max_length=2000)


class ReviewStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str
    exercise_id: str
    exercise_text: str


class TargetedPracticeRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available: bool
    source_event_id: Optional[str] = None
    skill_id: Optional[str] = None
    display_name: Optional[str] = None
    reason: Optional[str] = None


class TargetedPracticeStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_event_id: str = Field(..., min_length=1, max_length=36)


class TargetedPracticeStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str
    source_event_id: str
    skill_id: str
    display_name: str
    exercise_id: str
    exercise_text: str
    status: str = Field(..., pattern="^(pending|correct|incorrect|partial|invalid|not_applicable)$")


class TargetedPracticeSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_answer: str = Field(..., min_length=1, max_length=2000)


class TargetedPracticeSubmitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str
    event_id: str
    skill_id: str
    status: str = Field(..., pattern="^(accepted|rejected|ambiguous|invalid|low_confidence)$")
    result: str = Field(..., pattern="^(correct|incorrect|partial|unknown|not_applicable)$")
    mastery_updated: bool
    learner_status: str = Field(..., pattern="^(mastery_updated|evidence_recorded|not_accepted|already_completed)$")
    due_at: Optional[datetime] = None


class AssessmentProposal(BaseModel):
    """Strict, reasoning-free model proposal. Application validation is authoritative."""

    model_config = ConfigDict(extra="forbid", strict=True)

    assessable: bool
    skill_id: str = Field(..., min_length=1, max_length=100)
    result: Literal["correct", "incorrect", "partial", "unknown", "not_applicable"]
    error_type: Optional[Literal["grammar", "vocabulary", "word_order", "agreement", "other"]] = None
    severity: Optional[Literal[1, 2, 3]] = None
    confidence: float = Field(..., ge=0, le=1)
    evidence: str = Field(..., min_length=1, max_length=2000)
    correction: Optional[str] = Field(None, max_length=2000)
    misconception_id: Optional[str] = Field(None, max_length=100)
    assessment_version: Literal["phase5-v1"]
