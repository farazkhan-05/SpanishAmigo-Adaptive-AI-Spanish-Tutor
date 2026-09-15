"""Tenant-scoped Phase-4 adaptive storage helpers.

These helpers intentionally store audit inputs without assessing them or mutating
mastery.  Callers must pass the UID obtained from verified Firebase claims.
"""
from __future__ import annotations

from typing import Literal, Optional, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.curriculum_metadata import SKILLS, TAXONOMY_VERSION, SkillDefinition
from app.models import AssessmentEvent, LearnerSkillState, PracticeAttempt

AssessmentStatus = Literal["proposed", "accepted", "rejected", "ambiguous", "invalid", "low_confidence"]
LearnerResult = Literal["correct", "incorrect", "partial", "unknown", "not_applicable"]


def skill_definition(skill_id: str) -> SkillDefinition:
    for skill in SKILLS:
        if skill.skill_id == skill_id:
            return skill
    raise ValueError("unknown stable skill ID")


def mastery_eligibility(skill_id: str, evidence_modality: str) -> bool:
    """Foundation only: later validators must use this before any state mutation."""
    skill = skill_definition(skill_id)
    return skill.assessment_mode == "text" and evidence_modality == "text"


def status_for_state(state: Optional[LearnerSkillState], skill_id: str) -> str:
    skill = skill_definition(skill_id)
    # Contextual tags are never exposed as atomic mastery claims.
    if skill.assessment_mode == "contextual":
        return "not_assessed"
    if state is None or state.mastery_estimate is None:
        return "evidence_insufficient" if state and state.accepted_evidence_count else "not_assessed"
    return "assessed"


def get_state_for_user(db: Session, verified_uid: str, skill_id: str) -> Optional[LearnerSkillState]:
    return cast(Optional[LearnerSkillState], db.scalar(select(LearnerSkillState).where(LearnerSkillState.user_id == verified_uid, LearnerSkillState.skill_id == skill_id)))


def get_states_for_user(db: Session, verified_uid: str) -> list[LearnerSkillState]:
    return list(db.scalars(select(LearnerSkillState).where(LearnerSkillState.user_id == verified_uid).order_by(LearnerSkillState.skill_id)))


def create_unknown_state(db: Session, verified_uid: str, skill_id: str) -> LearnerSkillState:
    """Create a non-contextual state row with NULL mastery; never calculate mastery."""
    skill = skill_definition(skill_id)
    if skill.assessment_mode == "contextual":
        raise ValueError("contextual skills are not atomic learner mastery targets")
    existing = get_state_for_user(db, verified_uid, skill_id)
    if existing:
        return existing
    state = LearnerSkillState(user_id=verified_uid, skill_id=skill_id)
    db.add(state)
    return state


def create_assessment_event(
    db: Session, *, verified_uid: str, skill_id: str | None, source_type: str,
    evidence_snapshot: str | None, proposed_result: LearnerResult,
    validation_status: AssessmentStatus = "proposed", evidence_modality: str = "text",
    source_event_key: str | None = None, chat_session_id: int | None = None,
    chat_message_id: int | None = None, proposal_confidence: float | None = None,
) -> AssessmentEvent:
    if skill_id is not None:
        skill_definition(skill_id)
    if validation_status == "accepted" and proposed_result in {"unknown", "not_applicable"}:
        raise ValueError("accepted event requires a concrete learner result")
    if source_event_key:
        existing = db.scalar(select(AssessmentEvent).where(AssessmentEvent.user_id == verified_uid, AssessmentEvent.source_event_key == source_event_key))
        if existing:
            return cast(AssessmentEvent, existing)
    event = AssessmentEvent(id=str(uuid4()), user_id=verified_uid, skill_id=skill_id, source_type=source_type,
        evidence_snapshot=evidence_snapshot, proposed_result=proposed_result, validation_status=validation_status,
        evidence_modality=evidence_modality, proposal_confidence=proposal_confidence,
        taxonomy_version=TAXONOMY_VERSION, source_event_key=source_event_key,
        chat_session_id=chat_session_id, chat_message_id=chat_message_id)
    db.add(event)
    # Make a second delivery in the same transaction observe the unique source key.
    if source_event_key:
        db.flush()
    return event


def create_practice_attempt(
    db: Session, *, verified_uid: str, skill_id: str, exercise_type: str,
    source_event_key: str | None = None, **values: object,
) -> PracticeAttempt:
    skill_definition(skill_id)
    if source_event_key:
        existing = db.scalar(select(PracticeAttempt).where(PracticeAttempt.user_id == verified_uid, PracticeAttempt.source_event_key == source_event_key))
        if existing:
            return cast(PracticeAttempt, existing)
    attempt = PracticeAttempt(id=str(uuid4()), user_id=verified_uid, skill_id=skill_id,
        exercise_type=exercise_type, taxonomy_version=TAXONOMY_VERSION,
        source_event_key=source_event_key, **values)
    db.add(attempt)
    if source_event_key:
        db.flush()
    return attempt
