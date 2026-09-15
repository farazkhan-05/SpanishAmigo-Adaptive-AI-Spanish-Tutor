# SpanishAmigo pre-adaptive evaluation baseline

Evaluation protects an honest before/after comparison while retrieval and curriculum evolve. Every result is marked **MEASURED**, **NOT RUN**, or **NOT IMPLEMENTED**; this repository contains no placeholder scores.

Baseline A is the existing Lumi tutoring prompt and generation-model/fallback behavior with curriculum retrieval excluded. It is evaluation-only, not a production mode. Baseline B is the current production RAG path: Gemini `gemini-embedding-2` configured through `GEMINI_EMBEDDING_MODEL`, a 768-dimensional query prefixed `task: search result | query: `, cosine ranking against `lesson_slides`, top 3 candidates, and only context under cosine distance `0.65`, formatted beneath `RELEVANT LESSON REFERENCE CONTEXT`. B retains the current tutor prompt and model fallback behavior. C, the adaptive learner-state tutor, is **NOT IMPLEMENTED**.

The initial versioned dataset has 62 human-curated cases spanning Spanish correctness/corrections, ser/estar, articles/gender, conjugation, vocabulary, self-correction, ambiguity, grammar questions, non-assessable inputs, greetings, translation, curriculum questions, retrieval distractors/cross-lesson evidence, off-topic content, injection, guardrail boundaries, and minimal inputs. It deliberately uses broad grammar labels and current lesson/slide references only; it defines no provisional skill taxonomy.

## Reproduction

From `spanish_amigo_api`:

```powershell
uv run python -m evals.run_eval offline --report evals/reports/offline.json
```

This is an **OFFLINE METRIC TEST**: deterministic schema/dataset/config/report validation and unit-tested fixture metrics. It makes no network, Gemini, database, or adapter calls. It reports validation reliability; live retrieval and safety outcomes are **NOT RUN**.

```powershell
uv run python -m evals.run_eval db-retrieval --report evals/reports/db-retrieval.json
```

This optional **LOCAL/INTEGRATION RETRIEVAL EVAL** is explicitly opt-in. It uses configured Gemini embeddings and reads the current local PostgreSQL/pgvector `lesson_slides` table only. It never seeds, migrates, writes, or runs destructive curriculum tooling. It measures Recall@3 and MRR only for cases with slide labels and records stable case-ID failure artifacts.

```powershell
uv run python -m evals.run_eval live-model --baseline B --limit 1 --confirm-live --report evals/reports/live-model.json
```

This optional **LIVE MODEL EVAL** is deliberately opt-in and requires `--confirm-live`; it invokes the configured Gemini generation model and may consume quota. It can run A (prompt-only) or B (current RAG), records timestamp, Git SHA, dataset hash, baseline configuration, observed guardrail behavior, latency, and provider-supplied token usage when available. It does not call a model judge or claim generated-answer correctness. The external model is mutable, so live results are not perfectly reproducible.

Implemented retrieval metrics are Recall@K and MRR. Reliability reports case-load and run failures. Safety, latency, and token usage are report fields but are **NOT RUN** unless an applicable adapter supplies actual observations; token use is never estimated. Adaptive mastery, policy, and FSRS metrics are **NOT IMPLEMENTED**.

Known limitations: no live model judge or generated-response scoring exists; guardrail outcomes are not evaluated by the offline runner; the optional DB mode requires existing local database and configured provider access; retrieval fixtures do not claim to execute pgvector.
