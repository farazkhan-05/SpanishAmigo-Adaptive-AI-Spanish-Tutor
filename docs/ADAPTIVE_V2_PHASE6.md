# Adaptive V2 Phase 6: mastery, independent practice, FSRS review

Phase 6 adds the first authoritative mastery mutation path. It does not change the frontend, chat/SSE contracts, `plan_turn`, the 0.80 assessment threshold, or production `B_legacy` retrieval.

## Eligibility and transaction

`process_accepted_evidence` is the only Phase-6 writer. In one database transaction it scopes an event and attempt to the verified Firebase UID, requires `accepted` concrete text evidence for an atomic non-vocabulary skill, requires a linked non-exposure practice attempt, locks state/card rows, applies the deterministic update, schedules FSRS, and writes immutable review history. Rejected, ambiguous, invalid, low-confidence, contextual, speech-text, vocabulary-domain, explanation-only, and duplicate events cannot mutate state.

The unique `review_history.assessment_event_id` is the durable idempotency barrier. A retry returns the already-updated state. Client requests never carry result, mastery, confidence, rating, or schedule.

## Mastery estimate and confidence

`phase6-evidence-step-v1` starts the first accepted estimate at 0.50 only at the point of real accepted evidence; previously unknown state is `NULL`. It moves toward 1 for correct and toward 0 for incorrect evidence. Independent step base is 0.12; hinted/guided base is 0.05; partial is half; validation confidence is conservatively limited to 0.80–1.00; and evidence decays as `1/(1+n/8)`. Output is bounded `[0,1]`.

Estimate confidence is accumulated evidence strength, not model confidence: independent contributes 0.20, assisted contributes 0.08, both confidence-weighted and capped at 0.90. No evidence remains `NULL`.

## FSRS and reviews

Uses PyPI `fsrs==6.3.2` / upstream `open-spaced-repetition/py-fsrs`, defaults with fuzzing disabled for reproducibility. `review_items` persists card state, step, stability, difficulty, due and last-review timestamps (UTC), plus library/scheduler version. `review_history` persists source event/attempt, previous and resulting serialized card state, due date, rating, and versions.

Application-owned rating mapping: independent incorrect = Again; correct hinted/guided or partial assisted = Hard; correct independent = Good; Easy is never automatic. Explanation is never a successful review.

Authenticated endpoints are `GET /adaptive/reviews/due`, `GET /adaptive/reviews/next`, `POST /adaptive/reviews/{review_id}/start`, and `POST /adaptive/reviews/{review_id}/submit`.

`start` locks a due, UID-owned review item and creates (or resumes) one pending server-issued `PracticeAttempt`. Its opaque attempt ID, server-generated exercise ID, taxonomy-grounded prompt snapshot, review-item foreign key, skill, and processing version form the authoritative exercise context. Starting/viewing it does not mutate mastery.

`submit` accepts only that attempt ID and learner answer. It locks and UID-scopes both review and attempt, then reuses Phase 5's `propose_assessment`, assessability gate, and `validate_assessment_proposal`; it also requires the accepted proposed skill to match the stored review skill. The append-only assessment event is linked to the attempt. Accepted events call `process_accepted_evidence`; rejected, invalid, malformed/provider-failed, low-confidence, contextual, speech-text, vocabulary, invented-evidence, and mismatched-skill events finalize without mastery or FSRS mutation. Repeated submission returns the already-linked event, rather than reassessing or rescheduling.

Every lookup is UID-scoped. Rationale uses stored facts only: due, prior independent failure, or need for additional validated evidence.

Migration `c6d7e8f9a0b1` is additive and reversible. Live PostgreSQL/pgvector execution was not verified within this implementation phase (subsequently verified during production release gates).
