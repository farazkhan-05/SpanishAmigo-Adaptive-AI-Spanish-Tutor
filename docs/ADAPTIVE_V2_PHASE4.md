# Adaptive V2 Phase 4: tenant-safe learner evidence storage

Phase 4 adds persistence only. It does not assess chat, calculate mastery, schedule reviews, generate practice, or change retrieval.

## Learner state and unknown semantics

`learner_skill_states` has one tenant UID + stable `skill_id` row where a future service needs a durable state container. `mastery_estimate` and `estimate_confidence` are nullable and `NULL` means **unknown**, never zero or a midpoint. Counters begin at zero and this phase has no production writer that calculates or assigns a mastery estimate. State rows are not created for contextual skills through the public storage helper.

`GET /adaptive/state` is authenticated and always scopes its query to the verified Firebase UID. It returns the taxonomy's display label and mode, with `not_assessed`, `evidence_insufficient`, or `assessed` status. An absent row is returned honestly as `not_assessed`; no client identity or write operation is accepted.

## Evidence and attempts

`assessment_events` is append-oriented: it stores a UUID, user/skill, compact evidence snapshot, optional chat provenance, structured proposed result, validation status, optional correction/misconception fields, confidence, taxonomy version, and validator/model version fields. It deliberately excludes model reasoning traces. Events can point to a prior event through `supersedes_event_id`; normal application helpers create only new events and expose no update endpoint.

Lifecycle statuses are `proposed`, `accepted`, `rejected`, `ambiguous`, `invalid`, and `low_confidence`; results are `correct`, `incorrect`, `partial`, `unknown`, and `not_applicable`. A helper rejects accepting a non-concrete result. Final evidence validation and all mastery mutation remain later work.

`practice_attempts` stores its own UUID, user/skill, optional event and chat references, exercise identifier/type, compact prompt/response snapshots, outcome placeholder, support level, hint usage, independent recall flag, processing version, and taxonomy version. `independent`, `hinted`, `guided`, `exposure`, and `failed` are distinct support levels. Exposure therefore cannot be mistaken for successful independent recall.

Both records support a server-created, trusted `source_event_key`, unique per user. Replaying the same key returns the existing record within normal service usage; constraints provide the durable duplicate barrier. It is not a client authorization mechanism.

## Provenance, taxonomy, and deletion

ChatSession and ChatMessage remain optional provenance. Event and attempt tables use `ON DELETE SET NULL` for those source references, while retaining the minimal learner evidence/prompt/response snapshot needed to explain a historical record after chat deletion. User deletion cascades tenant-owned state, events, and attempts, consistent with current user-owned chat/progress cascades. There is no separate account-deletion workflow in the current source; a future account-deletion implementation must include these tables. There is no permanent-retention policy added here.

Taxonomy identity is the static stable `skill_id`; events and attempts retain `spanishamigo-v1` for historical interpretation rather than duplicating the full taxonomy. The `mastery_eligibility` foundation returns true only for text-mode skills with text evidence. It is deliberately a narrow predicate, not an acceptance or mastery algorithm: speech-required skills require a future speech-specific validator, contextual skills cannot become atomic mastery targets through the helper, and broad vocabulary skills get no domain-wide inference from an event or attempt.

## Migration and verification boundary

Migration `b4c5d6e7f8a9` is additive, names every new foreign key/constraint/index, bounds numeric values, uses nullable mastery fields, and has a reversible downgrade. It has not been executed against a safe disposable PostgreSQL/pgvector database in this phase; static and SQLite-backed application tests do not verify PostgreSQL DDL, Phase 3 migration behavior, or downgrade/re-upgrade behavior.

Deliberately deferred: LLM assessment proposals, final evidence validation, mastery mutation, adaptive policy/LangGraph, FSRS, exercise generation, adaptive UI, hybrid retrieval activation, and a public event/attempt write API.
