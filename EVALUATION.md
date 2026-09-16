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

- **PostgreSQL and pgvector migrations**: Verified against live PostgreSQL; production Neon database upgraded to migration head `c6d7e8f9a0b1`.
- **Curriculum seeding and idempotency**: Verified in production; 14 skills, 231 slides, and 382 associations seeded with real `gemini-embedding-2` 768-dimensional vectors. Second execution confirmed idempotency (0 inserts, 0 updates, 245 unchanged, 0 failures).
- **Live Gemini assessment**: Verified in production using `gemini-3.1-flash-lite`, confirming structured assessment proposal generation, deterministic validation acceptance/rejection, and audit event persistence.
- **Production deployment**: Verified operational on Vercel for both frontend (`https://spanishamigo.vercel.app`) and FastAPI backend (`https://spanish-amigo-api.vercel.app`), with `ADAPTIVE_V2_PLANNER_ENABLED=true` active in production.
- **Retrieval status**: Real retrieval quality measurement (Recall@K, MRR) against a representative labeled production-like PostgreSQL corpus remains **NOT RUN**. Production retrieval remains `B_legacy`; `B_metadata` and `B_hybrid` remain evaluation experiments.

## Explicit opt-in live/integration evaluation

```powershell
uv run python -m evals.run_eval live-assessment-smoke --limit 5 --confirm-live --report evals/reports/live-c-smoke.json
uv run python -m evals.run_eval live-model --baseline A --limit 5 --confirm-live --report evals/reports/live-a.json
uv run python -m evals.run_eval live-model --baseline B --limit 5 --confirm-live --report evals/reports/live-b.json
uv run python -m evals.run_eval db-retrieval --variant B_legacy --report evals/reports/db-retrieval.json
```

Live tutoring quality is optional and must identify provider/model/config and label any judge result **MODEL-JUDGED**. Use the versioned rubric dimensions correctness, curriculum grounding, pedagogical usefulness, level appropriateness, directness, hallucination, and unnecessary adaptation/interruption; prefer blinded pairwise A/B/C comparisons. A judge is supplementary, never the sole signal or CI requirement. The real DB command is read-only and must target only a known safe local database; it is not run automatically.

Known limitations: The Phase 7 offline test harness evaluates deterministic backend fixtures and deliberately excludes external networks, live model APIs, and database engines. Fixture retrieval is not a pgvector benchmark, and real retrieval quality metrics (Recall@K, MRR) remain NOT RUN pending a representative labeled PostgreSQL benchmark corpus. Model-judged live tutoring quality was not measured. While PostgreSQL migrations, curriculum seeding, and live Gemini assessment were subsequently verified during production release gates, the offline scenario runner itself complements rather than replaces live integration tests.
