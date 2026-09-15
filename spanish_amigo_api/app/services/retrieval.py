"""Curriculum retrieval strategies. Legacy semantic is the frozen Phase-2 B adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import LessonSlide, LessonSlideSkill, Skill

LEGACY_TOP_K = 3
LEGACY_MAX_COSINE_DISTANCE = 0.65
RRF_K = 60  # Standard RRF smoothing constant; ranking, not raw-score, fusion.


@dataclass(frozen=True)
class RetrievalFilters:
    skill_ids: tuple[str, ...] = ()
    cefr_level: str | None = None
    lesson_id: int | None = None
    difficulty: int | None = None


@dataclass(frozen=True)
class RetrievedSlide:
    slide_id: str
    lesson_id: int
    slide_index: int
    content_text: str
    explanation: str | None
    skill_ids: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    rank: int | None = None
    scores: dict[str, float] = field(default_factory=dict)


def _identifier(slide: LessonSlide) -> str: return f"L{slide.lesson_id}-S{slide.slide_index}"

def _result(slide: LessonSlide, source: str, rank: int, score: float) -> RetrievedSlide:
    return RetrievedSlide(_identifier(slide), slide.lesson_id, slide.slide_index, slide.content_text, slide.explanation, tuple(sorted(s.skill_id for s in slide.skills)), (source,), rank, {source: score})

def _filtered(stmt: Select, filters: RetrievalFilters) -> Select:
    if filters.lesson_id is not None: stmt = stmt.where(LessonSlide.lesson_id == filters.lesson_id)
    if filters.cefr_level is not None: stmt = stmt.where(LessonSlide.cefr_level == filters.cefr_level)
    if filters.difficulty is not None: stmt = stmt.where(LessonSlide.difficulty == filters.difficulty)
    if filters.skill_ids: stmt = stmt.join(LessonSlideSkill).where(LessonSlideSkill.skill_id.in_(filters.skill_ids))
    return stmt

def legacy_semantic(db: Session, query_vector: list[float]) -> list[RetrievedSlide]:
    """Exact historical B: query prefix/embedding creation occurs at the caller; top 3, < .65."""
    distance = LessonSlide.embedding.cosine_distance(query_vector)
    rows = db.execute(select(LessonSlide, distance.label("distance")).options(selectinload(LessonSlide.skills)).order_by(distance, LessonSlide.id).limit(LEGACY_TOP_K)).all()
    return [_result(slide, "semantic", rank, float(distance_value)) for rank, (slide, distance_value) in enumerate(rows, 1) if distance_value < LEGACY_MAX_COSINE_DISTANCE]

def semantic_metadata(db: Session, query_vector: list[float], filters: RetrievalFilters, candidate_count: int = 12) -> list[RetrievedSlide]:
    distance = LessonSlide.embedding.cosine_distance(query_vector)
    stmt = _filtered(select(LessonSlide, distance.label("distance")).options(selectinload(LessonSlide.skills)), filters).distinct().order_by(distance, LessonSlide.id).limit(candidate_count)
    return [_result(slide, "semantic_metadata", rank, float(value)) for rank, (slide, value) in enumerate(db.execute(stmt).all(), 1)]

def lexical(db: Session, query: str, filters: RetrievalFilters = RetrievalFilters(), candidate_count: int = 12) -> list[RetrievedSlide]:
    query_expr = func.websearch_to_tsquery("simple", query)
    rank_expr = func.ts_rank_cd(LessonSlide.__table__.c.search_vector, query_expr)
    stmt = _filtered(select(LessonSlide, rank_expr.label("rank")).options(selectinload(LessonSlide.skills)).where(LessonSlide.__table__.c.search_vector.op("@@")(query_expr)), filters).distinct().order_by(rank_expr.desc(), LessonSlide.id).limit(candidate_count)
    return [_result(slide, "lexical", rank, float(value)) for rank, (slide, value) in enumerate(db.execute(stmt).all(), 1)]

def reciprocal_rank_fusion(*ranked_lists: Iterable[RetrievedSlide], limit: int = LEGACY_TOP_K, k: int = RRF_K) -> list[RetrievedSlide]:
    if k < 1 or limit < 1: raise ValueError("RRF k and limit must be positive")
    merged: dict[str, dict[str, object]] = {}
    for candidates in ranked_lists:
        for position, candidate in enumerate(candidates, 1):
            state = merged.setdefault(candidate.slide_id, {"slide": candidate, "score": 0.0, "sources": [], "scores": {}})
            state["score"] = float(state["score"]) + 1.0 / (k + position)
            state["sources"] = list(dict.fromkeys([*state["sources"], *candidate.sources]))
            state["scores"].update(candidate.scores)
    ordered = sorted(merged.values(), key=lambda item: (-float(item["score"]), item["slide"].lesson_id, item["slide"].slide_index, item["slide"].slide_id))
    return [RetrievedSlide(item["slide"].slide_id, item["slide"].lesson_id, item["slide"].slide_index, item["slide"].content_text, item["slide"].explanation, item["slide"].skill_ids, tuple(item["sources"]), rank, {**item["scores"], "rrf": float(item["score"])}) for rank, item in enumerate(ordered[:limit], 1)]

def hybrid(db: Session, query: str, query_vector: list[float], filters: RetrievalFilters = RetrievalFilters(), candidate_count: int = 12, limit: int = LEGACY_TOP_K) -> list[RetrievedSlide]:
    return reciprocal_rank_fusion(semantic_metadata(db, query_vector, filters, candidate_count), lexical(db, query, filters, candidate_count), limit=limit)
