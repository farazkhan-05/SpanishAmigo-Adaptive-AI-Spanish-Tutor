# SpanishAmigo Documentation Index

This directory contains technical design contracts, implementation milestone records, and historical audits for the SpanishAmigo Adaptive V2 system.

Current operational behavior and deployment architecture are defined by the active source code and primary documentation:

## Current documentation

- [Root README](../README.md): Full system architecture, live deployment URLs, environment configuration, database schema, and local development setup.
- [EVALUATION.md](../EVALUATION.md): Evaluation methodology, offline CI test gates, measured results, and release verification status.
- [Backend README](../spanish_amigo_api/README.md): FastAPI service routes, authentication details, migration workflows, and operational endpoints.

## Historical Adaptive V2 implementation records

The following documents are retained as auditable engineering records. They describe the system as it existed at each stage of development. Statements within these files reflecting planned work, unverified gates, or pre-release findings describe conditions at the time the respective milestone was completed. Current runtime behavior is governed by active source code and the primary documentation above.

- [Adaptive upgrade contract](ADAPTIVE_UPGRADE_CONTRACT.md): Initial architectural design contract and constraints drafted prior to implementation.
- [Phase 3: Curriculum and retrieval foundation](ADAPTIVE_V2_PHASE3.md): Taxonomy definition, slide-to-skill mappings, and embedding backfill design.
- [Phase 4: Tenant-safe evidence storage](ADAPTIVE_V2_PHASE4.md): Database persistence schema for learner state, assessment events, and practice attempts.
- [Phase 5: Validated assessment and turn planning](ADAPTIVE_V2_PHASE5.md): Shared turn planner, assessability gate, deterministic validation, and LangGraph topology.
- [Phase 5 targeted practice lifecycle](ADAPTIVE_V2_PHASE5_TARGETED_PRACTICE.md): Confirmed chat-to-practice gap, server-owned targeted practice, and the second-response mastery boundary.
- [Phase 6: Mastery, practice, and FSRS review](ADAPTIVE_V2_PHASE6.md): Deterministic mastery mutation, review endpoints, and FSRS scheduling integration.
- [Phase 7: Rigorous offline evaluation](ADAPTIVE_V2_PHASE7.md): Deterministic evaluation harness, golden test cases, and safety invariant verification.
- [Phase 8: Learner-facing adaptive UX](ADAPTIVE_V2_PHASE8.md): Frontend My Spanish dashboard and spaced review workflow.
- [Adaptive V2 pre-release audit](ADAPTIVE_V2_PRE_RELEASE_AUDIT.md): Pre-release audit record from 2026-09-15 preserving original pre-release findings alongside subsequent production gate closure.
