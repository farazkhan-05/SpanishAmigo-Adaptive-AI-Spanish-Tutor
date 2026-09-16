# Adaptive V2 Phase 5: validated assessment and shared turn planning

## Scope and activation

Phase 5 implements structured learner-assessment proposals, deterministic validation, deterministic teaching policy, and one pre-generation turn planner shared by `/chat/send` and `/chat/send_stream`. It does **not** mutate mastery, schedule review, create practice success, add FSRS, change the frontend, or activate hybrid retrieval.

`ADAPTIVE_V2_PLANNER_ENABLED` is an internal environment setting and defaults to `false`. With the flag off, the shared planner still owns guardrails and context preparation but selects `NO_ADAPTIVE_ACTION`, creates no assessment event, and uses frozen `B_legacy`. Offline evaluation and internal tests enable the planner explicitly. This conservative default keeps legacy production behavior available until later adaptive phases are complete.

## Assessability and structured proposal

The deterministic first gate classifies a turn as potential learner production only when there is an explicit answer/self-correction, an answer in recent exercise context, or meaningful independent Spanish production. Greetings, information/explanation questions, translation requests, UI/theme commands, blocked/off-topic input, metadata requests, and minimal noise are not assessed. Language detection alone is insufficient.

An assessable turn may be sent to the configured Gemini model with strict Pydantic output `AssessmentProposal` (`extra=forbid`, strict types): `assessable`, stable `skill_id`, `result`, optional small `error_type`, optional severity `1..3`, confidence in `[0,1]`, exact learner `evidence`, optional correction/misconception ID, and fixed `assessment_version=phase5-v1`. Results are `correct`, `incorrect`, `partial`, `unknown`, or `not_applicable`. No free-form reasoning or chain-of-thought is requested or stored. The configured active model identifier is recorded.

## Deterministic evidence validation

The proposal is untrusted. Validator `phase5-validator-v1` checks, in order:

1. both the application gate and proposal say the turn is assessable;
2. `skill_id` exists in taxonomy `spanishamigo-v1`;
3. evidence modality is supported;
4. `speech_required` is rejected for text evidence;
5. `contextual` is rejected as an atomic mastery claim;
6. vocabulary-category skills are rejected as broad-domain overclaims from one lexical span;
7. proposed evidence is an exact substring or survives only conservative normalization against the current learner turn;
8. the result is concrete; and
9. confidence is at least the application-owned `0.80` threshold.

Normalization applies Unicode NFC, case-folding, surrounding/repeated whitespace folding, and folding of ordinary sentence punctuation into separators. It does not strip Spanish diacritics, remove lexical tokens, remove negation, stem, translate, or reorder words. Exact evidence receives character offsets; safely normalized-only evidence remains traceable through `normalized_evidence` without fabricated offsets.

Confidence is an uncalibrated model signal, not probability or mastery confidence. Below `0.80` produces `low_confidence`, never accepted evidence.

## Event lifecycle and storage

The source turn produces at most one append-only final validation record containing proposal fields, evidence and normalized evidence, optional exact span, validation status/reason, taxonomy, validator, schema version, and configured model identifier. Status is `accepted`, `rejected`, `ambiguous`, `invalid`, or `low_confidence`; Phase 4's `proposed` value remains available for explicitly unvalidated internal ingestion. A server-derived key hashes the session and conversation prefix/current turn, and the existing per-user unique constraint prevents duplicate accepted evidence on retry.

Assessment persistence occurs after validation and before final generation. It concerns the already-submitted learner message, so a later failed stream does not erase it. A failed stream does not create a practice attempt, successful recall, mastery update, or review. `learner_skill_states.mastery_estimate` and `estimate_confidence` remain untouched and state rows are not fabricated.

## Deterministic pedagogical policy

The pure typed policy consumes assessability/intent, validation status/result, real existing mastery (or `None`), real accepted-event count, and assessment mode. Its bounded actions are `ANSWER_NORMALLY`, `EXPLAIN_AND_GUIDE`, `TARGETED_PRACTICE`, `TARGETED_PRACTICE_WITH_HINT`, `COLLECT_MORE_EVIDENCE`, `CONTEXTUAL_TRANSFER`, and `NO_ADAPTIVE_ACTION`.

Explicit questions and translation requests take precedence over pedagogical interruption. Unknown mastery remains `None`; a correct event with unknown mastery requests more evidence rather than inventing a level. Future numeric policy support centralizes boundaries at `0.35` and `0.70`; those values are used only when numeric state genuinely exists.

Contextual skills may select bounded transfer context but cannot yield accepted atomic evidence. Speech-required skills receive no accepted pronunciation evidence from text. Vocabulary category skills can guide retrieval/curriculum context but one word cannot establish whole-domain mastery.

## Shared planner and LangGraph topology

The authoritative service function is `plan_turn`:

`guardrail -> assessability -> optional structured proposal -> deterministic validation/persistence -> read-only learner/event context -> deterministic policy -> retrieval decision -> grounded tutor messages`

The compiled LangGraph is intentionally small:

`START -> plan_turn -> (tutor | save_memory when blocked) -> save_memory -> END`

`/chat/send` invokes this compiled graph. `/chat/send_stream` invokes the same `plan_turn` before final model-token delivery. Streaming differs only in final generation/delivery and subsequent chat-memory write. Given identical state and model mocks, both use the same assessability, validation, action, retrieval decision, and prompt preparation.

Normal retrieval remains `B_legacy`. Only a validated targeted explanation/practice/transfer action uses the existing metadata-filtered semantic abstraction for the validated skill. `B_hybrid` remains evaluation-only. Retrieved content is delimited as curriculum reference data and explicitly cannot override application/system instructions. Learner input is JSON-encoded as untrusted data for assessment. Neither source can change authorization, validation, thresholds, persistence rules, or execute tools.

Malformed output, missing fields, invalid skills/evidence, low confidence, and provider failure never become accepted evidence. Malformed/provider failures create an `invalid` audit event for assessable turns and then fall back to ordinary safe tutor generation. Retrieval failure degrades to generation without curriculum context. Existing model fallback remains in place. Existing `session_id`, token, optional `action_required: TOGGLE_THEME`, and `[DONE]` SSE frames are unchanged.

## Verification and Phase 6 boundary

The deterministic offline `C_planner` dataset contains 20 cases. The measured run is recorded in `evals/reports/phase5-planner.json`; live Gemini assessment, database retrieval evaluation, and PostgreSQL/pgvector migration execution were not run during this phase. At this milestone, Phase 6 remained the owner of mastery mutation, evidence-weighting/versioned mastery logic, state counters/confidence changes, and review scheduling, with FSRS implemented in that subsequent phase.
