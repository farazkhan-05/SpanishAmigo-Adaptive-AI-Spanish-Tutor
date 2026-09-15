"""Versioned description of A and the pre-change production B retrieval contract."""
from __future__ import annotations

BASELINE_VERSION = "pre-adaptive-v2-phase-2"


def baseline_configuration() -> dict[str, object]:
    return {
        "version": BASELINE_VERSION,
        "A": {"name": "prompt-only", "retrieval": "disabled", "prompt": "app.services.ai._TUTOR_SYSTEM_PROMPT", "generation_model_setting": "GEMINI_PRIMARY_MODEL with existing fallback"},
        "B": {"name": "current-rag", "retrieval": "Gemini embedding cosine-distance over lesson_slides", "embedding_model_setting": "GEMINI_EMBEDDING_MODEL", "embedding_dimensions": 768, "query_prefix": "task: search result | query: ", "top_k": 3, "max_cosine_distance": 0.65, "context_heading": "RELEVANT LESSON REFERENCE CONTEXT", "generation_model_setting": "GEMINI_PRIMARY_MODEL with existing fallback"},
        "C": {"status": "NOT IMPLEMENTED", "reason": "Adaptive learner-state tutor is out of scope for Phase 2."},
        "C_planner": {"status": "IMPLEMENTED", "scope": "Phase 5 planning and evidence validation only; no mastery mutation or scheduling."},
    }


def validate_baseline_configuration(config: dict[str, object]) -> None:
    b = config.get("B")
    if not isinstance(b, dict) or b.get("top_k") != 3 or b.get("max_cosine_distance") != 0.65:
        raise ValueError("baseline B does not match the current production retrieval contract")
    if config.get("C") != {"status": "NOT IMPLEMENTED", "reason": "Adaptive learner-state tutor is out of scope for Phase 2."}:
        raise ValueError("C must remain explicitly not implemented")
