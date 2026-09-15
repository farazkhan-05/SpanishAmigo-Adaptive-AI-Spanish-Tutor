# SpanishAmigo engineering guide

## Repository and baseline

- Inspect source before trusting README deployment or architecture claims.
- The responsive frontend redesign is established functionality. Preserve `CourseMap`, `CourseJourney`, `CourseSupportPanels`, the route-aware `Layout`, and the compact `LessonPlayer`.
- Course completion is curriculum navigation progress, not skill mastery.
- Current validation: `npm run lint`, `npm run build`; then from `spanish_amigo_api`, `uv run python -m unittest discover -s tests -p "test_*.py"` and `uv run --with mypy mypy app/config.py app/services/auth.py app/services/health.py main.py --config-file mypy.ini`. Also run `git diff --check`.

## Auth, tenancy, and product contracts

- Firebase UID is the authoritative tenant identity. Never trust an arbitrary client `user_id` when a verified UID exists.
- Anonymous Firebase users are real backend users; preserve current guest progress and the three-message anonymous global-chat quota.
- Preserve Google account linking. Fallback Google sign-in can produce a different UID; do not silently migrate adaptive state without an explicit design.
- Preserve progress, chat-session/history ownership, `/chat/send`, `/chat/send_stream`, model fallback, guardrails, dark mode, responsiveness, accessibility, and the current frontend redesign.
- Preserve the SSE contract: JSON `session_id`, `token`, optional `action_required`, then `data: [DONE]`.

## Database and adaptive boundaries

- Use Alembic for production schema evolution. Make migrations reversible where realistically possible and name constraints explicitly where appropriate.
- Never use destructive curriculum drop/recreate as a metadata migration. Future adaptive work must make `seed_embeddings.py` non-destructive.
- Preserve evidence needed to explain accepted mastery changes.
- LLMs may propose assessments and generate grounded content. Application code owns authorization, evidence validation, thresholds, policy, mastery mutation, scheduling, and persistence.
- Invalid, rejected, or low-confidence evidence--and merely showing an explanation--cannot change mastery.
- Future adaptive planning for `/chat/send` and `/chat/send_stream` must converge on one authoritative implementation.

## Evals, supply chain, and deferrals

- Important adaptive behavior must be testable offline; CI must not require Gemini or other external API access. Never fabricate evaluation numbers; keep A/B baselines reproducible.
- Research and verify every new dependency through its official registry/source, advisories/CVEs, package identity, and relevant install scripts. Do not bypass security software.
- Deferred by default: GraphRAG, graph DBs, multi-agent swarms, AI avatars, pronunciation scoring, paid observability/search/vector services, and voice as a required core feature.
