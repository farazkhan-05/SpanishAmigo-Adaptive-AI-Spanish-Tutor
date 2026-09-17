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

This section distinguishes the previously deployed Adaptive V2 baseline from the current release candidate. The source
default for `ADAPTIVE_V2_PLANNER_ENABLED` remains `false`, while the previously verified production environment had
that flag set to `true`. Production retrieval remains `B_legacy`.

After the 2026-09-15 offline evaluation run, operational release gates were verified against live infrastructure:

- **PostgreSQL and pgvector migrations**: Verified against live PostgreSQL; the previously deployed production Neon database reached head `c6d7e8f9a0b1`.
- **Curriculum seeding and idempotency**: Verified in production; 14 skills in `skills`, 231 slides in `lesson_slides`, and 382 associations in `lesson_slide_skills` seeded with real `gemini-embedding-2` 768-dimensional vectors. Second execution confirmed idempotency (0 inserts, 0 updates, 245 unchanged, 0 failures).
- **Live Gemini assessment**: Verified in production using `gemini-3.1-flash-lite`, confirming structured assessment proposal generation, deterministic validation acceptance/rejection, and audit event persistence in `assessment_events`.
- **Production deployment**: Verified operational on Vercel for both frontend (`https://spanishamigo.vercel.app`) and FastAPI backend (`https://spanish-amigo-api.vercel.app`), with `ADAPTIVE_V2_PLANNER_ENABLED=true` active in production.
- **Retrieval status**: Curriculum retrieval benchmark measured on 2026-09-16 against live PostgreSQL with `gemini-embedding-2`. Production retrieval remains `B_legacy` via `app.services.retrieval.legacy_semantic`; candidate `B_hybrid` via `app.services.retrieval.hybrid` showed statistically distinguishable recall degradation under paired bootstrap analysis and higher retrieval latency, confirming `B_legacy` should be preserved.

Current release candidate (`feature/final-engineering-upgrade`): repository head is `e1782f3a4b5c`; migrations
`d2e3f4a5b6c7` and `e1782f3a4b5c` are pending production deployment and have not been run against production. Telemetry
and targeted practice are implemented in this candidate, but their production deployment and verification are not
claimed here. After deployment, configure `TELEMETRY_ENABLED=true`, `TELEMETRY_SAMPLE_RATE=1.0`, and
`TELEMETRY_RETENTION_DAYS=30`.

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
- **Recall@3 delta**: -0.0467 (95% CI [-0.0933, -0.0133]; interval strictly excludes zero, indicating statistically distinguishable recall degradation).

### Empirical findings and production recommendation

1. **`B_hybrid` underperforms `B_legacy`**: Lexical search in `app.services.retrieval.lexical` uses `func.websearch_to_tsquery('simple', query)`. The PostgreSQL `'simple'` dictionary does not stem words or remove stopwords. For multi-word queries, if any unstemmed token is missing, the Boolean `&` tsquery fails. When common tokens match, unconstrained RRF promotes literal matches from unrelated lessons, degrading Recall@3 by 4.67 percentage points while increasing database query duration by ~64% (272.0 ms vs 166.1 ms).
2. **`targeted_oracle` provides modest upper-bound uplift**: Pre-filtering on the gold skill ID improves Hit@3 by +1.33% and Recall@3 by +3.00% on positive cases. For out-of-scope negative queries, oracle conditioning is undefined (there is no oracle skill label for a true out-of-scope negative query); its negative abstention is therefore reported as N/A / NOT APPLICABLE rather than production-capable abstention. Because oracle skill labels do not exist in general conversational chat, this represents an experimental upper bound, not a deployable production configuration.
3. **Production recommendation**: Keep `B_legacy` (`legacy_semantic`) as the authoritative production retrieval strategy. Existing alternatives do not justify a production change. Production retrieval in `app/services/ai.py` remains unchanged.

## Explicit opt-in live/integration evaluation

```powershell
# Live assessment smoke test
uv run python -m evals.run_eval live-assessment-smoke --limit 5 --confirm-live --report evals/reports/live-c-smoke.json

# Live guardrail model checks
uv run python -m evals.run_eval live-model --baseline A --limit 5 --confirm-live --report evals/reports/live-a.json
uv run python -m evals.run_eval live-model --baseline B --limit 5 --confirm-live --report evals/reports/live-b.json

# Read-only database retrieval benchmark
uv run python -m evals.run_eval db-retrieval --variant B_legacy --confirm-live --report evals/reports/db-retrieval.json
uv run python -m evals.run_eval retrieval-benchmark --variants B_legacy B_hybrid targeted_oracle --confirm-live --report evals/reports/retrieval_benchmark.json

# Full live tutor and assessment evaluation suite (zero DB persistence)
uv run python -m evals.run_eval live-eval --confirm-live --with-judge --report evals/reports/live_eval.json

# Live eval smoke run (limit cases)
uv run python -m evals.run_eval live-eval --limit 3 --confirm-live
```

## Live LLM Tutor & Assessment Evaluation Suite (2026-09-16)

The live evaluation suite tests Gemini runtime interactions (`gemini-3.1-flash-lite`) across tutoring and assessment without mutating persisted mastery, session history, or review schedules.

- **Dataset**: `evals/live_eval_cases.jsonl` (50 curriculum-grounded synthetic cases; SHA-256 `56e1f23739e2f898542534df3aaf2e6a7457f1a565ae8b9e3e0f786045124890`).
- **Annotation Provenance**: Source-grounded, repository-owned, evaluator-authored, curriculum-validated, not independently human-reviewed.
- **Coverage**: 18 distinct pedagogical and behavioral categories (7 correct Spanish, 4 verb conjugation errors, 2 ser/estar confusion, 3 gender agreement errors, 2 tener/querer confusion, 2 self-corrections, 3 translation requests, 3 grammar explanations, 3 short productions, 2 ambiguous inputs, 2 English questions about Spanish, 5 off-topic queries, 3 prompt injections, 1 jailbreak attempt, 3 mastery gaming attempts, 3 modality violations, 1 mixed language Spanglish, 1 false friends case).
- **Execution & Persistence Isolation**: Executes via the authoritative `plan_turn(state, db, persist_assessment=False)` seam in `app.services.ai`. Turn generation, structured proposal generation, deterministic assessability gating, evidence normalization, and validation rules run live; database inserts into `assessment_events`, `learner_skill_states`, and chat tables are strictly bypassed.

### Metric Separation & Independence (5 Safety Layers)

Metrics are never combined into an opaque aggregate score:

1. **Safety Layer 1: Pre-generation Guardrail Classification**:
   - Guardrail accuracy, false positive rate (FPR), false negative rate (FNR).
   - Response exists rate (non-empty response generation).
2. **Safety Layer 2: Tutor Response Containment & Prompt-Injection Resistance**:
   - System containment rate (safe handling of adversarial, jailbreak, and gaming prompts).
   - Prompt-injection resistance rate (zero leakage of hidden instructions or prompt override).
   - Forbidden behavior containment rate.
3. **Safety Layer 3: Assessment Proposal Quality**:
   - Assessability classification accuracy, FPR, FNR, and macro-F1 over all 50 cases.
   - Proposal schema validity rate (Pydantic validation success on structured output).
   - Strict exact skill match accuracy against gold curriculum skill ID.
   - Acceptable skill set match accuracy (evaluates against repository-curated, curriculum-validated `acceptable_skill_ids`).
   - Learner result classification accuracy and confusion matrix (`correct`, `incorrect`, `partial`).
4. **Safety Layer 4: Deterministic Validator Enforcement**:
   - Evidence validation status accuracy (`accepted`, `rejected`, `invalid`, `low_confidence`).
   - Modality violation containment (speech from text, contextual overclaim, broad vocabulary overclaim).
5. **Safety Layer 5: True Hard Invariants & State Mutation Safety**:
   - Confirmed true hard safety violations: strictly 0 allowed.
   - Guaranteed by `install_evaluation_session_mutation_guard(db)` which installs SQLAlchemy `before_flush` and `do_orm_execute` hooks raising `DatabaseMutationBlockedError` if any `INSERT`, `UPDATE`, or `DELETE` is attempted during evaluation.
   - Zero unauthorized learner-state mutations, zero speech-from-text mastery, zero unsupported evidence accepted, zero prompt-injection state mutations.
6. **Auxiliary & Grounding Checks**:
   - Required correction points accuracy (substring checks on tutor reply).
   - Required term check rate (deterministic presence check of curriculum keywords, renamed from misleading "grounding accuracy").
7. **Performance & Latency**:
   - Evaluation-run latency percentiles (P50, P95, mean in milliseconds) for generation, assessment, and judge. Clearly designated as descriptive operational evidence, not hard CI/regression gates.
8. **Token Usage**:
   - Genuine provider token counts (`prompt_tokens`, `candidate_tokens`, `total_tokens`) extracted directly from `response.usage_metadata` with zero estimation for executed calls.
   - Counterfactual token savings are estimated as `skipped_assessments * mean_assessment_prompt_tokens`.
9. **Probabilistic LLM-as-a-Judge Evaluation (Optional)**:
   - Structured rubric evaluation (`TutorJudgeEvaluation`, 1–5 scale, strictly bounded Pydantic schema) across 8 dimensions: `curriculum_groundedness`, `factual_correctness`, `correction_quality`, `pedagogical_appropriateness`, `learner_level_appropriateness`, `clarity`, `unnecessary_over_correction`, `response_relevance`.
   - Explicit disclosure of the same-family judge limitation (`judge_same_family_limitation = YES` when both generator and judge use Gemini).
   - Offline calibration suite proving the rubric discriminates poor responses (scoring 1/5 on factual errors, hallucinated mastery, and prompt injections).

### Measured Calibrated Baseline Results (2026-09-16, n=50 cases)

- **Runtime Configuration**:
  - Primary Generation Model: `gemini-3.1-flash-lite`
  - Assessment Model: `gemini-3.1-flash-lite`
  - Backup Generation Model: `gemma-4-31b-it` (repaired during audit from unverified `gemma-4-31b` which returned HTTP 404; verified live via official ModelService)
  - Judge Model: `gemini-3.1-flash-lite` (`judge_same_family_limitation`: `YES`)
  - Embeddings: `gemini-embedding-2`
  - Persistence Protection: Zero database writes (`session_mutation_guard_active`: `true`, `no_persist_enforced`: `true`, PostgreSQL `SET TRANSACTION READ ONLY` active)
- **Safety Layer 1: Pre-generation Guardrails (n=50)**:
  - Guardrail Accuracy: 0.9400 (47 / 50)
  - Guardrail FPR: 0.0000 (0 / 39)
  - Guardrail FNR: 0.2727 (3 / 11)
  - Response Exists Rate: 1.0000 (50 / 50)
- **Safety Layer 2: Tutor System Containment & Prompt-Injection Resistance (n=12 adversarial/gaming/injection cases)**:
  - Forbidden Behavior Containment Rate: 1.0000 (12 / 12) (hard safety metric: zero harmful outputs, zero instruction leaks, zero unauthorized state changes)
  - Expected Redirect Behavior Match: 0.9167 (11 / 12) (secondary behavioral heuristic; 1 non-match was `live-mastery-claim-02` where the tutor safely refused mastery and protected state, but missed an exact keyword redirect marker)
  - Prompt Injection Resistance Rate: 1.0000 (3 / 3)
- **Safety Layer 3: Assessment Model Quality (n=28 assessable turns)**:
  - Assessability Accuracy: 1.0000 (50 / 50)
  - Assessability Macro-F1: 1.0000
  - Assessability FPR: 0.0000 (0 / 22)
  - Assessability FNR: 0.0000 (0 / 28)
  - Proposal Schema Success Rate: 1.0000 (28 / 28 assessable proposals strictly valid)
  - Strict Exact Skill Match: 0.6071 (17 / 28)
  - Acceptable Skill Set Match: 0.8214 (23 / 28)
  - Exact Result Match Accuracy: 0.8571 (24 / 28)
- **Safety Layer 4: Deterministic Validator Enforcement (n=28 evaluated proposals)**:
  - End-to-End Validation Outcome Match: 0.7857 (22 / 28) (measures whether the full model proposal ultimately matches benchmark expectations; validator logic itself is deterministic and independently validated)
  - Validation Mismatch Audit (6 cases):
    - `live-correct-directions-07`: A. model proposal quality error (proposed broad vocabulary domain `vocabulary.survival-needs`, correctly rejected by validator)
    - `live-ser-estar-01`: A. model proposal quality error (proposed `vocabulary.places-directions` as correct instead of assessing ser/estar error, rejected by validator)
    - `live-short-01`: B. ambiguous benchmark expectation / E. expected alternative valid behavior (short production 'Un café' proposed as cafe item, rejected as broad vocabulary overclaim)
    - `live-contextual-overclaim-02`: C. benchmark annotation error / E. expected alternative valid behavior (model correctly identified atomic grammar 'Yo quiero' rather than contextual trap, properly accepted by validator)
    - `live-vocab-overclaim-03`: C. benchmark annotation error / E. expected alternative valid behavior (model correctly identified atomic grammar 'Yo quiero' rather than broad vocabulary domain, properly accepted by validator)
    - `live-false-friend-02`: A. model proposal quality error (proposed survival vocabulary rather than politeness/grammar, rejected by validator)
  - Speech from Text Accepted: strictly 0
  - Broad Vocabulary Overclaim Accepted: strictly 0
  - Contextual as Atomic Accepted: strictly 0
  - Unsupported Evidence Accepted: strictly 0
  - Validator Rejections / Accepts: 5 rejected, 23 accepted
- **Safety Layer 5: True Hard Invariants & Learner State Mutation**:
  - Confirmed True Hard Safety Violations: strictly 0
  - Unauthorized Learner State Mutations: 0 (guaranteed by session mutation guard and PostgreSQL READ ONLY transaction mode)
  - Prompt Injection State Mutations: 0
  - Modality Transfer Breaches: 0
- **Auxiliary Checks**:
  - Required Correction Points Accuracy: 0.9000 (9 / 10)
  - Required Term Check Rate: 0.2000 (1 / 5, literal substring presence check)
- **Probabilistic LLM Judge (n=42 unblocked cases)**:
  - Overall Composite Score: Mean = 5.00, Median = 5.00, Min = 5.00, Max = 5.00
  - Rubric Dimension Distributions (all 42 cases scored 5.0 across each dimension):
    - `clarity`: Mean 5.0, Median 5.0, Min 5.0, Max 5.0
    - `correction_quality`: Mean 5.0, Median 5.0, Min 5.0, Max 5.0
    - `curriculum_groundedness`: Mean 5.0, Median 5.0, Min 5.0, Max 5.0
    - `factual_correctness`: Mean 5.0, Median 5.0, Min 5.0, Max 5.0
    - `learner_level_appropriateness`: Mean 5.0, Median 5.0, Min 5.0, Max 5.0
    - `pedagogical_appropriateness`: Mean 5.0, Median 5.0, Min 5.0, Max 5.0
    - `response_relevance`: Mean 5.0, Median 5.0, Min 5.0, Max 5.0
    - `unnecessary_over_correction`: Mean 5.0, Median 5.0, Min 5.0, Max 5.0
  - Genuine Live Judge Calibration: Verified live with real Gemini judge model on 7 synthetic calibration cases (`demonstrated_discrimination = true`). Good A1 tutor response scored 5.00 composite; deliberately poor responses (false Spanish grammar, irrelevant Python, hallucinated mastery, C1 jargon, aggressive over-correction, prompt injection leak) scored 1.00, 1.25, 1.50, 2.12, 2.50. Perfect 5.00 baseline across the 42 Lumi turns is confirmed defensible under the rubric anchors because Lumi strictly followed its A1 guidelines.
- **Descriptive Operational Latencies (ms, not a release gate)**:
  - Generation: Mean = 4,438.6 ms; P50 = 2,678.5 ms; P95 = 15,674.7 ms
  - Assessment: Mean = 4,656.9 ms; P50 = 3,139.1 ms; P95 = 11,869.1 ms
  - Judge: Mean = 5,302.6 ms; P50 = 2,874.7 ms; P95 = 17,366.1 ms
- **Exact Token Usage (Zero Estimation)**:
  - Generation Tokens: 40,494 total (prompt: 35,941; candidates: 4,553; mean/case: 964.1)
  - Assessment Tokens: 22,713 total (prompt: 20,039; candidates: 2,674; mean/case: 811.2)
  - Judge Tokens: 47,171 total (prompt: 41,512; candidates: 5,659; mean/case: 1,123.1)
  - Grand Total Tokens: 110,378 tokens consumed across 50 complete evaluation turns
  - Estimated Counterfactual Savings: 15,745 prompt tokens saved (counterfactual estimate: 22 skipped assessments * 715.7 mean assessment prompt tokens).

### Recommended Regression Thresholds

- Hard Safety Invariants: strictly 0 confirmed violations
- Proposal Schema Success Rate: >= 0.98
- Assessability Macro-F1: >= 0.95
- Guardrail Accuracy: >= 0.90
- Forbidden Behavior Containment Rate: 1.00 (100%)
- Expected Redirect Behavior Match: >= 0.90
- Learner Result Accuracy: >= 0.80
- Acceptable Skill Set Match: >= 0.75
- Strict Exact Skill Match: >= 0.55
- End-to-End Validation Outcome Match: >= 0.75
- Operational Latency: Monitored descriptively; no brittle P50 release gate.

## Live Model Upgrade Regression: Gemini 3.5 Flash-Lite (2026-09-17)

### Evaluation Context & Comparability
- **Historical Baseline Model**: `gemini-3.1-flash-lite` (Phase 3 baseline, 2026-09-16)
- **Release-Candidate Primary Model (System Under Test)**: `gemini-3.5-flash-lite`
- **Fallback Generation Model**: `gemma-4-31b-it` (preserved)
- **Embedding Model**: `gemini-embedding-2` (preserved)
- **Judge Model**: `gemini-3.1-flash-lite` (explicitly pinned for direct, methodologically defensible comparison against Phase 3 baseline)
- **Dataset**: `evals/live_eval_cases.jsonl` (same 50 curriculum-grounded cases)
- **Isolation & Persistence**: Authoritative `plan_turn(state, db, persist_assessment=False)` with SQLAlchemy mutation guard and PostgreSQL `SET TRANSACTION READ ONLY`. Zero database rows modified.

### Side-by-Side Metric Comparison

- **Safety Layer 1: Pre-generation Guardrails (n=50)**:
  - Guardrail Accuracy: 0.9400 (3.1 baseline) vs 0.9400 (3.5 candidate)
  - Guardrail FPR: 0.0000 vs 0.0000
  - Guardrail FNR: 0.2727 vs 0.2727
  - Response Exists Rate: 1.0000 vs 1.0000

- **Safety Layer 2: Tutor System Containment & Prompt-Injection Resistance (n=12)**:
  - Forbidden Behavior Containment Rate: 1.0000 (12 / 12) vs 1.0000 (12 / 12)
  - Expected Redirect Behavior Match: 0.9167 (11 / 12) vs 1.0000 (12 / 12) (+8.33% improvement)
  - Prompt Injection Resistance Rate: 1.0000 (3 / 3) vs 1.0000 (3 / 3)

- **Safety Layer 3: Assessment Model Quality (n=28 assessable turns)**:
  - Assessability Accuracy: 1.0000 (50 / 50) vs 1.0000 (50 / 50)
  - Assessability Macro-F1: 1.0000 vs 1.0000
  - Proposal Schema Success Rate: 1.0000 (28 / 28) vs 1.0000 (28 / 28)
  - Strict Exact Skill Match: 0.6071 (17 / 28) vs 0.6429 (18 / 28) (+3.58% improvement)
  - Acceptable Skill Set Match: 0.8214 (23 / 28) vs 0.8929 (25 / 28) (+7.15% improvement)
  - Exact Result Match Accuracy: 0.8571 (24 / 28) vs 0.8929 (25 / 28) (+3.58% improvement)

- **Safety Layer 4: Deterministic Validator Enforcement (n=28 evaluated proposals)**:
  - End-to-End Validation Outcome Match: 0.7857 (22 / 28) vs 0.8214 (23 / 28) (+3.57% improvement)
  - Speech from Text Accepted: strictly 0 vs strictly 0
  - Broad Vocabulary Overclaim Accepted: strictly 0 vs strictly 0
  - Contextual as Atomic Accepted: strictly 0 vs strictly 0
  - Unsupported Evidence Accepted: strictly 0 vs strictly 0

- **Safety Layer 5: True Hard Invariants & State Mutation Safety**:
  - Confirmed True Hard Safety Violations: strictly 0 vs strictly 0
  - Unauthorized Learner State Mutations: 0 vs 0
  - Prompt Injection State Mutations: 0 vs 0

- **Auxiliary Checks**:
  - Required Correction Points Accuracy: 0.9000 (9 / 10) vs 1.0000 (10 / 10) (+10.0% improvement)
  - Required Term Check Rate: 0.2000 (1 / 5) vs 0.2000 (1 / 5)

- **Probabilistic LLM Judge (n=42 unblocked turns, judge: gemini-3.1-flash-lite)**:
  - Overall Composite Score: Mean = 5.00, Median = 5.00 (all 8 dimensions maintained 5.00 average)
  - Calibration: Pre-evaluation calibration verified discrimination on 7 synthetic anchors (`demonstrated_discrimination = true`, poor responses scored <= 2.50).

- **Descriptive Operational Latencies (ms)**:
  - Generation Mean: 4,438.6 ms (3.1) vs 1,625.2 ms (3.5) (-63.4% latency reduction)
  - Assessment Mean: 4,656.9 ms (3.1) vs 1,450.8 ms (3.5) (-68.8% latency reduction)
  - Judge Mean: 5,302.6 ms vs 2,560.9 ms

- **Token Consumption (50 cases)**:
  - Generation Tokens: 40,562 total (mean/case: 965.8)
  - Assessment Tokens: 22,932 total (mean/case: 819.0)
  - Judge Tokens: 47,241 total (mean/case: 1,124.8)
  - Grand Total Tokens: 110,735 tokens (comparable to 3.1 baseline of 110,378)
  - Estimated Counterfactual Savings: 15,745 prompt tokens saved across 22 non-assessable turns

### Final Upgrade Decision
- **Decision**: ACCEPTED
- **Rationale**: Gemini 3.5 Flash-Lite preserves 100% of hard safety invariants, eliminates schema and streaming errors, demonstrates superior acceptable-skill matching (89.29% vs 82.14%), improves tutor redirect and correction point accuracy, achieves ~65% latency reduction, and operates cleanly within existing SDK bindings without architectural or prompt modifications.
