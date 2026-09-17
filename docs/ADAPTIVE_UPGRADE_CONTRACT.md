# SpanishAmigo adaptive-upgrade contract (historical design contract)

> **Historical design contract**: This document records the architectural constraints and design requirements established prior to Adaptive V2 implementation. The implementation has since been completed and verified in production. For current operational behavior and deployment architecture, consult the root [README.md](../README.md), [EVALUATION.md](../EVALUATION.md), and source code. Statements below that use future tense or describe components as absent reflect the state of the repository at the time this contract was written.

## 1. Product thesis

SpanishAmigo evolves from a stateful RAG tutor into an auditable adaptive learning system:

`Observe -> Diagnose -> Validate -> Decide -> Practice -> Verify -> Review`

The architecture prioritizes evidence-backed long-term personalization over increasing AI autonomy.

## 2. Existing baseline that must survive

- Firebase ID tokens are verified by the FastAPI backend. Firebase anonymous users are valid, tenant-owned backend users; Google linking is supported.
- Progress is locally cached and synchronised for authenticated Firebase identities. CourseMap limits anonymous users to lesson 1; it is not merely local guest progress.
- Chat sessions/messages are Firebase-UID-owned, with history, list, rename, and delete endpoints. Anonymous global chat is limited to three messages per anonymous UID.
- `/chat/send` is the non-streaming endpoint. `/chat/send_stream` sends SSE JSON frames for `session_id`, `token`, and optionally `action_required`, followed by `data: [DONE]`.
- Phase 5's compiled LangGraph runs `plan_turn -> tutor -> save_memory`; a blocked plan routes directly to memory. Streaming calls the same authoritative pre-generation `plan_turn` and differs only in final token delivery and chat-memory persistence.
- Current RAG is Gemini embedding cosine retrieval over PostgreSQL/pgvector `lesson_slides`.
- The existing responsive CourseMap, CourseJourney, CourseSupportPanels, route-aware Layout, compact LessonPlayer, dark mode, and accessibility work are baseline functionality to extend, not rebuild.
- Schema changes use Alembic; Python dependencies use `uv`/`uv.lock`, frontend dependencies use npm/`package-lock.json`.

Baseline note at time of contract: active backend deployment target was not verified from repository source (subsequently established and verified on Vercel).

## 3. Learner-state semantics

This contract defines future concepts—stable skills, an unknown/unassessed state, mastery estimate, confidence in that estimate, evidence volume, misconceptions, review state, and evidence provenance—without creating database schemas.

`UNKNOWN != 0%` and `UNKNOWN != 50%`. Unknown means there is not yet sufficient evidence to make a learner claim.

## 4. Evidence model

A future general immutable `assessment_events` concept should support correct, incorrect, ambiguous, rejected, invalid, and low-confidence outcomes. It must retain enough evidence to explain every accepted state change.

Reuse `ChatSession` initially as optional conversational provenance. Do not require a separate `learning_sessions` table unless a later concrete requirement proves it necessary.

## 5. Product-state separation

**Course completion** answers: "How much curriculum has this learner completed?"

**Skill mastery** answers: "What does validated learner evidence indicate this learner currently knows?"

They must never be conflated.

## 6. Probabilistic versus deterministic boundary

LLMs propose structured assessments and generate curriculum-grounded teaching/practice content. Application code authenticates, validates tenancy and evidence, selects the deterministic policy action, updates mastery, schedules review, persists state, and decides whether a proposal is accepted.

## 7. Streaming parity requirement

`/chat/send` uses the compiled LangGraph. `/chat/send_stream` currently performs substantial orchestration independently. Future adaptive planning must converge on one authoritative shared planning/service layer; streaming may differ only in delivery.

Do not duplicate assessability, evidence validation, policy, learner-state loading, retrieval decisions, or state-mutation rules between these routes.

Phase 5 establishes `plan_turn` as that shared boundary. It completes guardrails, assessability, proposal validation/audit, learner-context loading, application-owned policy, retrieval selection, and grounded prompt preparation before either complete or streamed generation.

### Assessment-validation boundary

Structured model assessment is only a proposal. Text evidence is accepted only when it is grounded in the current turn, targets an atomic text-mode non-vocabulary skill, has a concrete result, and meets the centralized confidence threshold. Speech-required, contextual, broad vocabulary-domain, unsupported, malformed, and low-confidence proposals cannot become accepted evidence. Acceptance records validated evidence only; it does not imply mastery mutation.

## 8. Persistence principle

Beginning a stream is not a mastery event. A partial response cannot create a mastery mutation. State mutation requires validated learner evidence through the appropriate later practice/recall path.

## 9. Curriculum and retrieval strategy

The intended progression is:

`metadata filters -> vector candidates -> PostgreSQL lexical candidates -> simple deterministic rank fusion`

Do not add GraphRAG or a reranker unless evaluation later proves a need.

## 10. Curriculum migration rule

Current destructive `lesson_slides` reseeding is unsuitable for adaptive metadata rollout. Future changes require additive migrations, idempotent metadata backfill/upsert, and preservation of valid existing embeddings.

## 11. Mastery requirements

Do not prematurely choose a sophisticated algorithm. A future implementation must be deterministic, bounded `[0,1]`, versioned, gradual, auditable, confidence/evidence-aware, and idempotent. Explanation exposure does not update mastery. Rejected or low-confidence evidence does not update mastery.

## 12. Review scheduling

The future system schedules skill-level spaced review. FSRS is a preferred candidate, not a requirement, until its dependency, provenance, and compatibility are checked in that implementation phase. FSRS does not exist in this repository today.

## 13. Evaluation strategy

Preserve meaningful baselines before current RAG is materially changed:

- A: prompt-only tutor
- B: current RAG tutor
- C: future adaptive tutor

Offline evaluation must not depend on Gemini or network access. Evaluation numbers must be measured and reported honestly.

## 14. Free-first rule

Core adaptive functionality should use existing/free infrastructure wherever realistic. Do not require a new paid vector DB, search service, graph DB, scheduler, tracing/observability platform, or voice platform. Configurable Gemini access may remain the generation/embedding provider.

## 15. Frontend integration

The current frontend redesign is baseline. Later adaptive UX extends it rather than rebuilding it, and may show skill mastery, evidence confidence, due reviews, and "why this exercise?" only when backed by real state.

## 16. Deferred features

Defer voice roleplay, pronunciation scoring, GraphRAG, reinforcement learning, fine-tuning, multi-agent systems, avatar features, and emotion detection until core adaptive functionality and evaluations justify more complexity.
