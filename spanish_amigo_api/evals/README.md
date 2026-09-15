# Pre-adaptive evaluation baseline

This directory records repository-owned human expectations for the pre-adaptive tutor. `golden_cases.jsonl` is data, never executable input. The `offline` command validates cases and snapshots configuration without importing model or database adapters.

`db-retrieval` is an explicit, read-only local/integration command: it calls the configured embedding provider and queries existing `lesson_slides`; it never invokes `seed_embeddings.py`, migrations, inserts, updates, or deletes. `live-model` intentionally has no implementation in Phase 2, so it cannot silently consume quota.
