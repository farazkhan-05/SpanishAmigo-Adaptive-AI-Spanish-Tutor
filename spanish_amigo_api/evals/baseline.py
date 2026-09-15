"""Versioned description of A and the pre-change production B retrieval contract."""
from __future__ import annotations

BASELINE_VERSION = "pre-adaptive-v2-phase-2"


def baseline_configuration() -> dict[str, object]:
    return {
        "version": BASELINE_VERSION,
        "A": {"name": "prompt-only", "retrieval": "disabled", "prompt": "app.services.ai._TUTOR_SYSTEM_PROMPT", "generation_model_setting": "GEMINI_PRIMARY_MODEL with existing fallback"},
        "B": {"name": "current-rag", "retrieval": "Gemini embedding cosine-distance over lesson_slides", "embedding_model_setting": "GEMINI_EMBEDDING_MODEL", "embedding_dimensions": 768, "query_prefix": "task: search result | query: ", "top_k": 3, "max_cosine_distance": 0.65, "context_heading": "RELEVANT LESSON REFERENCE CONTEXT", "generation_model_setting": "GEMINI_PRIMARY_MODEL with existing fallback"},
        "C": {"name": "adaptive-backend", "scope": "Phase-5 shared planner, validated assessment, application-owned policy, Phase-6 mastery/practice/FSRS review loop. Phase-8 frontend is not included."},
        "C_planner": {"status": "IMPLEMENTED", "scope": "Historical Phase 5 planning and evidence validation slice; no mastery mutation or scheduling."},
    }


def validate_baseline_configuration(config: dict[str, object]) -> None:
    b = config.get("B")
    if not isinstance(b, dict) or b.get("top_k") != 3 or b.get("max_cosine_distance") != 0.65:
        raise ValueError("baseline B does not match the current production retrieval contract")
    c = config.get("C")
    if not isinstance(c, dict) or c.get("name") != "adaptive-backend" or "frontend" not in str(c.get("scope", "")).casefold():
        raise ValueError("C must describe the implemented backend-only adaptive system")
