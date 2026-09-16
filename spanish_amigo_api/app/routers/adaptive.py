from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import UTC, datetime
import uuid

from app.curriculum_metadata import SkillDefinition
from app.database import get_db
from app.models import ReviewHistory, ReviewItem
from app.schemas import (
    AdaptiveStateResponse,
    ReviewResponse,
    ReviewStartResponse,
    ReviewSubmission,
    TargetedPracticeRecommendation,
    TargetedPracticeStartRequest,
    TargetedPracticeStartResponse,
    TargetedPracticeSubmission,
    TargetedPracticeSubmitResponse,
)
from app.services.adaptive import (
    _utc,
    assess_review_submission,
    assess_targeted_practice_submission,
    get_state_for_user,
    get_states_for_user,
    get_targeted_practice_recommendation,
    review_rationale,
    skill_definition,
    start_due_review,
    start_targeted_practice,
    status_for_state,
)
from app.services.auth import get_current_user
from app.services.telemetry import error_category, record

router = APIRouter(prefix="/adaptive", tags=["Adaptive"])


def _response(skill: SkillDefinition, state) -> AdaptiveStateResponse:
    status = status_for_state(state, skill.skill_id)
    # Contextual skills cannot leak an accidental persisted numeric claim.
    estimate = state.mastery_estimate if state and skill.assessment_mode != "contextual" else None
    confidence = state.estimate_confidence if state and skill.assessment_mode != "contextual" else None
    return AdaptiveStateResponse(skill_id=skill.skill_id, display_name=skill.display_label,
        assessment_mode=skill.assessment_mode, mastery_estimate=estimate,
        estimate_confidence=confidence, accepted_evidence_count=state.accepted_evidence_count if state else 0,
        last_practiced_at=state.last_practiced_at if state else None,
        status=status)


@router.get("/state", response_model=list[AdaptiveStateResponse])
def get_adaptive_state(skill_id: str | None = Query(None, max_length=100), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    verified_uid = current_user.get("uid")
    if not verified_uid:
        raise HTTPException(status_code=401, detail="Authentication failed.")
    if skill_id:
        try:
            skill = skill_definition(skill_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown stable skill ID.")
        return [_response(skill, get_state_for_user(db, verified_uid, skill_id))]
    states = {state.skill_id: state for state in get_states_for_user(db, verified_uid)}
    # Include every taxonomy skill so an empty database honestly renders as unknown.
    from app.curriculum_metadata import SKILLS
    return [_response(skill, states.get(skill.skill_id)) for skill in SKILLS]


def _review_response(db: Session, item: ReviewItem, now: datetime) -> ReviewResponse:
    history = db.scalar(select(ReviewHistory).where(ReviewHistory.review_item_id == item.id).order_by(ReviewHistory.created_at.desc()))
    skill = skill_definition(item.skill_id)
    return ReviewResponse(review_id=item.id, skill_id=item.skill_id, display_name=skill.display_label, due_at=item.due_at,
                          rationale=review_rationale(item, history, now))


@router.get("/reviews/due", response_model=list[ReviewResponse])
def due_reviews(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    uid = current_user.get("uid")
    if not uid: raise HTTPException(status_code=401, detail="Authentication failed.")
    now = datetime.now(UTC)
    items = list(db.scalars(select(ReviewItem).where(ReviewItem.user_id == uid, ReviewItem.due_at <= now).order_by(ReviewItem.due_at, ReviewItem.skill_id)))
    return [_review_response(db, item, now) for item in items]


@router.get("/reviews/next", response_model=ReviewResponse | None)
def next_review(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    uid = current_user.get("uid")
    if not uid: raise HTTPException(status_code=401, detail="Authentication failed.")
    now = datetime.now(UTC)
    item = db.scalar(select(ReviewItem).where(ReviewItem.user_id == uid).order_by(ReviewItem.due_at, ReviewItem.skill_id))
    return _review_response(db, item, now) if item else None


@router.post("/reviews/{review_id}/start", response_model=ReviewStartResponse)
def start_review(review_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    uid = current_user.get("uid")
    if not uid: raise HTTPException(status_code=401, detail="Authentication failed.")
    try:
        attempt = start_due_review(db, verified_uid=uid, review_id=review_id)
        db.commit()
    except Exception as error:
        record(operation_id=str(uuid.uuid4()), operation="review_schedule", success=False,
               review_scheduling_failure="review_start_failed", error_category=error_category(error))
        raise HTTPException(status_code=404 if str(error) == "review not found" else 409, detail=str(error))
    return ReviewStartResponse(attempt_id=attempt.id, exercise_id=attempt.exercise_id or attempt.id, exercise_text=attempt.prompt_snapshot or "")


@router.post("/reviews/{review_id}/submit")
def submit_review(review_id: str, payload: ReviewSubmission, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Run the same Phase-5 assessment/validation then the sole Phase-6 mutation service."""
    uid = current_user.get("uid")
    if not uid: raise HTTPException(status_code=401, detail="Authentication failed.")
    try:
        result = assess_review_submission(db, verified_uid=uid, review_id=review_id, attempt_id=payload.attempt_id, learner_answer=payload.learner_answer)
        db.commit()
    except Exception as error:
        db.rollback()
        record(operation_id=str(uuid.uuid4()), operation="adaptive_update", success=False,
               adaptive_update_failure="review_submission_failed", error_category=error_category(error))
        raise HTTPException(status_code=404 if "not found" in str(error) else 409, detail=str(error))
    return {"attempt_id": payload.attempt_id, "event_id": result.event.id, "status": result.event.validation_status,
            # This is the validated outcome stored by the server, not a client-supplied rating.
            "result": result.event.proposed_result,
            "mastery_updated": result.event.validation_status == "accepted"}


@router.get("/practice/recommendation", response_model=TargetedPracticeRecommendation)
def targeted_practice_recommendation(
    session_id: int | None = Query(None),
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user),
):
    uid = current_user.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication failed.")
    event = get_targeted_practice_recommendation(db, verified_uid=uid, chat_session_id=session_id)
    if event is None:
        return TargetedPracticeRecommendation(available=False)
    if event.skill_id is None:
        return TargetedPracticeRecommendation(available=False)
    skill = skill_definition(event.skill_id)
    return TargetedPracticeRecommendation(
        available=True,
        source_event_id=event.id,
        skill_id=skill.skill_id,
        display_name=skill.display_label,
        reason="A validated chat response needs one more independent practice response.",
    )


@router.post("/practice/start", response_model=TargetedPracticeStartResponse)
def start_targeted_practice_route(
    payload: TargetedPracticeStartRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    uid = current_user.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication failed.")
    try:
        attempt = start_targeted_practice(
            db, verified_uid=uid, source_event_id=payload.source_event_id
        )
        db.commit()
    except Exception as error:
        db.rollback()
        record(operation_id=str(uuid.uuid4()), operation="adaptive_update", success=False,
               adaptive_update_failure="targeted_practice_start_failed", error_category=error_category(error))
        raise HTTPException(status_code=404 if "not found" in str(error) else 409, detail=str(error))
    skill = skill_definition(attempt.skill_id)
    return TargetedPracticeStartResponse(
        attempt_id=attempt.id,
        source_event_id=attempt.source_assessment_event_id or payload.source_event_id,
        skill_id=skill.skill_id,
        display_name=skill.display_label,
        exercise_id=attempt.exercise_id or attempt.id,
        exercise_text=attempt.prompt_snapshot or "",
        status=attempt.outcome,
    )


@router.post("/practice/{attempt_id}/submit", response_model=TargetedPracticeSubmitResponse)
def submit_targeted_practice(
    attempt_id: str,
    payload: TargetedPracticeSubmission,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    uid = current_user.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication failed.")
    try:
        result = assess_targeted_practice_submission(
            db, verified_uid=uid, attempt_id=attempt_id, learner_answer=payload.learner_answer
        )
        due_at = None
        if result.mastery_updated:
            item = db.scalar(select(ReviewItem).where(
                ReviewItem.user_id == uid, ReviewItem.skill_id == result.attempt.skill_id
            ))
            due_at = item.due_at if item else None
        db.commit()
    except Exception as error:
        db.rollback()
        record(operation_id=str(uuid.uuid4()), operation="adaptive_update", success=False,
               adaptive_update_failure="targeted_practice_submission_failed", error_category=error_category(error))
        raise HTTPException(status_code=404 if "not found" in str(error) else 409, detail=str(error))
    skill = skill_definition(result.attempt.skill_id)
    learner_status = (
        "already_completed" if result.already_completed else
        "mastery_updated" if result.mastery_updated else
        "evidence_recorded"
    )
    return TargetedPracticeSubmitResponse(
        attempt_id=result.attempt.id,
        event_id=result.event.id,
        skill_id=skill.skill_id,
        status=result.event.validation_status,
        result=result.event.proposed_result,
        mastery_updated=result.mastery_updated,
        learner_status=learner_status,
        due_at=due_at,
    )
