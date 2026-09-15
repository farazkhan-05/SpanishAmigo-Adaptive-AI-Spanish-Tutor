"""Read-only reproduction of the current B retrieval query; it never seeds or mutates tables."""
from __future__ import annotations

from google import genai
from google.genai import types
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import LessonSlide


def runtime_configuration() -> dict[str, object]:
    settings = get_settings()
    return {"provider": "Google Gemini", "embedding_model": settings.GEMINI_EMBEDDING_MODEL, "generation_primary_model": settings.GEMINI_PRIMARY_MODEL, "generation_backup_model": settings.GEMINI_BACKUP_MODEL, "retrieval_mode": "current semantic pgvector cosine retrieval"}


def retrieve_current_rag(user_input: str) -> list[str]:
    settings = get_settings()
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    embedding = client.models.embed_content(model=settings.GEMINI_EMBEDDING_MODEL, contents=f"task: search result | query: {user_input}", config=types.EmbedContentConfig(output_dimensionality=768))
    vector = embedding.embeddings[0].values
    db = SessionLocal()
    try:
        distance = LessonSlide.embedding.cosine_distance(vector)
        rows = db.execute(select(LessonSlide, distance.label("distance")).order_by(distance).limit(3)).all()
        return [f"L{slide.lesson_id}-S{slide.slide_index}" for slide, value in rows if value < 0.65]
    finally:
        db.close()
