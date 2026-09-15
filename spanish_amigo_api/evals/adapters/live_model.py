"""Explicit A/B model adapter. It is never loaded by CI/offline evaluation."""
from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.database import SessionLocal
from app.config import get_settings
from app.services.ai import (
    _TUTOR_SYSTEM_PROMPT,
    extract_text_content,
    guardrails_node,
    invoke_with_fallback,
    prepare_tutor_messages,
)

from ..schemas import GoldenCase


def _token_usage(response: Any) -> int | None:
    metadata = getattr(response, "usage_metadata", None)
    if isinstance(metadata, dict):
        total = metadata.get("total_tokens")
        return total if isinstance(total, int) else None
    return None


def runtime_configuration() -> dict[str, str]:
    settings = get_settings()
    return {"provider": "Google Gemini", "generation_primary_model": settings.GEMINI_PRIMARY_MODEL, "generation_backup_model": settings.GEMINI_BACKUP_MODEL, "embedding_model": settings.GEMINI_EMBEDDING_MODEL, "prompt": "app.services.ai._TUTOR_SYSTEM_PROMPT"}


def evaluate_live_case(case: GoldenCase, baseline: str) -> dict[str, object]:
    """Run existing guardrails then A or B, returning minimal safe observation metadata."""
    state: dict[str, Any] = {"messages": [HumanMessage(content=case.user_input)], "user_id": "eval-user", "user_name": "Eval Amigo", "completed_lessons_count": 0}
    guardrail = guardrails_node(state)
    if guardrail["guardrail_blocked"]:
        return {"behavior": "blocked", "latency_ms": 0.0, "token_usage": None, "retrieved_slide_ids": []}
    started = time.perf_counter()
    db = SessionLocal()
    try:
        if baseline == "A":
            prompt = _TUTOR_SYSTEM_PROMPT.format(user_name="Eval Amigo", completed_count=0)
            messages = [SystemMessage(content=prompt), state["messages"][0]]
        else:
            messages = prepare_tutor_messages(state, db)
        response = invoke_with_fallback(messages, db, bind_toggle_theme=True)
        # Evaluate only behavior/metadata; do not persist arbitrary full model traces in reports.
        _ = extract_text_content(response.content)
        return {"behavior": "allowed", "latency_ms": round((time.perf_counter() - started) * 1000, 3), "token_usage": _token_usage(response), "retrieved_slide_ids": []}
    finally:
        db.close()
