"""Strict schemas for repository-owned evaluation data (no model-generated labels)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
}


@dataclass(frozen=True)
class RetrievalBenchmarkCase:
    """Source-grounded curriculum retrieval evaluation case with verified gold slide IDs."""
    id: str
    query: str
    category: str
    primary_lesson_id: int
    expected_relevant_slide_ids: tuple[str, ...]
    expected_relevant_lesson_ids: tuple[int, ...]
    expected_relevant_skill_ids: tuple[str, ...]
    notes: str

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
        if not isinstance(raw["primary_lesson_id"], int) or not (1 <= raw["primary_lesson_id"] <= 5):
            raise CaseValidationError("primary_lesson_id must be an integer between 1 and 5")
        slide_ids = raw["expected_relevant_slide_ids"]
        if not isinstance(slide_ids, list) or not slide_ids:
            raise CaseValidationError("expected_relevant_slide_ids must be a non-empty list of strings")
        if len(slide_ids) != len(set(slide_ids)):
            raise CaseValidationError("expected_relevant_slide_ids must not contain duplicate slide IDs")
        for sid in slide_ids:
            if not isinstance(sid, str) or not sid.startswith("L") or "-S" not in sid:
                raise CaseValidationError(f"invalid slide ID format: {sid}")
        lesson_ids = raw["expected_relevant_lesson_ids"]
        if not isinstance(lesson_ids, list) or not lesson_ids or not all(isinstance(x, int) and 1 <= x <= 5 for x in lesson_ids):
            raise CaseValidationError("expected_relevant_lesson_ids must be a non-empty list of integers (1..5)")
        skill_ids = raw["expected_relevant_skill_ids"]
        if not isinstance(skill_ids, list) or not all(isinstance(x, str) and x.strip() for x in skill_ids):
            raise CaseValidationError("expected_relevant_skill_ids must be a list of non-empty strings")
        if not isinstance(raw["notes"], str) or not raw["notes"].strip():
            raise CaseValidationError("notes must be a non-empty string")
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
