# Adaptive V2 Phase 3: curriculum and retrieval foundation

Taxonomy `spanishamigo-v1` contains 14 human-curated, stable IDs. It is scoped to the five actual beginner lessons and treats each skill as reusable/assessable rather than labeling every slide. The only CEFR claim is A1 where the material supports it; unresolved slides use `UNKNOWN`.

Mappings are static in `app/curriculum_metadata.py`, versioned, and auditable. Nine cultural/personal-space lesson-one slides are deliberately unresolved. The remaining 222 of 231 slides have one or more mapped skills (96.1% coverage). No mapping is model-generated at runtime.

`python seed_embeddings.py --dry-run` reports inserted, updated, unchanged, unresolved, failures, and embeddings generated. A normal run uses upserts and preserves valid embeddings; it requests an embedding only for a missing embedding or a changed source. It never drops, truncates, or recreates `lesson_slides`.

The additive migration creates `skills`, `lesson_slide_skills`, audited slide metadata, a `simple` PostgreSQL full-text vector (chosen for mixed English prompt/Spanish answer text), its GIN index, and the lesson/slide uniqueness constraint. It first detects duplicates and aborts rather than deleting them.

Retrieval has `B_legacy`, metadata-aware semantic, lexical, and hybrid strategies. Hybrid uses reciprocal-rank fusion with k=60, deterministic tie-breaking by lesson/slide identity, and deduplication. The tutor still calls only `B_legacy`; hybrid is evaluation-only pending measured evidence.
