"""Tenant-scoped Phase-4 adaptive storage helpers.

These helpers intentionally store audit inputs without assessing them or mutating
mastery.  Callers must pass the UID obtained from verified Firebase claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
import unicodedata
from typing import Literal, Optional, Sequence, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.curriculum_metadata import SKILLS, TAXONOMY_VERSION, SkillDefinition
from app.models import AssessmentEvent, LearnerSkillState, PracticeAttempt
from app.schemas import AssessmentProposal

AssessmentStatus = Literal["proposed", "accepted", "rejected", "ambiguous", "invalid", "low_confidence"]
LearnerResult = Literal["correct", "incorrect", "partial", "unknown", "not_applicable"]

ASSESSMENT_VERSION = "phase5-v1"
VALIDATOR_VERSION = "phase5-validator-v1"
ASSESSMENT_AUDIT_VERSION = f"{VALIDATOR_VERSION};schema={ASSESSMENT_VERSION}"
MIN_ACCEPTANCE_CONFIDENCE = 0.80
LOW_MASTERY_MAX = 0.35
DEVELOPING_MASTERY_MAX = 0.70


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
    state = LearnerSkillState(user_id=verified_uid, skill_id=skill_id)
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
