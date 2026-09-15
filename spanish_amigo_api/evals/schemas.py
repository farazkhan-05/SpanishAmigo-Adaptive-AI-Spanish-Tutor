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
