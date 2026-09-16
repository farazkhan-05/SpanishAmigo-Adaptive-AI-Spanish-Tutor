"""Read-only production-authoritative retrieval adapter; never seeds or mutates tables."""
from __future__ import annotations

import time
from typing import Any
from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.services.retrieval import (
    LEGACY_MAX_COSINE_DISTANCE,
    LEGACY_TOP_K,
    RetrievalFilters,
    hybrid,
    legacy_semantic,
    semantic_metadata,
)


def runtime_configuration() -> dict[str, object]:
    settings = get_settings()
    return {
        "provider": "Google Gemini",
        "embedding_model": settings.GEMINI_EMBEDDING_MODEL,
        "generation_primary_model": settings.GEMINI_PRIMARY_MODEL,
        "generation_backup_model": settings.GEMINI_BACKUP_MODEL,
        "retrieval_mode": "production authoritative pgvector cosine retrieval (legacy_semantic)",
        "legacy_top_k": LEGACY_TOP_K,
        "legacy_max_cosine_distance": LEGACY_MAX_COSINE_DISTANCE,
    }


def embed_query(query: str, client: genai.Client | None = None) -> list[float]:
    """Generate one query embedding using production format and model."""
    settings = get_settings()
    client = client or genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.embed_content(
        model=settings.GEMINI_EMBEDDING_MODEL,
        contents=f"task: search result | query: {query}",
        config=types.EmbedContentConfig(output_dimensionality=768),
    )
    return [float(v) for v in response.embeddings[0].values]


def retrieve_legacy(db: Session, query_vector: list[float]) -> list[str]:
    """Authoritative production B_legacy retrieval via app.services.retrieval.legacy_semantic."""
    results = legacy_semantic(db, query_vector)
    return [r.slide_id for r in results]


def retrieve_hybrid_variant(db: Session, query: str, query_vector: list[float], limit: int = LEGACY_TOP_K) -> list[str]:
    """Authoritative B_hybrid retrieval via app.services.retrieval.hybrid (fair: no metadata filters)."""
    results = hybrid(db, query, query_vector, filters=RetrievalFilters(), limit=limit)
    return [r.slide_id for r in results]


def retrieve_targeted_oracle_variant(db: Session, query_vector: list[float], skill_id: str, limit: int = LEGACY_TOP_K) -> list[str]:
    """Targeted skill retrieval using oracle skill conditioning (upper-bound experiment)."""
    results = semantic_metadata(db, query_vector, RetrievalFilters(skill_ids=(skill_id,)))[:limit]
    return [r.slide_id for r in results]


def retrieve_current_rag(user_input: str, db: Session | None = None, query_vector: list[float] | None = None) -> list[str]:
    """Read-only production B retrieval calling production legacy_semantic directly."""
    vector = query_vector if query_vector is not None else embed_query(user_input)
    if db is not None:
        return retrieve_legacy(db, vector)
    session = SessionLocal()
    try:
        return retrieve_legacy(session, vector)
    finally:
        session.close()


def retrieve_variant(
    user_input: str,
    variant: str,
    db: Session | None = None,
    query_vector: list[float] | None = None,
    oracle_skill_id: str | None = None,
) -> list[str]:
    """Read-only retrieval adapter supporting shared query embeddings and connection reuse."""
    if variant == "B_legacy":
        return retrieve_current_rag(user_input, db=db, query_vector=query_vector)

    vector = query_vector if query_vector is not None else embed_query(user_input)

    def _execute(session: Session) -> list[str]:
        if variant == "B_hybrid":
            return retrieve_hybrid_variant(session, user_input, vector)
        elif variant == "targeted_oracle":
            if not oracle_skill_id:
                return []
            return retrieve_targeted_oracle_variant(session, vector, oracle_skill_id)
        elif variant == "B_metadata":
            rows = semantic_metadata(session, vector, RetrievalFilters())
            return [row.slide_id for row in rows]
        else:
            raise ValueError(f"unknown retrieval variant: {variant}")

    if db is not None:
        return _execute(db)
    session = SessionLocal()
    try:
        return _execute(session)
    finally:
        session.close()
