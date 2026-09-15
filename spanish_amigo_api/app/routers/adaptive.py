from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.curriculum_metadata import SkillDefinition
from app.database import get_db
from app.schemas import AdaptiveStateResponse
from app.services.adaptive import get_state_for_user, get_states_for_user, skill_definition, status_for_state
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
