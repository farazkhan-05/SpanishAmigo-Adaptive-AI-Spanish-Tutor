from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import UTC, datetime

from app.curriculum_metadata import SkillDefinition
from app.database import get_db
from app.models import ReviewHistory, ReviewItem
from app.schemas import AdaptiveStateResponse, ReviewResponse, ReviewStartResponse, ReviewSubmission
from app.services.adaptive import _utc, assess_review_submission, get_state_for_user, get_states_for_user, review_rationale, skill_definition, start_due_review, status_for_state
from app.services.auth import get_current_user

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
    except ValueError as error:
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
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=404 if "not found" in str(error) else 409, detail=str(error))
    return {"attempt_id": payload.attempt_id, "event_id": result.event.id, "status": result.event.validation_status,
            # This is the validated outcome stored by the server, not a client-supplied rating.
            "result": result.event.proposed_result,
            "mastery_updated": result.event.validation_status == "accepted"}
