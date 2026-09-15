"""Non-destructive, rerunnable curriculum embedding and metadata backfill."""
import json
import os
import sys
import time
from dataclasses import asdict

from google import genai
from google.genai import types
from sqlalchemy.dialects.postgresql import insert as pg_insert

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.config import get_settings
from app.curriculum_metadata import SKILLS, TAXONOMY_VERSION, metadata_for_slide, validate_taxonomy
from app.database import SessionLocal
from app.models import LessonSlide, LessonSlideSkill, Skill

settings = get_settings()

def _document_text(slide: dict[str, object]) -> str:
    body = str(slide["content_text"])
    if slide.get("explanation"): body += f"\nExplanation: {slide['explanation']}"
    return f"title: Lesson {slide['lesson_id']} Slide {slide['slide_index']} | text: {body}"

def backfill(dry_run: bool = False) -> dict[str, int]:
    """Upsert metadata; only new or source-changed rows request an embedding; never delete slides."""
    validate_taxonomy()
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lessons_data.json")
    if not os.path.exists(path): raise FileNotFoundError("lessons_data.json not found; run parse_lessons.js first")
    slides = json.loads(open(path, encoding="utf-8").read())
    report = {key: 0 for key in ("inserted", "updated", "unchanged", "unresolved", "failures", "embeddings_generated")}
    db = SessionLocal(); client = None
    try:
        for definition in SKILLS:
            values = {**asdict(definition), "taxonomy_version": TAXONOMY_VERSION}; values.pop("prerequisites")
            old = db.get(Skill, definition.skill_id)
            report["inserted" if old is None else "updated" if any(getattr(old, key) != value for key, value in values.items()) else "unchanged"] += 1
            if not dry_run: db.execute(pg_insert(Skill).values(**values).on_conflict_do_update(index_elements=[Skill.skill_id], set_={key: value for key, value in values.items() if key != "skill_id"}))
        if not dry_run: db.flush()
        for data in slides:
            lesson_id, slide_index = int(data["lesson_id"]), int(data["slide_index"])
            skill_ids, cefr, difficulty, objective = metadata_for_slide(lesson_id, slide_index)
            if not skill_ids: report["unresolved"] += 1
            old = db.query(LessonSlide).filter_by(lesson_id=lesson_id, slide_index=slide_index).one_or_none()
            source_changed = old is not None and any(getattr(old, key) != data.get(key) for key in ("slide_type", "content_text", "explanation"))
            values = {"lesson_id": lesson_id, "slide_index": slide_index, "slide_type": data["slide_type"], "content_text": data["content_text"], "explanation": data.get("explanation"), "cefr_level": cefr, "difficulty": difficulty, "learning_objective": objective, "taxonomy_version": TAXONOMY_VERSION}
            if old is None or old.embedding is None or source_changed:
                if not dry_run:
                    client = client or genai.Client(api_key=settings.GEMINI_API_KEY)
                    values["embedding"] = client.models.embed_content(model=settings.GEMINI_EMBEDDING_MODEL, contents=_document_text(data), config=types.EmbedContentConfig(output_dimensionality=768)).embeddings[0].values
                    report["embeddings_generated"] += 1; time.sleep(0.75)
            report["inserted" if old is None else "updated" if any(getattr(old, key) != value for key, value in values.items() if key != "embedding") else "unchanged"] += 1
            if not dry_run:
                db.execute(pg_insert(LessonSlide).values(**values).on_conflict_do_update(index_elements=[LessonSlide.lesson_id, LessonSlide.slide_index], set_=values)); db.flush()
                row = db.query(LessonSlide).filter_by(lesson_id=lesson_id, slide_index=slide_index).one()
                db.query(LessonSlideSkill).filter_by(lesson_slide_id=row.id, taxonomy_version=TAXONOMY_VERSION).delete(synchronize_session=False)
                db.add_all(LessonSlideSkill(lesson_slide_id=row.id, skill_id=skill_id, taxonomy_version=TAXONOMY_VERSION) for skill_id in skill_ids)
        if dry_run: db.rollback()
        else: db.commit()
    except Exception:
        report["failures"] += 1; db.rollback(); raise
    finally: db.close()
    return report

if __name__ == "__main__": print(backfill(dry_run="--dry-run" in sys.argv))
