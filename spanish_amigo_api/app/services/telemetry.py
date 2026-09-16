"""Best-effort, content-free AI telemetry and local reporting."""
from __future__ import annotations
import logging
import random
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any, Sequence
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import SessionLocal
from app.models import AiTelemetryEvent

logger = logging.getLogger("spanish-amigo-telemetry")

def first_token_timestamp(existing: float | None, content: str, now: float) -> float | None:
    """Set TTFT once, and only for a non-empty generated text token."""
    return existing if existing is not None or not content else now

def error_category(error: BaseException) -> str:
    name = type(error).__name__.lower()
    text = str(error).lower()
    if "429" in text or "quota" in text or "resource_exhausted" in text: return "provider_quota"
    if "timeout" in name or "timeout" in text: return "provider_timeout"
    if "validation" in name or "parse" in text: return "structured_output"
    return "provider_error"

def token_fields(metadata: Any) -> dict[str, int | None]:
    if not isinstance(metadata, dict): return {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    def number(*keys: str) -> int | None:
        for key in keys:
            value = metadata.get(key)
            if isinstance(value, int) and value >= 0: return value
        return None
    return {"input_tokens": number("input_tokens", "prompt_token_count"), "output_tokens": number("output_tokens", "candidates_token_count"), "total_tokens": number("total_tokens", "total_token_count")}

def record(**fields: Any) -> None:
    """Never let a database outage alter learner-facing behavior."""
    settings = get_settings()
    # Failures are always retained; only successful events are sampled.
    if not settings.TELEMETRY_ENABLED: return
    if fields.get("success", True) and random.random() > settings.TELEMETRY_SAMPLE_RATE: return
    allowed = {column.name for column in AiTelemetryEvent.__table__.columns}
    safe = {key: value for key, value in fields.items() if key in allowed}
    try:
        with SessionLocal() as db:
            db.add(AiTelemetryEvent(**safe))
            db.commit()
    except Exception:
        logger.warning("telemetry write failed", exc_info=True)

def percentile(values: Sequence[float], percent: int) -> float | None:
    if not values: return None
    ordered = sorted(values); index = round((len(ordered) - 1) * percent / 100)
    return ordered[index]

def report(db: Session, hours: int = 24) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = list(db.scalars(select(AiTelemetryEvent).where(AiTelemetryEvent.occurred_at >= since)))
    durations = {name: [float(value) for row in rows if (value := getattr(row, name)) is not None] for name in ("total_duration_ms", "ttft_ms", "model_duration_ms", "retrieval_duration_ms", "assessment_duration_ms", "embedding_duration_ms")}
    tokens = [row.total_tokens for row in rows if row.total_tokens is not None]
    failures = sum(not row.success for row in rows)
    return {"hours": hours, "sample_count": len(rows), "percentiles": {name: {"sample_count": len(values), "p50": percentile(values, 50), "p95": percentile(values, 95)} for name, values in durations.items()}, "token_total": sum(tokens) if tokens else None, "token_mean": (sum(tokens) / len(tokens)) if tokens else None, "model_failures": failures, "model_failure_rate": (failures / len(rows)) if rows else 0.0, "fallbacks": sum(row.fallback_used for row in rows), "retries": sum(row.retry_count for row in rows), "structured_output_failures": sum(row.structured_output_failure is not None for row in rows), "assessment_rejections": {reason: sum(row.assessment_rejection_reason == reason for row in rows) for reason in sorted({row.assessment_rejection_reason for row in rows if row.assessment_rejection_reason})}, "adaptive_update_failures": sum(row.adaptive_update_failure is not None for row in rows), "review_scheduling_failures": sum(row.review_scheduling_failure is not None for row in rows)}

def prune(db: Session, retention_days: int | None = None) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days or get_settings().TELEMETRY_RETENTION_DAYS)
    result = db.execute(delete(AiTelemetryEvent).where(AiTelemetryEvent.occurred_at < cutoff)); db.commit()
    return int(result.rowcount or 0)
