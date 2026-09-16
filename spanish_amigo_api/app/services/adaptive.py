"""Tenant-scoped Phase-4 adaptive storage helpers.

These helpers intentionally store audit inputs without assessing them or mutating
mastery.  Callers must pass the UID obtained from verified Firebase claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Literal, Optional, Sequence, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fsrs import Card, Rating, Scheduler, State

from app.curriculum_metadata import SKILLS, TAXONOMY_VERSION, SkillDefinition
from app.models import AssessmentEvent, LearnerSkillState, PracticeAttempt, ReviewHistory, ReviewItem, User
from app.schemas import AssessmentProposal

AssessmentStatus = Literal["proposed", "accepted", "rejected", "ambiguous", "invalid", "low_confidence"]
LearnerResult = Literal["correct", "incorrect", "partial", "unknown", "not_applicable"]

ASSESSMENT_VERSION = "phase5-v1"
VALIDATOR_VERSION = "phase5-validator-v1"
ASSESSMENT_AUDIT_VERSION = f"{VALIDATOR_VERSION};schema={ASSESSMENT_VERSION}"
MIN_ACCEPTANCE_CONFIDENCE = 0.80
LOW_MASTERY_MAX = 0.35
DEVELOPING_MASTERY_MAX = 0.70
MASTERY_ALGORITHM_VERSION = "phase6-evidence-step-v1"
FSRS_LIBRARY_VERSION = "6.3.2"
FSRS_SCHEDULER_VERSION = "py-fsrs-defaults-v6"


@dataclass(frozen=True)
class MasteryUpdate:
    estimate: float
    confidence: float
    evidence_weight: float


@dataclass(frozen=True)
class ReviewAssessmentResult:
    event: AssessmentEvent
    state: LearnerSkillState | None
    completed: bool


@dataclass(frozen=True)
class TargetedPracticeAssessmentResult:
    attempt: PracticeAttempt
    event: AssessmentEvent
    state: LearnerSkillState | None
    mastery_updated: bool
    already_completed: bool = False


def review_exercise_text(skill_id: str) -> str:
    """Server-owned, taxonomy-grounded recall prompt; no claim of success on display."""
    skill = skill_definition(skill_id)
    return f"Recall practice for {skill.display_label}: write one Spanish answer that demonstrates {skill.description}. Your turn."


def _is_targeted_practice_source(event: AssessmentEvent) -> bool:
    if event.source_type != "chat_message" or event.validation_status != "accepted":
        return False
    if event.skill_id is None or event.evidence_modality != "text":
        return False
    if event.proposed_result not in {"incorrect", "partial"}:
        return False
    try:
        skill = skill_definition(event.skill_id)
        return skill.category != "vocabulary" and mastery_eligibility(event.skill_id, event.evidence_modality)
    except ValueError:
        return False


def get_targeted_practice_recommendation(db: Session, *, verified_uid: str) -> AssessmentEvent | None:
    """Return the newest eligible chat mistake that has no practice attempt yet."""
    events = db.scalars(select(AssessmentEvent).where(
        AssessmentEvent.user_id == verified_uid,
        AssessmentEvent.source_type == "chat_message",
        AssessmentEvent.validation_status == "accepted",
    ).order_by(AssessmentEvent.created_at.desc(), AssessmentEvent.id.desc()))
    for event in events:
        if not _is_targeted_practice_source(event):
            continue
        prior_attempt = db.scalar(select(PracticeAttempt.id).where(
            PracticeAttempt.user_id == verified_uid,
            PracticeAttempt.source_assessment_event_id == event.id,
        ))
        if prior_attempt is None:
            return event
    return None


def start_targeted_practice(db: Session, *, verified_uid: str, source_event_id: str) -> PracticeAttempt:
    """Create or return one server-owned attempt for one eligible chat event."""
    event = db.scalar(select(AssessmentEvent).where(
        AssessmentEvent.id == source_event_id,
        AssessmentEvent.user_id == verified_uid,
    ).with_for_update())
    if event is None or not _is_targeted_practice_source(event):
        raise ValueError("practice recommendation not found")
    if event.skill_id is None:
        raise ValueError("practice recommendation has no target skill")
    skill_id = event.skill_id
    existing = db.scalar(select(PracticeAttempt).where(
        PracticeAttempt.user_id == verified_uid,
        PracticeAttempt.source_assessment_event_id == event.id,
    ).order_by(PracticeAttempt.created_at.desc()).with_for_update())
    if existing is not None:
        return existing
    try:
        attempt = create_practice_attempt(
            db,
            verified_uid=verified_uid,
            skill_id=skill_id,
            exercise_type="targeted_chat_followup",
            source_assessment_event_id=event.id,
            exercise_id=f"targeted:{event.id}",
            prompt_snapshot=review_exercise_text(skill_id),
            outcome="pending",
            support_level="independent",
            independent_recall=True,
            processing_version="phase5-targeted-practice-v1",
            source_event_key=f"targeted-practice:{event.id}",
        )
        db.flush()
        return attempt
    except IntegrityError:
        # A concurrent start may win either the source-link or deterministic-key
        # unique constraint. Return that committed winner as the idempotent result.
        db.rollback()
        existing = db.scalar(select(PracticeAttempt).where(
            PracticeAttempt.user_id == verified_uid,
            PracticeAttempt.source_assessment_event_id == event.id,
        ).order_by(PracticeAttempt.created_at.desc()))
        if existing is not None:
            return existing
        raise


def assess_targeted_practice_submission(
    db: Session, *, verified_uid: str, attempt_id: str, learner_answer: str,
) -> TargetedPracticeAssessmentResult:
    """Assess a new answer for a server-issued targeted attempt and apply eligible evidence once."""
    attempt = db.scalar(select(PracticeAttempt).where(
        PracticeAttempt.id == attempt_id,
        PracticeAttempt.user_id == verified_uid,
    ).with_for_update())
    if attempt is None or attempt.source_assessment_event_id is None:
        raise ValueError("practice attempt not found")
    source_event = db.scalar(select(AssessmentEvent).where(
        AssessmentEvent.id == attempt.source_assessment_event_id,
        AssessmentEvent.user_id == verified_uid,
    ).with_for_update())
    if source_event is None or not _is_targeted_practice_source(source_event) or source_event.skill_id != attempt.skill_id:
        raise ValueError("practice attempt source is no longer eligible")
    if attempt.assessment_event_id:
        event = db.get(AssessmentEvent, attempt.assessment_event_id)
        if event is None:
            raise RuntimeError("completed practice attempt has no event")
        state = get_state_for_user(db, verified_uid, attempt.skill_id)
        return TargetedPracticeAssessmentResult(attempt, event, state, db.scalar(
            select(ReviewHistory.id).where(ReviewHistory.assessment_event_id == event.id)
        ) is not None, True)
    if attempt.outcome != "pending":
        raise ValueError("practice attempt already completed")

    gate = assessability_gate(learner_answer, prior_messages=(attempt.prompt_snapshot or "Your turn",))
    event_key = f"targeted-practice-submit:{attempt.id}"
    try:
        from app.services.ai import propose_assessment
        proposal, model_version = propose_assessment(learner_answer, db)
        validation = validate_assessment_proposal(
            proposal, learner_turn=learner_answer, gate=gate, evidence_modality="text"
        )
        if validation.status == "accepted" and (
            validation.skill is None or validation.skill.skill_id != attempt.skill_id
        ):
            validation = EvidenceValidation(
                "rejected", "targeted_practice_skill_mismatch", validation.skill,
                validation.normalized_evidence, validation.span_start, validation.span_end,
            )
        event = create_assessment_event(
            db,
            verified_uid=verified_uid,
            skill_id=attempt.skill_id,
            source_type="practice_attempt",
            evidence_snapshot=proposal.evidence,
            normalized_evidence=validation.normalized_evidence,
            evidence_span_start=validation.span_start,
            evidence_span_end=validation.span_end,
            evidence_modality="text",
            proposed_result=proposal.result,
            validation_status=validation.status,
            proposal_confidence=proposal.confidence,
            error_type=proposal.error_type,
            severity=proposal.severity,
            correction=proposal.correction,
            misconception_id=proposal.misconception_id,
            rejection_reason=validation.reason,
            validator_version=ASSESSMENT_AUDIT_VERSION,
            assessment_model_version=model_version,
            source_event_key=event_key,
        )
    except Exception:
        event = create_assessment_event(
            db,
            verified_uid=verified_uid,
            skill_id=attempt.skill_id,
            source_type="practice_attempt",
            evidence_snapshot=learner_answer,
            proposed_result="not_applicable",
            validation_status="invalid",
            evidence_modality="text",
            rejection_reason="practice_assessment_provider_or_schema_failure",
            validator_version=ASSESSMENT_AUDIT_VERSION,
            source_event_key=event_key,
        )
    attempt.learner_response_snapshot = learner_answer
    attempt.assessment_event_id = event.id
    attempt.outcome = event.proposed_result if event.validation_status == "accepted" else "invalid"
    if event.validation_status != "accepted":
        db.flush()
        return TargetedPracticeAssessmentResult(attempt, event, None, False)
    state = process_accepted_evidence(
        db, verified_uid=verified_uid, event_id=event.id, practice_attempt_id=attempt.id
    )
    db.flush()
    return TargetedPracticeAssessmentResult(attempt, event, state, True)


def start_due_review(db: Session, *, verified_uid: str, review_id: str, now: datetime | None = None) -> PracticeAttempt:
    now = _utc(now or datetime.now(UTC))
    item = db.scalar(select(ReviewItem).where(ReviewItem.id == review_id, ReviewItem.user_id == verified_uid).with_for_update())
    if item is None: raise ValueError("review not found")
    if _utc(item.due_at) > now: raise ValueError("review is not due")
    skill = skill_definition(item.skill_id)
    if not mastery_eligibility(item.skill_id, "text") or skill.category == "vocabulary":
        raise ValueError("review skill is not text-mastery eligible")
    # Only one open server-issued exercise per due card; a retry resumes it.
    attempt = db.scalar(select(PracticeAttempt).where(PracticeAttempt.user_id == verified_uid, PracticeAttempt.review_item_id == item.id, PracticeAttempt.outcome == "pending").order_by(PracticeAttempt.created_at.desc()))
    if attempt is not None: return attempt
    exercise_id = f"review:{item.id}:{uuid4()}"
    attempt = create_practice_attempt(db, verified_uid=verified_uid, skill_id=item.skill_id,
        exercise_type="fsrs_review", source_event_key=f"review-start:{item.id}:{exercise_id}", review_item_id=item.id,
        exercise_id=exercise_id, prompt_snapshot=review_exercise_text(item.skill_id), outcome="pending",
        support_level="independent", independent_recall=True, processing_version="phase6-review-exercise-v1")
    db.flush()
    return attempt


def assess_review_submission(db: Session, *, verified_uid: str, review_id: str, attempt_id: str,
                             learner_answer: str) -> ReviewAssessmentResult:
    """Phase-5 proposal/validation reused for a server-issued review exercise."""
    item = db.scalar(select(ReviewItem).where(ReviewItem.id == review_id, ReviewItem.user_id == verified_uid).with_for_update())
    if item is None: raise ValueError("review not found")
    attempt = db.scalar(select(PracticeAttempt).where(PracticeAttempt.id == attempt_id, PracticeAttempt.user_id == verified_uid).with_for_update())
    if attempt is None or attempt.review_item_id != item.id or attempt.skill_id != item.skill_id: raise ValueError("review attempt not found")
    if attempt.assessment_event_id:
        event = db.get(AssessmentEvent, attempt.assessment_event_id)
        if event is None: raise RuntimeError("completed review attempt has no event")
        return ReviewAssessmentResult(event, get_state_for_user(db, verified_uid, item.skill_id), True)
    if attempt.outcome != "pending": raise ValueError("review attempt already completed")
    gate = assessability_gate(learner_answer, prior_messages=(attempt.prompt_snapshot or "Your turn",))
    event_key = f"review-submit:{attempt.id}"
    try:
        # Local import prevents the existing ai -> adaptive dependency from becoming circular.
        from app.services.ai import propose_assessment
        proposal, model_version = propose_assessment(learner_answer, db)
        validation = validate_assessment_proposal(proposal, learner_turn=learner_answer, gate=gate, evidence_modality="text")
        if validation.status == "accepted" and (validation.skill is None or validation.skill.skill_id != item.skill_id):
            validation = EvidenceValidation("rejected", "review_skill_mismatch", validation.skill, validation.normalized_evidence, validation.span_start, validation.span_end)
        event = create_assessment_event(db, verified_uid=verified_uid, skill_id=validation.skill.skill_id if validation.skill else None,
            source_type="practice_attempt", evidence_snapshot=proposal.evidence, normalized_evidence=validation.normalized_evidence,
            evidence_span_start=validation.span_start, evidence_span_end=validation.span_end, evidence_modality="text",
            proposed_result=proposal.result, validation_status=validation.status, proposal_confidence=proposal.confidence,
            error_type=proposal.error_type, severity=proposal.severity, correction=proposal.correction,
            misconception_id=proposal.misconception_id, rejection_reason=validation.reason,
            validator_version=ASSESSMENT_AUDIT_VERSION, assessment_model_version=model_version, source_event_key=event_key)
    except Exception as error:
        # Provider/schema failure is durable audit evidence, never fabricated correctness.
        event = create_assessment_event(db, verified_uid=verified_uid, skill_id=item.skill_id, source_type="practice_attempt",
            evidence_snapshot=learner_answer, proposed_result="not_applicable", validation_status="invalid", evidence_modality="text",
            rejection_reason="review_assessment_provider_or_schema_failure", validator_version=ASSESSMENT_AUDIT_VERSION,
            source_event_key=event_key)
    attempt.learner_response_snapshot = learner_answer
    attempt.assessment_event_id = event.id
    attempt.outcome = event.proposed_result if event.validation_status == "accepted" else "invalid"
    if event.validation_status != "accepted":
        db.flush()
        return ReviewAssessmentResult(event, None, True)
    state = process_accepted_evidence(db, verified_uid=verified_uid, event_id=event.id, practice_attempt_id=attempt.id)
    db.flush()
    return ReviewAssessmentResult(event, state, True)


def update_mastery(*, previous: float | None, accepted_count: int, result: LearnerResult,
                   support_level: str, independent_recall: bool, validation_confidence: float | None) -> MasteryUpdate:
    """Versioned, bounded evidence-step estimate; it is not a calibrated statistical model.

    First evidence starts at 0.50, then a signed step moves toward 1 for correct or
    0 for incorrect. Base step is .12 independent / .05 assisted, partial is half,
    confidence only ranges from .80 to 1.0, and repeated evidence decays by 1/(1+n/8).
    Confidence is evidence strength: independent .20, assisted .08, capped at .90.
    """
    if result not in {"correct", "incorrect", "partial"}:
        raise ValueError("mastery update requires a concrete result")
    assisted = support_level in {"hinted", "guided"} or not independent_recall
    base = 0.05 if assisted else 0.12
    if result == "partial": base *= 0.5
    confidence_factor = max(0.8, min(1.0, validation_confidence or MIN_ACCEPTANCE_CONFIDENCE))
    step = base * confidence_factor / (1 + accepted_count / 8)
    current = 0.5 if previous is None else previous
    if result == "correct":
        estimate = current + step * (1 - current)
    else:
        estimate = current - step * current
    prior_strength = 0.0 if previous is None else min(0.90, accepted_count * 0.20)
    strength = 0.08 if assisted else 0.20
    return MasteryUpdate(round(max(0.0, min(1.0, estimate)), 6), round(min(0.90, prior_strength + strength * confidence_factor), 6), step)


def fsrs_rating_for_event(*, result: LearnerResult, support_level: str, independent_recall: bool) -> Rating:
    """Application-owned mapping. Easy is intentionally never emitted automatically."""
    if result == "incorrect" and independent_recall and support_level == "independent":
        return Rating.Again
    if result == "correct" and independent_recall and support_level == "independent":
        return Rating.Good
    # Partial recall is not a Good outcome even when the response did not use an
    # explicit hint.  It is a valid concrete assessment result, so schedule it
    # conservatively rather than letting the otherwise accepted submission abort.
    if result == "partial" and support_level in {"independent", "hinted", "guided"}:
        return Rating.Hard
    if result == "correct" and support_level in {"hinted", "guided"}:
        return Rating.Hard
    raise ValueError("event does not have a defensible FSRS rating")


def _card_dict(card: Card) -> dict[str, object]:
    return {"state": card.state.value, "step": card.step, "stability": card.stability, "difficulty": card.difficulty,
            "due": card.due.astimezone(UTC).isoformat(), "last_review": card.last_review.astimezone(UTC).isoformat() if card.last_review else None}


def _utc(value: datetime) -> datetime:
    """PostgreSQL persists aware UTC; this also keeps SQLite test adapters honest."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _card_from_item(item: ReviewItem | None, now: datetime) -> Card:
    if item is None:
        return Card(state=State.Learning, due=now)
    return Card(state=State(item.card_state), step=item.card_step, stability=item.stability, difficulty=item.difficulty,
                due=_utc(item.due_at), last_review=_utc(item.last_review_at) if item.last_review_at else None)


def process_accepted_evidence(db: Session, *, verified_uid: str, event_id: str, practice_attempt_id: str | None = None,
                              now: datetime | None = None) -> LearnerSkillState:
    """Single transactional authoritative event-to-state transition; retries return existing history."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    # Serialize first-card/state creation for this tenant.  Row locks on only
    # state/card rows cannot protect the initial transition because neither row
    # exists yet; the verified owner row is always present through the event FK.
    owner = db.scalar(select(User).where(User.id == verified_uid).with_for_update())
    if owner is None:
        raise ValueError("authenticated user not found")
    event = db.scalar(select(AssessmentEvent).where(AssessmentEvent.id == event_id, AssessmentEvent.user_id == verified_uid).with_for_update())
    if event is None: raise ValueError("event not found for authenticated user")
    if event.source_type != "practice_attempt":
        raise ValueError("chat evidence cannot mutate mastery")
    if event.validation_status != "accepted" or event.skill_id is None or not mastery_eligibility(event.skill_id, event.evidence_modality):
        raise ValueError("event is not mastery eligible")
    if event.proposed_result not in {"correct", "incorrect", "partial"}: raise ValueError("event result is not concrete")
    attempt = None
    if practice_attempt_id:
        attempt = db.scalar(select(PracticeAttempt).where(PracticeAttempt.id == practice_attempt_id, PracticeAttempt.user_id == verified_uid).with_for_update())
        if attempt is None or attempt.skill_id != event.skill_id or attempt.assessment_event_id != event.id: raise ValueError("attempt does not own this event")
    if db.scalar(select(ReviewHistory).where(ReviewHistory.assessment_event_id == event.id)):
        state = get_state_for_user(db, verified_uid, event.skill_id)
        if state is None: raise RuntimeError("idempotency history without state")
        return state
    if attempt is None or attempt.support_level == "exposure" or attempt.outcome not in {"correct", "incorrect", "partial"}:
        raise ValueError("eligible accepted practice attempt required")
    if attempt.source_assessment_event_id:
        source_event = db.scalar(select(AssessmentEvent).where(
            AssessmentEvent.id == attempt.source_assessment_event_id,
            AssessmentEvent.user_id == verified_uid,
        ).with_for_update())
        if source_event is None or not _is_targeted_practice_source(source_event) or source_event.skill_id != event.skill_id:
            raise ValueError("practice attempt source is not eligible")
    skill = skill_definition(event.skill_id)
    if skill.assessment_mode != "text" or skill.category == "vocabulary": raise ValueError("non-atomic skill")
    state = create_unknown_state(db, verified_uid, event.skill_id)
    update = update_mastery(previous=state.mastery_estimate, accepted_count=state.accepted_evidence_count, result=cast(LearnerResult, event.proposed_result), support_level=attempt.support_level, independent_recall=attempt.independent_recall, validation_confidence=event.proposal_confidence)
    rating = fsrs_rating_for_event(result=cast(LearnerResult, event.proposed_result), support_level=attempt.support_level, independent_recall=attempt.independent_recall)
    item = db.scalar(select(ReviewItem).where(ReviewItem.user_id == verified_uid, ReviewItem.skill_id == event.skill_id).with_for_update())
    before = _card_from_item(item, now)
    after, _log = Scheduler(enable_fuzzing=False).review_card(before, rating, review_datetime=now)
    if item is None:
        item = ReviewItem(id=str(uuid4()), user_id=verified_uid, skill_id=event.skill_id, card_state=after.state.value, card_step=after.step, stability=after.stability, difficulty=after.difficulty, due_at=after.due.astimezone(UTC), last_review_at=after.last_review.astimezone(UTC) if after.last_review else None, fsrs_version=FSRS_LIBRARY_VERSION, scheduler_version=FSRS_SCHEDULER_VERSION, created_at=now, updated_at=now)
        db.add(item)
        db.flush()
    else:
        item.card_state, item.card_step, item.stability, item.difficulty, item.due_at, item.last_review_at = after.state.value, after.step, after.stability, after.difficulty, after.due.astimezone(UTC), after.last_review.astimezone(UTC) if after.last_review else None
        item.updated_at = now
    state.mastery_estimate, state.estimate_confidence = update.estimate, update.confidence
    state.accepted_evidence_count += 1
    if attempt.independent_recall: state.independent_attempt_count += 1
    else: state.assisted_attempt_count += 1
    state.last_evidence_at = now.replace(tzinfo=None); state.last_practiced_at = now.replace(tzinfo=None); state.state_version += 1
    db.add(ReviewHistory(id=str(uuid4()), user_id=verified_uid, review_item_id=item.id, skill_id=event.skill_id, practice_attempt_id=attempt.id, assessment_event_id=event.id, rating=rating.value, previous_card=json.dumps(_card_dict(before), sort_keys=True), new_card=json.dumps(_card_dict(after), sort_keys=True), due_at=after.due.astimezone(UTC), mastery_algorithm_version=MASTERY_ALGORITHM_VERSION, fsrs_version=FSRS_LIBRARY_VERSION, created_at=now))
    db.flush()
    return state


def review_rationale(item: ReviewItem, history: ReviewHistory | None, now: datetime) -> str:
    if _utc(item.due_at) <= _utc(now): return "review is due"
    if history and history.rating == Rating.Again.value: return "previous independent recall failed"
    return "skill needs additional validated evidence"


class UserIntent(str, Enum):
    PRODUCTION = "production"
    QUESTION = "question"
    TRANSLATION_REQUEST = "translation_request"
    UI_COMMAND = "ui_command"
    GREETING = "greeting"
    META = "meta"
    UNKNOWN = "unknown"


class PedagogicalAction(str, Enum):
    ANSWER_NORMALLY = "ANSWER_NORMALLY"
    EXPLAIN_AND_GUIDE = "EXPLAIN_AND_GUIDE"
    TARGETED_PRACTICE = "TARGETED_PRACTICE"
    TARGETED_PRACTICE_WITH_HINT = "TARGETED_PRACTICE_WITH_HINT"
    COLLECT_MORE_EVIDENCE = "COLLECT_MORE_EVIDENCE"
    CONTEXTUAL_TRANSFER = "CONTEXTUAL_TRANSFER"
    NO_ADAPTIVE_ACTION = "NO_ADAPTIVE_ACTION"


@dataclass(frozen=True)
class AssessabilityDecision:
    assessable: bool
    intent: UserIntent
    reason: str


@dataclass(frozen=True)
class EvidenceValidation:
    status: AssessmentStatus
    reason: str | None
    skill: SkillDefinition | None
    normalized_evidence: str | None
    span_start: int | None = None
    span_end: int | None = None


@dataclass(frozen=True)
class PolicyInput:
    assessability: AssessabilityDecision
    validation: EvidenceValidation | None
    result: LearnerResult | None
    mastery_estimate: float | None
    accepted_event_count: int
    assessment_mode: str | None


_THEME_PATTERNS = (
    "dark mode", "light mode", "dark theme", "light theme", "toggle theme",
    "change theme", "switch theme", "too bright", "too dark", "eyes hurt",
)
_GREETING_ONLY = {"hola", "hi", "hello", "thanks", "gracias", "buenos dias", "buenos d\u00edas", "buenas tardes", "buenas noches"}
_REQUEST_PREFIXES = (
    "explain ", "what does ", "what is ", "why ", "how do ", "how can ",
    "translate ", "can you ", "could you ", "please explain", "define ",
    "\u00bfpor qu\u00e9", "por qu\u00e9", "\u00bfqu\u00e9 significa", "qu\u00e9 significa", "\u00bfc\u00f3mo se dice",
)
_SPANISH_PRODUCTION_MARKERS = {
    "yo", "t\u00fa", "usted", "quiero", "quiere", "tengo", "tiene", "soy", "estoy",
    "es", "est\u00e1", "un", "una", "el", "la", "por", "favor", "caf\u00e9", "agua",
    "buenos", "buenas", "hasta", "luego", "necesito", "d\u00f3nde", "perd\u00f3n",
}


def _compact_for_intent(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().strip().rstrip("?!.,;:").split())


def assessability_gate(message: str, *, guardrail_blocked: bool = False, prior_messages: Sequence[str] = ()) -> AssessabilityDecision:
    """Conservative deterministic gate; Spanish detection alone is never sufficient."""
    compact = _compact_for_intent(message)
    if guardrail_blocked:
        return AssessabilityDecision(False, UserIntent.META, "guardrail_blocked")
    if not compact or len(compact) < 2:
        return AssessabilityDecision(False, UserIntent.UNKNOWN, "empty_or_noise")
    if any(pattern in compact for pattern in _THEME_PATTERNS):
        return AssessabilityDecision(False, UserIntent.UI_COMMAND, "ui_command")
    if compact in _GREETING_ONLY:
        return AssessabilityDecision(False, UserIntent.GREETING, "greeting_only")
    if compact.startswith(_REQUEST_PREFIXES) or message.strip().endswith("?"):
        intent = UserIntent.TRANSLATION_REQUEST if "translate" in compact or "se dice" in compact else UserIntent.QUESTION
        return AssessabilityDecision(False, intent, "explicit_information_request")
    if any(marker in compact for marker in ("my answer:", "mi respuesta:", "i think the answer", "perd\u00f3n", "correction:")):
        return AssessabilityDecision(True, UserIntent.PRODUCTION, "explicit_answer_or_self_correction")
    tokens = set(re.findall(r"[^\W\d_]+", compact, flags=re.UNICODE))
    context_is_exercise = any(re.search(r"\b(answer|translate into spanish|your turn|responde|completa)\b", item.casefold()) for item in prior_messages[-2:])
    if context_is_exercise and tokens:
        return AssessabilityDecision(True, UserIntent.PRODUCTION, "response_to_exercise_context")
    if len(tokens) >= 2 and tokens & _SPANISH_PRODUCTION_MARKERS:
        return AssessabilityDecision(True, UserIntent.PRODUCTION, "independent_spanish_production")
    return AssessabilityDecision(False, UserIntent.UNKNOWN, "no_atomic_learner_production")


def normalize_evidence(text: str) -> str:
    """NFC + casefold + safe separator folding; accents and lexical tokens remain."""
    normalized = unicodedata.normalize("NFC", text).casefold().strip()
    normalized = re.sub(r"[\s\u00a1!\u00bf?,.;:]+", " ", normalized)
    return " ".join(normalized.split())


def _ground_evidence(learner_turn: str, evidence: str) -> tuple[bool, str, int | None, int | None]:
    exact_match = re.search(rf"(?<!\w){re.escape(evidence)}(?!\w)", learner_turn)
    normalized = normalize_evidence(evidence)
    if exact_match:
        return True, normalized, exact_match.start(), exact_match.end()
    normalized_turn = normalize_evidence(learner_turn)
    if normalized and f" {normalized} " in f" {normalized_turn} ":
        return True, normalized, None, None
    return False, normalized, None, None


def validate_assessment_proposal(
    proposal: AssessmentProposal,
    *,
    learner_turn: str,
    gate: AssessabilityDecision,
    evidence_modality: str = "text",
) -> EvidenceValidation:
    """Validate an untrusted model proposal without changing learner state."""
    if not gate.assessable or not proposal.assessable:
        return EvidenceValidation("rejected", "turn_not_assessable", None, None)
    try:
        skill = skill_definition(proposal.skill_id)
    except ValueError:
        return EvidenceValidation("invalid", "unknown_skill", None, normalize_evidence(proposal.evidence))
    if evidence_modality != "text":
        return EvidenceValidation("invalid", "unsupported_evidence_modality", skill, normalize_evidence(proposal.evidence))
    if skill.assessment_mode == "speech_required":
        return EvidenceValidation("rejected", "speech_required_skill_from_text", skill, normalize_evidence(proposal.evidence))
    if skill.assessment_mode == "contextual":
        return EvidenceValidation("rejected", "contextual_skill_not_atomic", skill, normalize_evidence(proposal.evidence))
    if skill.category == "vocabulary":
        return EvidenceValidation("rejected", "broad_vocabulary_domain_overclaim", skill, normalize_evidence(proposal.evidence))
    grounded, normalized, start, end = _ground_evidence(learner_turn, proposal.evidence)
    if not grounded:
        return EvidenceValidation("invalid", "unsupported_evidence", skill, normalized)
    if proposal.result in {"unknown", "not_applicable"}:
        return EvidenceValidation("ambiguous", "non_concrete_result", skill, normalized, start, end)
    if proposal.confidence < MIN_ACCEPTANCE_CONFIDENCE:
        return EvidenceValidation("low_confidence", "below_acceptance_threshold", skill, normalized, start, end)
    return EvidenceValidation("accepted", None, skill, normalized, start, end)


def select_pedagogical_action(inputs: PolicyInput) -> PedagogicalAction:
    """Pure application-owned policy. Unknown mastery remains None, never a midpoint."""
    if inputs.assessability.intent in {UserIntent.QUESTION, UserIntent.TRANSLATION_REQUEST}:
        return PedagogicalAction.ANSWER_NORMALLY
    if inputs.assessability.intent == UserIntent.UI_COMMAND or not inputs.assessability.assessable:
        return PedagogicalAction.NO_ADAPTIVE_ACTION
    validation = inputs.validation
    if inputs.assessment_mode == "contextual":
        return PedagogicalAction.CONTEXTUAL_TRANSFER
    if validation is None or validation.status != "accepted":
        return PedagogicalAction.COLLECT_MORE_EVIDENCE
    if inputs.result in {"incorrect", "partial"}:
        if inputs.mastery_estimate is not None and inputs.mastery_estimate <= LOW_MASTERY_MAX:
            return PedagogicalAction.TARGETED_PRACTICE_WITH_HINT
        return PedagogicalAction.EXPLAIN_AND_GUIDE
    if inputs.result == "correct":
        if inputs.mastery_estimate is None:
            return PedagogicalAction.COLLECT_MORE_EVIDENCE
        if inputs.mastery_estimate <= DEVELOPING_MASTERY_MAX:
            return PedagogicalAction.TARGETED_PRACTICE
        return PedagogicalAction.ANSWER_NORMALLY
    return PedagogicalAction.COLLECT_MORE_EVIDENCE


def source_turn_key(session_id: int | None, messages: Sequence[str]) -> str:
    material = "\x1f".join(messages).encode("utf-8")
    return f"chat:{session_id or 'none'}:{hashlib.sha256(material).hexdigest()}"


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
    state = LearnerSkillState(user_id=verified_uid, skill_id=skill_id, accepted_evidence_count=0,
                              independent_attempt_count=0, assisted_attempt_count=0, state_version=1)
    db.add(state)
    return state


def create_assessment_event(
    db: Session, *, verified_uid: str, skill_id: str | None, source_type: str,
    evidence_snapshot: str | None, proposed_result: LearnerResult,
    validation_status: AssessmentStatus = "proposed", evidence_modality: str = "text",
    source_event_key: str | None = None, chat_session_id: int | None = None,
    chat_message_id: int | None = None, proposal_confidence: float | None = None,
    normalized_evidence: str | None = None, evidence_span_start: int | None = None,
    evidence_span_end: int | None = None, error_type: str | None = None,
    severity: int | None = None, correction: str | None = None,
    misconception_id: str | None = None, rejection_reason: str | None = None,
    validator_version: str | None = None, assessment_model_version: str | None = None,
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
        normalized_evidence=normalized_evidence, evidence_span_start=evidence_span_start,
        evidence_span_end=evidence_span_end, error_type=error_type, severity=severity,
        correction=correction, misconception_id=misconception_id,
        rejection_reason=rejection_reason, validator_version=validator_version,
        assessment_model_version=assessment_model_version,
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
