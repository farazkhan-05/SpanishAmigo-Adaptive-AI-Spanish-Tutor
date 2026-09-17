# Adaptive V2 pre-release audit (archival record)

> **Archival status note**: This document preserves the historical pre-release audit conducted on 2026-09-15 against baseline commit `b2a9a42` on `feature/adaptive-v2`, prior to production release gate execution. The original pre-release verdict of FAIL is preserved below as historical evidence. All mandatory release and activation gates identified in this audit were subsequently completed and verified in production. The pre-release findings below no longer represent current production status.

## Post-audit gate closure

Following this audit, mandatory release gates were executed and verified against live infrastructure:

1. **PostgreSQL migration chain verified**: The then-current Adaptive V2 Alembic sequence was verified against live PostgreSQL and pgvector. The previously deployed production Neon database successfully reached head `c6d7e8f9a0b1`; this archival closure does not include later release-candidate migrations `d2e3f4a5b6c7` or `e1782f3a4b5c`.
2. **Curriculum seeding and idempotency verified**: `seed_embeddings.py` populated 14 skills, 231 lesson slides, and 382 lesson-to-skill associations (222 mapped slides, 9 intentionally unmapped slides) with real 768-dimensional `gemini-embedding-2` vectors. Second execution verified seeder idempotency: 0 inserts, 0 updates, 245 unchanged, 0 regenerated embeddings, and 0 failures.
3. **Live Gemini structured assessment verified**: Production `/chat/send` verification with `gemini-3.1-flash-lite` confirmed live structured assessment proposal generation, deterministic validation, and audit event persistence. Tested live cases confirmed:
   - Correct production (*"Yo quiero un café, por favor"*) generated an accepted assessment event for `grammar.present-tense-querer`.
   - Incorrect production (*"Yo tener dos hermanos"*) generated an accepted assessment event for `grammar.present-tense-tener`.
   - Information questions did not become mastery evidence.
   - Typed text regarding silent-H knowledge could not create pronunciation mastery.
4. **Backend deployment verified**: Backend deployment verified operational on Vercel (`https://spanish-amigo-api.vercel.app`), with `/health` returning HTTP 200.
5. **Adaptive V2 planner activated**: `ADAPTIVE_V2_PLANNER_ENABLED=true` enabled in Vercel production environment; live `/adaptive/state` and `/adaptive/reviews/due` endpoints verified operational.
6. **Production smoke tests passed**: My Spanish and full course journey verified against live production.
7. **Retrieval boundary maintained**: Real retrieval quality measurement using a representative labeled production-like PostgreSQL corpus remains NOT RUN. Production retrieval remains `B_legacy`; `B_metadata` and `B_hybrid` remain experiments.

This closure describes the historical Adaptive V2 deployment baseline only. The current `feature/final-engineering-upgrade`
release candidate has repository head `e1782f3a4b5c`; its telemetry and targeted-practice migrations remain pending
production deployment and are not covered by the historical production verification above.

---

## Historical pre-release audit findings (2026-09-15)

Audit date: 2026-09-15. Audited commit baseline: `b2a9a42` on `feature/adaptive-v2`.

### Findings and fixes

- MEDIUM (fixed): an accepted independent `partial` review assessment had no FSRS rating and therefore aborted its otherwise valid transaction. Partial recall now maps to the conservative `Hard` rating, with endpoint coverage.
- MEDIUM (fixed): concurrent first accepted events for one learner could both observe absent learner-state/review-card rows. `process_accepted_evidence` now locks the verified owner row before reading or creating authoritative state.
- MEDIUM (fixed): the historical chat-session migration created an unnamed foreign key and attempted to drop a constraint named `None`. It now explicitly uses PostgreSQL's legacy default name, `chat_messages_session_id_fkey`, allowing fresh and previously upgraded PostgreSQL chains to resolve the same downgrade target.
- LOW: Vite emits a 1.36 MB minified JavaScript chunk warning and Browserslist data is stale. Neither changes adaptive authority or release safety.

No HIGH finding was confirmed. No frontend redesign, feature activation change, commit, or push was made.

### Source audit verdicts

- Auth and tenancy: Firebase `verify_id_token` provides the UID. Adaptive state, review queries/start/submit, events, attempts, cards, and history are UID-scoped; guessed review IDs and attempt IDs fail. Existing progress and chat ownership checks remain. Anonymous Firebase users follow the authenticated UID path, and Google linking/fallback behavior is unchanged.
- Assessment/evidence: Gemini returns a strict, reasoning-free proposal only. The application gate, taxonomy/mode/domain checks, concrete-result requirement, conservative evidence grounding, and 0.80 application threshold control acceptance. NFC/case/whitespace/punctuation normalization preserves accents and negation tokens. No free-form model output writes mastery.
- Mastery/review: `process_accepted_evidence` is the sole state/card/history writer. It requires accepted atomic text evidence and a linked non-exposure server attempt, bounds estimate/confidence, persists immutable card transitions, and uses `review_history.assessment_event_id` for duplicate safety. Ratings remain server-owned: Again incorrect independent, Hard partial or assisted correct, Good correct independent, never Easy automatically. FSRS is pinned to `6.3.2`, uses UTC and disabled fuzzing.
- Send/stream: both use `plan_turn` before generation. Stream delivery alone differs and retains `session_id`, token, optional `action_required`, and `[DONE]` framing.
- Retrieval/taxonomy: production remains `B_legacy`; metadata semantic and hybrid are not activated. RRF has stable dedup/tie breaking. The static `spanishamigo-v1` taxonomy has 14 skills, no prerequisites, and correctly preserves text, speech-required, and contextual semantics.
- Frontend: My Spanish is additive below CourseJourney. It separates course completion from mastery, presents unknown/speech/contextual/vocabulary states honestly, derives exercises/results/rationale from the server, prevents duplicate submissions in-flight, and uses no authoritative adaptive local storage or `dangerouslySetInnerHTML`.

### Validation performed

- `uv run python -m unittest discover -s tests -p "test_*.py"`: **89 passed**.
- Phase-7 offline evaluation: **MEASURED, 68 cases, 0 failures**. Critical safety/tenancy/duplicate rates were zero; real retrieval remains NOT RUN.
- Phase-5 planner offline evaluation: **MEASURED, 20 cases, 0 failures**.
- Required mypy command: **Success: no issues found in 4 source files**.
- `npm.cmd run lint`: **PASS**.
- `npm.cmd run build`: **PASS** (non-blocking bundle-size and stale Browserslist warnings).
- `npm.cmd audit --omit=dev --audit-level=high`: initially found a critical websocket-driver issue, high gRPC and React Router issues, and a moderate protobufjs issue. `npm audit fix --package-lock-only --omit=dev` updated the official npm-registry lockfile artifacts: websocket-driver 0.7.5, @grpc/grpc-js 1.9.16, protobufjs 7.6.6, react-router/react-router-dom 7.18.3. Re-audit: **0 vulnerabilities**.
- `git diff --check`: **PASS**.

The Python lockfile pins `fsrs==6.3.2` to `files.pythonhosted.org` artifacts and hashes. PyPI identifies it as Py-FSRS from open-spaced-repetition; its upstream advisory page had no published advisories at audit time. Mypy was obtained only from official PyPI after provenance/advisory review; no security-tool detection occurred.

### Unverified items at audit time

- **POSTGRESQL MIGRATION EXECUTION: NOT VERIFIED.** No repository disposable database exists; Docker, `psql`, and `pg_ctl` are unavailable. No unknown/shared configured database was touched. Thus live PostgreSQL pgvector DDL, constraints, generated tsvector/GIN behavior, full downgrade/re-upgrade, and seed rollback were not executed.
- **CURRICULUM BACKFILL/IDEMPOTENCY: statically verified, not live-PostgreSQL executed.** `seed_embeddings.py` uses PostgreSQL upserts, retains embeddings when source content is unchanged, does not drop/truncate tables, and rolls back on error. Live repeated-run, changed-source, and rollback validation need the disposable DB above.
- **REAL RETRIEVAL EVAL: NOT RUN.** There is no safe representative embedded PostgreSQL corpus; no Recall@1/3/K or MRR is claimed.
- **LIVE GEMINI: NOT RUN.** Credentials were not inspected or used, so no controlled provider smoke test was performed.
- Current active backend deployment target: **NOT VERIFIED FROM REPOSITORY SOURCE**. The frontend has Vercel SPA rewrites; the backend Dockerfile exists, but no active deployment configuration or migration-run step is established.

### Release and activation decision (pre-release)

READY TO MERGE: **NO**.

READY TO ENABLE `ADAPTIVE_V2` IN PRODUCTION: **CONDITIONAL**.

Before merge/activation of that historical baseline, run the complete Alembic chain on a verified disposable PostgreSQL + pgvector instance (upgrade, schema/constraint/index checks, downgrade, re-upgrade), execute the non-destructive seed idempotency/rollback checks there, and perform the documented five-case controlled Gemini smoke test. The historical source default was `ADAPTIVE_V2_PLANNER_ENABLED=false`; subsequent production verification recorded the deployed environment value as `true`. Production retrieval must remain `B_legacy` unless a real labeled retrieval measurement supports changing it.

Remaining risks are unverified PostgreSQL-specific migration behavior, no real retrieval measurement, no live Gemini structured-output check, and an unestablished backend deployment/migration operator. The deployment must run Alembic to head before enabling adaptive routes; old schema should fail requests rather than silently mutate learner state.

Overall Phase 9 verdict: **FAIL pending the stated mandatory activation gates**.
