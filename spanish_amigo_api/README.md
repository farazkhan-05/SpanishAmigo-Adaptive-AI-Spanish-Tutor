# SpanishAmigo API

FastAPI backend for SpanishAmigo. It provides authenticated learner progress, Lumi chat orchestration, contextual curriculum retrieval, and adaptive skill review services backed by PostgreSQL and pgvector.

For complete project architecture and end-to-end setup, see the root [README.md](../README.md).

## Current Stack

- Python 3.12+
- FastAPI and Uvicorn
- SQLAlchemy 2.0 typed ORM
- Alembic schema migrations
- Neon Serverless PostgreSQL with `pgvector`
- Google Gemini API (`gemini-3.5-flash-lite` default, `gemini-embedding-2` embeddings)
- LangGraph tutor workflow
- Firebase Admin Auth for bearer token verification
- Free Spaced Repetition Scheduler (`py-fsrs` 6.3.2)
- `uv` for reproducible dependency and lockfile management

## Runtime Services

- `GET /health`: Database and service health check.
- `GET /status`: Backward-compatible alias for `/health`.
- `/progress/*`: Protected progress read and write routes.
- `/chat/send`: Protected non-streaming Lumi chat route.
- `/chat/send_stream`: Protected SSE Lumi chat route.
- `/chat/sessions/*`: Protected chat session lifecycle routes.
- `POST /chat/explain`: Public explanation route used by lesson reveal cards.
- `/adaptive/*`: Protected adaptive learning state, review scheduling, and review submission routes.

Protected routes require:

```http
Authorization: Bearer <Firebase ID token>
```

`/chat/explain` is intentionally public and does not count against the anonymous global chat quota.

## Environment Variables

Local development uses `spanish_amigo_api/.env`:

```env
ENV=development
DATABASE_URL=postgresql://...
GEMINI_API_KEY=...
FIREBASE_PROJECT_ID=spanishamigo-8016a
ALLOWED_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
AUTH_ALLOW_INSECURE_DEV_TOKENS=true
ADAPTIVE_V2_PLANNER_ENABLED=false
TELEMETRY_ENABLED=true
TELEMETRY_SAMPLE_RATE=1.0
TELEMETRY_RETENTION_DAYS=30
LOG_LEVEL=INFO
```

Production environment configuration:

```env
ENV=production
LOG_LEVEL=INFO
FIREBASE_PROJECT_ID=<your-firebase-project-id>
ALLOWED_CORS_ORIGINS=https://your-frontend-domain.vercel.app
AUTH_ALLOW_INSECURE_DEV_TOKENS=false
DATABASE_URL=postgresql://...
GEMINI_API_KEY=...
ADAPTIVE_V2_PLANNER_ENABLED=false
TELEMETRY_ENABLED=true
TELEMETRY_SAMPLE_RATE=1.0
TELEMETRY_RETENTION_DAYS=30
```

Important:

- `AUTH_ALLOW_INSECURE_DEV_TOKENS=false` must stay enforced in production.
- `ALLOWED_CORS_ORIGINS` is comma-separated (for example, `https://example.vercel.app,http://localhost:5173`).
- `ADAPTIVE_V2_PLANNER_ENABLED` defaults to `false`; the previously deployed Adaptive V2 production baseline was verified with the environment value `true`.
- The current release candidate adds migrations `d2e3f4a5b6c7` and `e1782f3a4b5c`, which remain pending production deployment after merge.
- `TELEMETRY_ENABLED` is a boolean, `TELEMETRY_SAMPLE_RATE` is a float from `0` to `1` for successful-event sampling (failures remain retained), and `TELEMETRY_RETENTION_DAYS` is a positive integer pruning horizon.

## Local Development

```powershell
cd spanish_amigo_api
uv sync --locked
uv run --locked uvicorn main:app --reload
```

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

## Migrations

Apply database schema migrations via Alembic:

```powershell
cd spanish_amigo_api
uv run --locked alembic upgrade head
```

## Tests And Quality Gates

Backend unit tests:

```powershell
cd spanish_amigo_api
uv run --locked python -m unittest discover -s tests -p "test_*.py"
```

Targeted type check:

```powershell
cd spanish_amigo_api
uv run --locked --with mypy mypy app/config.py app/services/auth.py app/services/health.py main.py --config-file mypy.ini
```

Dependency audit:

```powershell
cd spanish_amigo_api
uv run --locked --with pip-audit pip-audit --desc
```

Frontend production dependency audit from the repository root:

```powershell
npm.cmd audit --omit=dev --audit-level=high
```

Offline adaptive evaluations:

```powershell
cd spanish_amigo_api
uv run --locked python -m evals.run_eval phase7-offline --report evals/reports/phase7-offline.json
uv run --locked python -m evals.run_eval planner-offline --report evals/reports/phase5-planner.json
```

## Anonymous User Rules

The frontend creates Firebase anonymous users automatically. The backend treats anonymous UIDs as real users for ownership checks.

Current anonymous limits:

- Lesson 1 is available without Google sign-in.
- Lesson 2 and later require Google sign-in.
- Global Lumi chat allows exactly 3 lifetime messages for an anonymous UID.
- The 4th global Lumi message returns `403` with code `ANONYMOUS_CHAT_LIMIT_REACHED`.
- `Ask Lumi to Explain` remains public, free, and unmetered.

Anonymous chat usage is stored in `SystemStatus` with keys formatted as:

```text
anonymous_chat_usage:<firebase_uid>
```

## Deployment

The production backend is hosted on Vercel:

- Live URL: `https://spanish-amigo-api.vercel.app`
- Health endpoint: `https://spanish-amigo-api.vercel.app/health`

The repository also includes a portable `Dockerfile` for containerized environments:

- Python 3.12 slim base image with `uv` for reproducible frozen dependency synchronization (`uv sync --frozen --no-dev`).
- Uvicorn server running FastAPI on `$PORT` (default 8000).
- Health check available at `GET /health`.
- Target runtime database migrations must be applied (`uv run --locked alembic upgrade head`) before traffic is routed.

## Security Notes

- Firebase ID tokens are verified through Firebase Admin SDK.
- Progress, chat session, and adaptive routes enforce Firebase UID tenancy.
- Production uses JSON logs and request IDs.
- Dependency security is gated by `pip-audit`, `npm audit`, and dependency review.
- Rate limiting for LLM endpoints remains a recommended operational enhancement.
