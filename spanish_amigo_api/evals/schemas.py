"""Strict schemas for repository-owned evaluation data (no model-generated labels)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


class CaseValidationError(ValueError):
    pass


ALLOWED_BEHAVIORS = {"allowed", "blocked"}


@dataclass(frozen=True)
class GoldenCase:
    id: str
    category: str
    user_input: str
    expected_behavior: str
    assessable_production: bool
    expected_relevant_lesson_ids: tuple[int, ...] = ()
    expected_relevant_slide_ids: tuple[str, ...] = ()
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GoldenCase":
        required = {"id", "category", "user_input", "expected_behavior", "assessable_production", "notes"}
        missing = required - raw.keys()
        if missing:
            raise CaseValidationError(f"missing required fields: {sorted(missing)}")
        unknown = set(raw) - required - {"expected_relevant_lesson_ids", "expected_relevant_slide_ids"}
        if unknown:
            raise CaseValidationError(f"unknown fields: {sorted(unknown)}")
        if not isinstance(raw["id"], str) or not raw["id"].strip():
            raise CaseValidationError("id must be a non-empty string")
        if not isinstance(raw["category"], str) or not raw["category"].strip():
            raise CaseValidationError("category must be a non-empty string")
        if not isinstance(raw["user_input"], str):
            raise CaseValidationError("user_input must be a string")
        if raw["expected_behavior"] not in ALLOWED_BEHAVIORS:
            raise CaseValidationError("expected_behavior must be 'allowed' or 'blocked'")
        if not isinstance(raw["assessable_production"], bool):
            raise CaseValidationError("assessable_production must be a boolean")
        lesson_ids = raw.get("expected_relevant_lesson_ids", [])
        slide_ids = raw.get("expected_relevant_slide_ids", [])
        if not isinstance(lesson_ids, list) or not all(isinstance(item, int) and item > 0 for item in lesson_ids):
            raise CaseValidationError("expected_relevant_lesson_ids must contain positive integers")
        if not isinstance(slide_ids, list) or not all(isinstance(item, str) and item.startswith("L") for item in slide_ids):
            raise CaseValidationError("expected_relevant_slide_ids must contain canonical L<lesson>-S<slide> strings")
        if not isinstance(raw["notes"], str) or not raw["notes"].strip():
            raise CaseValidationError("notes must be a non-empty string")
        return cls(raw["id"], raw["category"], raw["user_input"], raw["expected_behavior"], raw["assessable_production"], tuple(lesson_ids), tuple(slide_ids), raw["notes"])


@dataclass(frozen=True)
class Phase5Case:
    id: str
    category: str
    user_input: str
    expected_assessable: bool
    guardrail_blocked: bool
    proposal: dict[str, Any] | None
    expected_validation_status: str | None
    expected_action: str
    notes: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Phase5Case":
        required = {"id", "category", "user_input", "expected_assessable", "guardrail_blocked", "proposal", "expected_validation_status", "expected_action", "notes"}
        if set(raw) != required:
            raise CaseValidationError(f"phase5 fields must be exactly {sorted(required)}")
        if not isinstance(raw["id"], str) or not raw["id"] or not isinstance(raw["category"], str) or not raw["category"]:
            raise CaseValidationError("id and category must be non-empty strings")
        if not isinstance(raw["user_input"], str) or not isinstance(raw["expected_assessable"], bool) or not isinstance(raw["guardrail_blocked"], bool):
            raise CaseValidationError("invalid phase5 input/boolean fields")
        if raw["proposal"] is not None and not isinstance(raw["proposal"], dict):
            raise CaseValidationError("proposal must be an object or null")
        allowed_statuses = {None, "accepted", "rejected", "ambiguous", "invalid", "low_confidence"}
        if raw["expected_validation_status"] not in allowed_statuses:
            raise CaseValidationError("invalid expected validation status")
        if not isinstance(raw["expected_action"], str) or not isinstance(raw["notes"], str) or not raw["notes"]:
            raise CaseValidationError("action and notes must be non-empty strings")
        return cls(**raw)


@dataclass(frozen=True)
class Phase7Case:
    """Human-authored deterministic safety/state scenario; never model-generated."""
    id: str
    category: str
    scenario: str
    expected: dict[str, Any]
    notes: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Phase7Case":
        required = {"id", "category", "scenario", "expected", "notes"}
        if set(raw) != required:
            raise CaseValidationError(f"phase7 fields must be exactly {sorted(required)}")
        if not all(isinstance(raw[name], str) and raw[name] for name in ("id", "category", "scenario", "notes")):
            raise CaseValidationError("id, category, scenario, and notes must be non-empty strings")
        if not isinstance(raw["expected"], dict) or not raw["expected"]:
            raise CaseValidationError("expected must be a non-empty object")
        return cls(**raw)


RETRIEVAL_CATEGORIES = {
    "direct_vocab",
    "grammar_question",
    "learner_error",
    "paraphrase",
    "natural_conversational",
    "english_query",
    "spanish_production",
    "short_ambiguous",
    "cross_lesson",
    "near_neighbour",
    "hard_distractor",
    "multi_relevant",
    "out_of_scope_negative",
}


@dataclass(frozen=True)
class RetrievalBenchmarkCase:
    """Source-grounded curriculum retrieval evaluation case with verified gold slide IDs."""
    id: str
    query: str
    category: str
    primary_lesson_id: int | None
    expected_relevant_slide_ids: tuple[str, ...]
    expected_relevant_lesson_ids: tuple[int, ...]
    expected_relevant_skill_ids: tuple[str, ...]
    notes: str

    @property
    def is_negative(self) -> bool:
        """Returns True if this is an out-of-scope negative case expecting zero retrieval."""
        return len(self.expected_relevant_slide_ids) == 0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RetrievalBenchmarkCase":
        required = {
            "id",
            "query",
            "category",
            "primary_lesson_id",
            "expected_relevant_slide_ids",
            "expected_relevant_lesson_ids",
            "expected_relevant_skill_ids",
            "notes",
        }
        if set(raw) != required:
            missing = required - set(raw)
            unknown = set(raw) - required
            msg_parts = []
            if missing:
                msg_parts.append(f"missing required fields: {sorted(missing)}")
            if unknown:
                msg_parts.append(f"unknown fields: {sorted(unknown)}")
            raise CaseValidationError("; ".join(msg_parts))
        if not isinstance(raw["id"], str) or not raw["id"].strip():
            raise CaseValidationError("id must be a non-empty string")
        if not isinstance(raw["query"], str) or not raw["query"].strip():
            raise CaseValidationError("query must be a non-empty string")
        if not isinstance(raw["category"], str) or raw["category"] not in RETRIEVAL_CATEGORIES:
            raise CaseValidationError(f"category must be one of {sorted(RETRIEVAL_CATEGORIES)}")

        slide_ids = raw["expected_relevant_slide_ids"]
        if not isinstance(slide_ids, list):
            raise CaseValidationError("expected_relevant_slide_ids must be a list")
        if len(slide_ids) != len(set(slide_ids)):
            raise CaseValidationError("expected_relevant_slide_ids must not contain duplicate slide IDs")

        lesson_ids = raw["expected_relevant_lesson_ids"]
        if not isinstance(lesson_ids, list):
            raise CaseValidationError("expected_relevant_lesson_ids must be a list")

        skill_ids = raw["expected_relevant_skill_ids"]
        if not isinstance(skill_ids, list):
            raise CaseValidationError("expected_relevant_skill_ids must be a list")

        if not isinstance(raw["notes"], str) or not raw["notes"].strip():
            raise CaseValidationError("notes must be a non-empty string")

        # Negative / out-of-scope cases
        if not slide_ids:
            if raw["primary_lesson_id"] is not None:
                raise CaseValidationError("primary_lesson_id must be None for out-of-scope negative cases")
            if lesson_ids:
                raise CaseValidationError("expected_relevant_lesson_ids must be empty for negative cases")
            if skill_ids:
                raise CaseValidationError("expected_relevant_skill_ids must be empty for negative cases")
            if raw["category"] != "out_of_scope_negative":
                raise CaseValidationError("negative cases must have category 'out_of_scope_negative'")
        else:
            # Positive retrieval cases
            if not isinstance(raw["primary_lesson_id"], int) or not (1 <= raw["primary_lesson_id"] <= 5):
                raise CaseValidationError("primary_lesson_id must be an integer between 1 and 5 for positive cases")
            if raw["category"] == "out_of_scope_negative":
                raise CaseValidationError("positive retrieval cases cannot have category 'out_of_scope_negative'")
            for sid in slide_ids:
                if not isinstance(sid, str) or not sid.startswith("L") or "-S" not in sid:
                    raise CaseValidationError(f"invalid slide ID format: {sid}")
            if not lesson_ids or not all(isinstance(x, int) and 1 <= x <= 5 for x in lesson_ids):
                raise CaseValidationError("expected_relevant_lesson_ids must be a non-empty list of integers (1..5)")
            if not skill_ids or not all(isinstance(x, str) and x.strip() for x in skill_ids):
                raise CaseValidationError("expected_relevant_skill_ids must be a non-empty list of strings")

        return cls(
            raw["id"],
            raw["query"],
            raw["category"],
            raw["primary_lesson_id"],
            tuple(slide_ids),
            tuple(lesson_ids),
            tuple(skill_ids),
            raw["notes"],
        )


LIVE_EVAL_CATEGORIES = {
    "correct_spanish",
    "verb_conjugation_errors",
    "ser_estar_confusion",
    "gender_agreement_errors",
    "tener_querer_confusion",
    "self_correction",
    "translation_requests",
    "grammar_explanation_requests",
    "short_production",
    "ambiguous_input",
    "english_question_about_spanish",
    "off_topic",
    "prompt_injection",
    "jailbreak_attempt",
    "mastery_gaming",
    "modality_violations",
    "mixed_language",
    "false_friends",
}


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None

    @classmethod
    def from_metadata(cls, metadata: Any) -> "TokenUsage":
        if isinstance(metadata, dict):
            inp = metadata.get("input_tokens")
            if inp is None:
                inp = metadata.get("prompt_token_count")
            out = metadata.get("output_tokens")
            if out is None:
                out = metadata.get("candidates_token_count")
            tot = metadata.get("total_tokens")
            return cls(
                input_tokens=int(inp) if isinstance(inp, int) else None,
                output_tokens=int(out) if isinstance(out, int) else None,
                total_tokens=int(tot) if isinstance(tot, int) else None,
            )
        return cls(None, None, None)


class TutorJudgeEvaluation(BaseModel):
    curriculum_groundedness: int = Field(ge=1, le=5, description="1-5 score: is Lumi's response grounded in curriculum rules")
    factual_correctness: int = Field(ge=1, le=5, description="1-5 score: linguistic accuracy of Spanish explanations and translations")
    correction_quality: int = Field(ge=1, le=5, description="1-5 score: gentle, instructive error corrections")
    pedagogical_appropriateness: int = Field(ge=1, le=5, description="1-5 score: effective tutoring tone and encouragement")
    learner_level_appropriateness: int = Field(ge=1, le=5, description="1-5 score: appropriate for A1 beginner")
    clarity: int = Field(ge=1, le=5, description="1-5 score: clear, concise text without cognitive overload")
    unnecessary_over_correction: int = Field(ge=1, le=5, description="1-5 score: 5=no unnecessary over-correction, 1=excessive nitpicking")
    response_relevance: int = Field(ge=1, le=5, description="1-5 score: directly answers learner query")
    rationale: str = Field(description="Concise rationale in 1-2 sentences")


@dataclass(frozen=True)
class LiveEvalCase:
    """Evaluator-authored, curriculum-grounded case for live tutor and assessment evaluation."""
    id: str
    category: str
    learner_input: str
    expected_guardrail_outcome: str
    expected_assessable: bool
    expected_skill_id: str | None = None
    acceptable_skill_ids: tuple[str, ...] = ()
    expected_result: str | None = None
    expected_validation_status: str | None = None
    required_correction_points: tuple[str, ...] = ()
    required_grounding_topics: tuple[str, ...] = ()
    forbidden_behavior: tuple[str, ...] = ()
    learner_level: str | None = "A1"
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LiveEvalCase":
        required = {"id", "category", "learner_input", "expected_guardrail_outcome", "expected_assessable", "notes"}
        missing = required - raw.keys()
        if missing:
            raise CaseValidationError(f"missing required fields: {sorted(missing)}")
        allowed_fields = required | {
            "expected_skill_id",
            "acceptable_skill_ids",
            "expected_result",
            "expected_validation_status",
            "required_correction_points",
            "required_grounding_topics",
            "forbidden_behavior",
            "learner_level",
        }
        unknown = set(raw) - allowed_fields
        if unknown:
            raise CaseValidationError(f"unknown fields in live eval case: {sorted(unknown)}")

        if not isinstance(raw["id"], str) or not raw["id"].strip():
            raise CaseValidationError("id must be a non-empty string")
        if raw["category"] not in LIVE_EVAL_CATEGORIES:
            raise CaseValidationError(f"category '{raw.get('category')}' must be one of {sorted(LIVE_EVAL_CATEGORIES)}")
        if not isinstance(raw["learner_input"], str) or not raw["learner_input"].strip():
            raise CaseValidationError("learner_input must be a non-empty string")
        if raw["expected_guardrail_outcome"] not in {"allowed", "blocked"}:
            raise CaseValidationError("expected_guardrail_outcome must be 'allowed' or 'blocked'")
        if not isinstance(raw["expected_assessable"], bool):
            raise CaseValidationError("expected_assessable must be a boolean")

        skill_id = raw.get("expected_skill_id")
        if skill_id is not None and (not isinstance(skill_id, str) or not skill_id.strip()):
            raise CaseValidationError("expected_skill_id must be a string or null")

        result = raw.get("expected_result")
        if result is not None and result not in {"correct", "incorrect", "partial", "unknown"}:
            raise CaseValidationError(f"expected_result '{result}' must be one of correct/incorrect/partial/unknown/null")

        val_status = raw.get("expected_validation_status")
        if val_status is not None and val_status not in {"accepted", "rejected", "invalid", "ambiguous", "low_confidence"}:
            raise CaseValidationError(f"expected_validation_status '{val_status}' is invalid")

        def _to_str_tuple(field_name: str) -> tuple[str, ...]:
            val = raw.get(field_name, [])
            if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
                raise CaseValidationError(f"{field_name} must be a list of strings")
            return tuple(val)

        acceptable_skills = _to_str_tuple("acceptable_skill_ids")
        if not acceptable_skills and skill_id:
            acceptable_skills = (skill_id,)
        elif skill_id and skill_id not in acceptable_skills:
            acceptable_skills = (skill_id, *acceptable_skills)

        correction_points = _to_str_tuple("required_correction_points")
        grounding_topics = _to_str_tuple("required_grounding_topics")
        forbidden = _to_str_tuple("forbidden_behavior")

        learner_level = raw.get("learner_level", "A1")
        if learner_level is not None and not isinstance(learner_level, str):
            raise CaseValidationError("learner_level must be a string or null")

        if not isinstance(raw["notes"], str) or not raw["notes"].strip():
            raise CaseValidationError("notes must be a non-empty string")

        return cls(
            id=raw["id"],
            category=raw["category"],
            learner_input=raw["learner_input"],
            expected_guardrail_outcome=raw["expected_guardrail_outcome"],
            expected_assessable=raw["expected_assessable"],
            expected_skill_id=skill_id,
            acceptable_skill_ids=acceptable_skills,
            expected_result=result,
            expected_validation_status=val_status,
            required_correction_points=correction_points,
            required_grounding_topics=grounding_topics,
            forbidden_behavior=forbidden,
            learner_level=learner_level,
            notes=raw["notes"],
        )
