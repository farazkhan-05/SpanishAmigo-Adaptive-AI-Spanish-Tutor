# SpanishAmigo Adaptive V2 evaluation

The version-controlled, human-curated corpus has 150 cases: 62 frozen general A/B cases, 20 Phase-5 planner cases, and 68 Phase-7 safety/state cases. Labels are evaluator-authored and are never generated or rewritten by the system under test.

Definitions: **A** is the prompt-only Lumi tutor baseline, with retrieval excluded. **B** is the frozen pre-adaptive Phase-2 RAG baseline (Gemini embedding cosine retrieval over `lesson_slides`, top 3, distance threshold 0.65). **C** is the current adaptive backend: shared Phase-5 planner, assessability, structured proposal, deterministic validation and policy, learner state, deterministic Phase-6 mastery updates, practice attempts, FSRS review scheduling, and review submission. C does not include the Phase-8 frontend. Production retrieval remains `B_legacy`; `B_metadata` and `B_hybrid` are experiments only.

## Offline CI gate

From `spanish_amigo_api`:

```powershell
uv run python -m evals.run_eval phase7-offline --report evals/reports/phase7-offline.json
uv run python -m evals.run_eval planner-offline --report evals/reports/phase5-planner.json
```

These commands have no Gemini, network, production DB, or executable-evaluation-text dependency. They use fixture structured outputs and deterministic application functions; Phase-6 persistence/end-to-end review behaviour is additionally covered by offline SQLite tests with mocked assessment output and controlled timestamps.

The Phase-7 report is machine-readable and records dataset hash, git SHA where available, taxonomy/schema/validator/mastery/policy/FSRS versions, mode, timestamp, retrieval variant, metrics, and stable case-level failure artifacts. Statuses are **MEASURED**, **NOT RUN**, **NOT IMPLEMENTED**, **NOT APPLICABLE**, or **MODEL-JUDGED**.

Metric denominators: Recall@K is relevant slide IDs returned in first K divided by labeled relevant slide IDs; MRR is reciprocal rank of the first relevant result over labeled retrieval cases. Assessability accuracy uses all assessability-labeled cases; precision divides correct assessable predictions by assessable predictions; recall divides them by assessable labels; macro-F1 averages per-label F1. Accepted-evidence precision divides valid accepts by all accepts; rejected-evidence accuracy uses negative validation cases; false accepted evidence rate divides invalid/rejected golden cases accepted by the validator by all such negative cases. Legitimate update success divides expected legitimate mutations that occurred by legitimate-mutation expectations; false mastery-update rate divides mutations where gold says no mutation by no-mutation cases; duplicate-update rate divides duplicate cases producing a second mutation by duplicate cases. Tenancy violation rate divides unauthorized accesses that succeed by unauthorized attempts. Review correctness uses its labeled deterministic review/rating/rejection cases. Schema failure rate is invalid evaluation records divided by records loaded.

Critical zero-violation gates: cross-tenant access, contextual mastery, text-only speech mastery, duplicate mastery mutation, duplicate FSRS update, client-selected mastery/rating, and invalid/rejected evidence mutation. They exist because a false learner-state change is materially more harmful than a missed tutoring preference.

## Measured offline result (2026-09-15)

Phase 7 C backend fixture evaluation: assessability accuracy/precision/recall/macro-F1 1.0; accepted-evidence precision 1.0; false accepted evidence 0.0; policy accuracy/macro-F1 1.0; legitimate update success 1.0; false mastery update 0.0; duplicate update 0.0; bounds violations 0; review deterministic correctness/rating mapping 1.0; tenancy unauthorized-access success 0.0; safety invariant violations 0; run failures 0. These measure deterministic backend fixtures, not learner outcomes or free-form tutor quality. A and B adaptive metrics are **NOT APPLICABLE**. Real retrieval Recall@1/3/K and MRR are **NOT RUN** without a safe local corpus/DB. Latency and tokens are **NOT RUN** unless actually observed.

## Release verification status

Subsequent to the 2026-09-15 offline evaluation run, operational release gates were executed and verified against live infrastructure:

- **PostgreSQL and pgvector migrations**: Verified against live PostgreSQL; production Neon database upgraded to migration head `c6d7e8f9a0b1`. The Adaptive V2 schema defines exact SQLAlchemy tables: `skills`, `lesson_slide_skills`, `lesson_slides`, `learner_skill_states`, `assessment_events`, `practice_attempts`, `review_items`, and `review_history` (with core tables `users`, `completed_lessons`, `chat_sessions`, `chat_messages`, `system_status`).
- **Curriculum seeding and idempotency**: Verified in production; 14 skills in `skills`, 231 slides in `lesson_slides`, and 382 associations in `lesson_slide_skills` seeded with real `gemini-embedding-2` 768-dimensional vectors. Second execution confirmed idempotency (0 inserts, 0 updates, 245 unchanged, 0 failures).
- **Live Gemini assessment**: Verified in production using `gemini-3.1-flash-lite`, confirming structured assessment proposal generation, deterministic validation acceptance/rejection, and audit event persistence in `assessment_events`.
- **Production deployment**: Verified operational on Vercel for both frontend (`https://spanishamigo.vercel.app`) and FastAPI backend (`https://spanish-amigo-api.vercel.app`), with `ADAPTIVE_V2_PLANNER_ENABLED=true` active in production.
- **Retrieval status**: Curriculum retrieval benchmark measured on 2026-09-16 against live PostgreSQL with `gemini-embedding-2`. Production retrieval remains `B_legacy` via `app.services.retrieval.legacy_semantic`; candidate `B_hybrid` via `app.services.retrieval.hybrid` showed statistically distinguishable recall degradation under paired bootstrap analysis and higher retrieval latency, confirming `B_legacy` should be preserved.

## Curriculum retrieval benchmark (2026-09-16)

The curriculum retrieval benchmark uses a dedicated evaluation dataset: `evals/retrieval_benchmark.jsonl` (85 cases total: 75 positive curriculum cases and 10 out-of-scope negative cases; SHA-256 `62be522d7e123517449c5a2959b29aab29375189a21b4836d7f0632db1592c25`). Machine-readable JSON execution reports in `evals/reports/` are intentionally untracked in Git (ignored via `evals/reports/.gitignore`) to maintain clean repository runs; authoritative benchmark evidence, metrics, and methodology are permanently committed here in `EVALUATION.md`.

- **Annotation provenance**: Source-grounded, repository-owned, evaluator-authored, curriculum-validated, not independently human-reviewed.
- **Positive cases (n=75)**: Distributed equally across all 5 curriculum lessons (15 cases each) covering 12 query categories (direct vocabulary, grammar questions, learner errors, paraphrases, natural conversational, English queries, Spanish production, short ambiguous, cross-lesson, near-neighbour, hard distractor, multi-relevant). Authoritative lesson titles derived directly from `lessons_data.json` and `src/data/lessons/`:
  - Lesson 1: *The Ultimate Greeting Masterclass*
  - Lesson 2: *The Magic Verbs (Survival Mode)*
  - Lesson 3: *Polite & Thirsty (Dining 101)*
  - Lesson 4: *Where is it? (The GPS Module)*
  - Lesson 5: *The Ultimate Café Simulation (RPG Mode)*
  All expected slide IDs (231 slides) and skill IDs (14 skills) are cross-validated against `lessons_data.json` and `curriculum_metadata.py`.
- **Negative cases (n=10)**: Global out-of-scope queries (programming/database, calculus, biology, geography, sports, medicine, cooking, economics, foreign languages) with `primary_lesson_id = null` and empty relevance sets.

### Execution commands

Offline verification (no DB or external API access; runs in ~2.0s):
```powershell
uv run python -m unittest tests.test_retrieval_benchmark
```

Live benchmark execution (requires `--confirm-live` to prevent unintentional API/DB quota consumption):
```powershell
uv run python -m evals.run_eval retrieval-benchmark --variants B_legacy B_hybrid targeted_oracle --confirm-live --report evals/reports/retrieval_benchmark.json
```

Smoke test with limit:
```powershell
uv run python -m evals.run_eval retrieval-benchmark --limit 5 --confirm-live --report evals/reports/retrieval_benchmark_smoke.json
```

### Measured benchmark results (configured Neon PostgreSQL, gemini-embedding-2)

#### Positive Retrieval Metrics (n=75 positive cases)

| Variant | Role | Hit@1 | Hit@3 | Recall@1 | Recall@3 | MRR | Failure Count (0 hits) |
|---|---|---|---|---|---|---|---|
| `B_legacy` | Baseline (Production, `legacy_semantic`) | 0.6533 | 0.8400 | 0.4111 | 0.6467 | 0.7356 | 12 / 75 |
| `B_hybrid` | Candidate (Semantic + Lexical RRF, `hybrid`) | 0.6400 | 0.8133 | 0.4011 | 0.6000 | 0.7133 | 14 / 75 |
| `targeted_oracle` | Experiment (Oracle skill-conditioned) | 0.6667 | 0.8533 | 0.4178 | 0.6767 | 0.7511 | 11 / 75 |

#### Negative Abstention Metrics (n=10 out-of-scope cases)

| Variant | Abstention Accuracy (0 slides returned) | False Positive Rate (>=1 slides returned) | Mean Incorrect Slides |
|---|---|---|---|
| `B_legacy` | 0.0 (0/10) | 1.0 (10/10) | 3.0 |
| `B_hybrid` | 0.0 (0/10) | 1.0 (10/10) | 3.0 |
| `targeted_oracle` | N/A (NOT APPLICABLE)* | N/A (NOT APPLICABLE)* | N/A* |

*\*Note: `targeted_oracle` is an oracle-conditioned experiment requiring a ground-truth target skill label. For out-of-scope negative cases, no relevant skill exists (oracle conditioning is undefined). Returning zero slides from an empty-skill query is an artifact of empty skill filtering, not evidence that the model can correctly abstain in production. The negative abstention metric is therefore reported as N/A / NOT APPLICABLE.*

#### Benchmark Latency Measurements (sample count n=85)

- **Gemini Query Embedding Duration**: Mean = 715.4 ms (external Gemini API embedding generation).
- **Database Retrieval Duration (excluding embedding)**:
  - `B_legacy`: Mean = 166.1 ms
  - `B_hybrid`: Mean = 272.0 ms (+63.7% latency overhead)
  - `targeted_oracle`: Mean = 173.6 ms

### Paired bootstrap confidence intervals (B_hybrid vs B_legacy, 1,000 resamples, 95% CI on positive cases n=75)

- **Hit@3 delta**: -0.0267 (95% CI [-0.0667, 0.0000]; interval includes zero on the upper boundary).
- **MRR delta**: -0.0222 (95% CI [-0.0578, +0.0133]; interval includes zero).
- **Recall@3 delta**: -0.0467 (95% CI [-0.0933, -0.0133]; **the 95% paired bootstrap confidence interval strictly excludes zero**, demonstrating that the observed recall degradation is statistically distinguishable from zero under this bootstrap interval).

### Empirical findings and production recommendation

1. **`B_hybrid` underperforms `B_legacy`**: Lexical search in `app.services.retrieval.lexical` uses `func.websearch_to_tsquery('simple', query)`. The PostgreSQL `'simple'` dictionary does not stem words or remove stopwords. For multi-word queries, if any unstemmed token is missing, the Boolean `&` tsquery fails. When common tokens match, unconstrained RRF promotes literal matches from unrelated lessons, degrading Recall@3 by 4.67 percentage points while increasing database query duration by ~64% (272.0 ms vs 166.1 ms).
2. **`targeted_oracle` provides modest upper-bound uplift**: Pre-filtering on the gold skill ID improves Hit@3 by +1.33% and Recall@3 by +3.00% on positive cases. For out-of-scope negative queries, oracle conditioning is undefined (there is no oracle skill label for a true out-of-scope negative query); its negative abstention is therefore reported as N/A / NOT APPLICABLE rather than production-capable abstention. Because oracle skill labels do not exist in general conversational chat, this represents an experimental upper bound, not a deployable production configuration.
3. **Production recommendation**: Keep `B_legacy` (`legacy_semantic`) as the authoritative production retrieval strategy. Existing alternatives do not justify a production change. Production retrieval in `app/services/ai.py` remains unchanged.

## Explicit opt-in live/integration evaluation

```powershell
uv run python -m evals.run_eval live-assessment-smoke --limit 5 --confirm-live --report evals/reports/live-c-smoke.json
uv run python -m evals.run_eval live-model --baseline A --limit 5 --confirm-live --report evals/reports/live-a.json
uv run python -m evals.run_eval live-model --baseline B --limit 5 --confirm-live --report evals/reports/live-b.json
uv run python -m evals.run_eval db-retrieval --variant B_legacy --confirm-live --report evals/reports/db-retrieval.json
```

Live tutoring quality is optional and must identify provider/model/config and label any judge result **MODEL-JUDGED**. Use the versioned rubric dimensions correctness, curriculum grounding, pedagogical usefulness, level appropriateness, directness, hallucination, and unnecessary adaptation/interruption; prefer blinded pairwise A/B/C comparisons. A judge is supplementary, never the sole signal or CI requirement. The real DB commands are read-only and require `--confirm-live`.

Known limitations: The Phase 7 offline test harness evaluates deterministic backend fixtures and deliberately excludes external networks, live model APIs, and database engines. The 2026-09-16 curriculum retrieval benchmark evaluated live PostgreSQL and Gemini embeddings under read-only conditions, confirming that hybrid lexical-semantic RRF does not outperform legacy vector retrieval on this curriculum. Model-judged live tutoring quality was not measured. The offline scenario runner complements rather than replaces live integration tests.
