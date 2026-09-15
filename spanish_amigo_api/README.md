# SpanishAmigo API

FastAPI backend for SpanishAmigo. It powers lesson progress, Lumi chat, AI explanations, chat sessions, adaptive learning state/reviews, Firebase-authenticated user data, and Neon Postgres persistence.

## Current Stack

- Python 3.12+
- FastAPI + Uvicorn
- SQLAlchemy 2.0 typed ORM
- Alembic migrations
- Neon Serverless Postgres
- Neon `pgvector` for lesson RAG embeddings
- Google Gemini API
- LangGraph tutor workflow
- Firebase Admin Auth for bearer-token verification
- `uv` for dependency and lockfile management

## Runtime Services

- `GET /health`: Database and service health check.
- `GET /status`: backward-compatible alias for `/health`.
- `/progress/*`: protected progress read/write routes.
- `/chat/send`: protected non-streaming Lumi chat route.
- `/chat/send_stream`: protected SSE Lumi chat route.
- `/chat/sessions/*`: protected chat session lifecycle routes.
- `POST /chat/explain`: public explanation route used by lesson reveal cards.
- `/adaptive/*`: protected adaptive learning state, review scheduling, and review submission routes.

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
```

Important:

- `AUTH_ALLOW_INSECURE_DEV_TOKENS=false` must stay enforced in production.
- `ALLOWED_CORS_ORIGINS` is comma-separated (e.g. `https://example.vercel.app,http://localhost:5173`).

## Local Development

```powershell
cd spanish_amigo_api
uv sync
uv run uvicorn main:app --reload
```

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

## Migrations

```powershell
cd spanish_amigo_api
uv run alembic upgrade head
```

The backend runs migrations via Alembic:

```powershell
cd spanish_amigo_api
uv run alembic upgrade head
```

## Tests And Quality Gates

Backend tests:

```powershell
cd spanish_amigo_api
uv run python -m unittest discover -s tests -p "test_*.py"
```

Targeted type check is configured through:

```text
mypy.ini
```

```powershell
cd spanish_amigo_api
uv run --with mypy mypy app/config.py app/services/auth.py app/services/health.py main.py --config-file mypy.ini
```

Dependency audit:

```powershell
cd spanish_amigo_api
uv run --with pip-audit pip-audit --desc
```

The security workflow also runs frontend production dependency audit from the repo root:

```powershell
npm.cmd audit --omit=dev --audit-level=high
```

## Anonymous User Rules

The frontend silently creates Firebase anonymous users. The backend treats anonymous UIDs as real users for ownership checks.

Current anonymous limits:

- Lesson 1 is available without Google sign-in.
- Lesson 2 and later require Google sign-in.
- Global Lumi chat allows exactly 3 lifetime messages for an anonymous UID.
- The 4th global Lumi message returns `403` with code `ANONYMOUS_CHAT_LIMIT_REACHED`.
- `Ask Lumi to Explain` remains public, free, and unmetered.

Anonymous chat usage is stored in `SystemStatus` with keys like:

```text
anonymous_chat_usage:<firebase_uid>
```

## Deployment

The backend application is containerized with `Dockerfile`:

- Python 3.12 slim base image with `uv` for reproducible frozen dependency synchronization (`uv sync --frozen --no-dev`).
- Uvicorn server running FastAPI on `$PORT` (default 8000).
- Health check available at `GET /health`.
- Target runtime database migrations must be applied (`uv run alembic upgrade head`) before traffic is routed.

## Security Notes

- Firebase ID tokens are verified through Firebase Admin SDK.
- Progress, chat/session, and adaptive routes enforce Firebase UID tenancy.
- Production uses JSON logs and request IDs.
- Dependency security is gated by `pip-audit`, `npm audit`, and dependency review.
- Known remaining hardening item: rate limiting for expensive LLM endpoints.
