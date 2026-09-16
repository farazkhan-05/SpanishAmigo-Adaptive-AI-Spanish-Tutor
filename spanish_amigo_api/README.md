# SpanishAmigo API

FastAPI backend for SpanishAmigo. It provides authenticated learner progress, Lumi chat orchestration, contextual curriculum retrieval, and adaptive skill review services backed by PostgreSQL and pgvector.

For complete project architecture and end-to-end setup, see the root [README.md](../README.md).

## Technology stack

- Python 3.12+
- FastAPI and Uvicorn
- SQLAlchemy 2.0 typed ORM
- Alembic schema migrations
- Neon PostgreSQL with `pgvector`
- Google Gemini API (`gemini-3.5-flash-lite` primary default, `gemma-4-31b-it` fallback, `gemini-embedding-2` embeddings)
- LangGraph tutor workflow
- Firebase Admin SDK for bearer token verification
- Free Spaced Repetition Scheduler (`py-fsrs` 6.3.2)
- `uv` for deterministic dependency and lockfile management

## Runtime services

- `GET /health`: Database and service health check.
- `GET /status`: Backward-compatible alias for `/health`.
- `/progress/*`: Protected progress read and write routes.
- `/chat/send`: Protected non-streaming Lumi chat route.
- `/chat/send_stream`: Protected SSE Lumi chat route.
- `/chat/sessions/*`: Protected chat session lifecycle routes (create, rename, list, delete).
- `POST /chat/explain`: Public explanation route used by lesson reveal cards (unmetered, unauthenticated).
- `/adaptive/*`: Protected adaptive learning state, review scheduling, targeted practice, and review submission routes.

Protected routes require a Firebase ID token in the authorization header:

```http
Authorization: Bearer <Firebase ID token>
```

`/chat/explain` is public and does not consume the anonymous global chat quota.

## Environment variables

Local development uses `spanish_amigo_api/.env`:

```env
ENV=development
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/spanish_amigo
GEMINI_API_KEY=your_gemini_api_key
FIREBASE_PROJECT_ID=spanishamigo-8016a
FIREBASE_SERVICE_ACCOUNT_JSON=
ALLOWED_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
AUTH_ALLOW_INSECURE_DEV_TOKENS=false
LOG_LEVEL=INFO
GEMINI_PRIMARY_MODEL=gemini-3.5-flash-lite
GEMINI_BACKUP_MODEL=gemma-4-31b-it
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
ADAPTIVE_V2_PLANNER_ENABLED=false
TELEMETRY_ENABLED=true
TELEMETRY_SAMPLE_RATE=1.0
TELEMETRY_RETENTION_DAYS=30
```

Production environment configuration:

```env
ENV=production
LOG_LEVEL=INFO
FIREBASE_PROJECT_ID=spanishamigo-8016a
FIREBASE_SERVICE_ACCOUNT_JSON=
ALLOWED_CORS_ORIGINS=https://spanishamigo.vercel.app
AUTH_ALLOW_INSECURE_DEV_TOKENS=false
DATABASE_URL=postgresql+psycopg://...
GEMINI_API_KEY=...
GEMINI_PRIMARY_MODEL=gemini-3.5-flash-lite
GEMINI_BACKUP_MODEL=gemma-4-31b-it
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
ADAPTIVE_V2_PLANNER_ENABLED=true
TELEMETRY_ENABLED=true
TELEMETRY_SAMPLE_RATE=1.0
TELEMETRY_RETENTION_DAYS=30
```

Operational notes:

- `AUTH_ALLOW_INSECURE_DEV_TOKENS=false` must remain enforced in production.
- `ALLOWED_CORS_ORIGINS` is a comma-separated list of allowed origins.
- `ADAPTIVE_V2_PLANNER_ENABLED` defaults to `false` in code; the deployed Adaptive V2 production baseline was verified with the environment value `true`.
- Release candidate migrations `d2e3f4a5b6c7` (telemetry events) and `e1782f3a4b5c` (targeted practice linkage) remain pending deployment to production.
- `TELEMETRY_ENABLED` controls telemetry logging, `TELEMETRY_SAMPLE_RATE` (0.0 to 1.0) samples successful events while preserving all failures, and `TELEMETRY_RETENTION_DAYS` specifies the pruning horizon.

## Local development

Navigate to the backend directory and synchronize dependencies:

```powershell
cd spanish_amigo_api
uv sync --locked
```

Start the development server:

```powershell
uv run --locked uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

## Database migrations and seeding

Apply database schema migrations via Alembic:

```powershell
cd spanish_amigo_api
uv run --locked alembic upgrade head
```

Run idempotent curriculum seeding:

```powershell
uv run --locked python seed_embeddings.py
```

## Quality assurance and tests

Backend unit and integration tests:

```powershell
cd spanish_amigo_api
uv run --locked python -m unittest discover -s tests -p "test_*.py"
```

Static type checking:

```powershell
cd spanish_amigo_api
uv run --locked --with mypy mypy app/config.py app/services/auth.py app/services/health.py main.py --config-file mypy.ini
```

Dependency security scan:

```powershell
cd spanish_amigo_api
uv run --locked --with pip-audit pip-audit --desc
```

Offline adaptive evaluations:

```powershell
cd spanish_amigo_api
uv run --locked python -m evals.run_eval phase7-offline --report evals/reports/phase7-offline.json
uv run --locked python -m evals.run_eval planner-offline --report evals/reports/phase5-planner.json
```

## Observability and telemetry CLI

The telemetry service records latency percentiles, TTFT, token usage, and failure categories in a content-free database table (`ai_telemetry_events`).

Run reporting:

```powershell
cd spanish_amigo_api
uv run python -m app.telemetry_cli --hours 24
```

Prune records older than `TELEMETRY_RETENTION_DAYS`:

```powershell
cd spanish_amigo_api
uv run python -m app.telemetry_cli --prune
```

## Anonymous user rules

The frontend creates Firebase anonymous users automatically. The backend treats anonymous UIDs as real users for ownership checks.

- Lesson 1 is accessible without Google sign-in.
- Lesson 2 and later require Google sign-in.
- Global Lumi chat allows up to 3 messages for an anonymous UID.
- The 4th message returns HTTP `403` with error code `ANONYMOUS_CHAT_LIMIT_REACHED`.
- `POST /chat/explain` is unmetered and public.

Anonymous chat usage is tracked in `system_status` under keys formatted as `anonymous_chat_usage:<firebase_uid>`.

## Deployment

The production backend is hosted on Vercel:

- Live URL: `https://spanish-amigo-api.vercel.app`
- Health endpoint: `https://spanish-amigo-api.vercel.app/health`

The repository also includes a container definition in `Dockerfile`:

- Python 3.12 slim base image with `uv` for frozen dependency synchronization (`uv sync --frozen --no-dev`).
- Uvicorn server running FastAPI on `$PORT` (default 8000).
- Health check available at `GET /health`.

## Security

- Firebase ID tokens are verified through Firebase Admin SDK.
- Progress, chat session, and adaptive routes enforce Firebase UID tenancy.
- Telemetry avoids storing prompts, completions, or user identifiers.
- Dependency security is verified with `pip-audit` and GitHub Dependency Review.
