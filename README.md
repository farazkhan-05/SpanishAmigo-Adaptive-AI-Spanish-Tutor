# SpanishAmigo: Production RAG Application with Real-Time AI Chat

SpanishAmigo is the product implementation of this system: a full-stack Spanish learning app with structured lessons, saved progress, and an AI tutor named Lumi. The frontend is built with React and Vite. The backend is a FastAPI service that verifies Firebase ID tokens, stores user progress and chat history in Postgres, and streams AI tutor responses over Server-Sent Events.

**Live Demo:** [spanishamigo.vercel.app](https://spanishamigo.vercel.app/)

The project is designed as a practical production-style portfolio app: small enough to understand, but complete enough to show real work across frontend, backend, authentication, persistence, AI integration, deployment, and operational hardening.

## Contents

- [Product Overview](#product-overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Repository Layout](#repository-layout)
- [Local Development](#local-development)
- [Environment Variables](#environment-variables)
- [Database And Migrations](#database-and-migrations)
- [Optional Lesson Retrieval Seeding](#optional-lesson-retrieval-seeding)
- [Quality Checks](#quality-checks)
- [Deployment](#deployment)
- [Security And Reliability Notes](#security-and-reliability-notes)
- [Current Status](#current-status)

## Product Overview

SpanishAmigo focuses on beginner Spanish practice. Learners work through short lessons, complete quiz-style interactions, and ask Lumi for help without leaving the lesson flow.

The app supports both guest and signed-in usage:

- Guest users are signed in anonymously through Firebase so the app can maintain a stable user identity.
- Google sign-in unlocks saved progress beyond the guest experience.
- Signed-in users can keep lesson progress and chat sessions tied to their Firebase account.

## Features

- Five structured Spanish lessons with context, translation reveal, and practice slides.
- Course map with lesson locking, progress stats, completion states, and achievement badges.
- Lesson player with slide transitions, answer feedback, hints, and completion handling.
- Firebase Authentication with anonymous sign-in and Google account upgrade.
- Local guest progress backed by `localStorage`.
- Signed-in progress sync through FastAPI and Postgres.
- Floating AI tutor with streamed responses over SSE.
- Multi-session chat history with create, load, rename, and delete support.
- Browser speech recognition for voice input.
- Browser speech synthesis for tutor responses.
- AI-generated explanations for translation reveal cards.
- Light and dark mode support.
- Backend guardrails to keep Lumi focused on Spanish learning.
- Optional semantic lesson retrieval with Gemini embeddings and `pgvector`.

## Architecture

```text
React/Vite frontend
        |
        | Firebase ID token
        v
FastAPI backend
        |
        | SQLAlchemy
        v
Postgres / pgvector
        |
        | lesson context, chat memory
        v
Gemini + LangGraph tutor workflow
```

### Frontend

The frontend lives at the repository root under `src/`.

Key areas:

- `src/App.jsx` sets up theme, routing, auth, and progress providers.
- `src/components/layout/Layout.jsx` owns the app shell and global chat widget.
- `src/components/chat/GlobalChatbot.jsx` handles chat sessions, SSE streaming, voice input, and speech playback.
- `src/context/AuthContext.jsx` manages Firebase anonymous auth and Google sign-in.
- `src/context/ProgressContext.jsx` syncs local and backend lesson progress.
- `src/pages/CourseMap.jsx` renders the lesson map.
- `src/pages/LessonPlayer.jsx` runs the lesson slide flow.
- `src/data/lessons/` contains the lesson content used by the frontend.

### Backend

The backend lives in `spanish_amigo_api/`.

Key areas:

- `main.py` creates the FastAPI app, configures CORS, request logging, health checks, and routers.
- `app/routers/progress.py` exposes protected progress endpoints.
- `app/routers/chat.py` exposes protected chat, streaming, session, history, and explanation endpoints.
- `app/services/auth.py` verifies Firebase ID tokens with Firebase Admin SDK.
- `app/services/ai.py` contains the LangGraph tutor workflow, guardrails, model fallback, memory saving, and lesson retrieval.
- `app/models.py` defines SQLAlchemy models for users, lessons, chat sessions, chat messages, lesson slides, and system status.
- `migrations/` contains Alembic migrations.

## Tech Stack

| Area | Technology |
| --- | --- |
| Frontend | React 19, Vite |
| Routing | React Router |
| UI | Material UI, Tailwind CSS, Lucide React |
| Auth | Firebase Authentication, Firebase Admin SDK |
| Backend | FastAPI, Uvicorn |
| AI Orchestration | LangGraph, LangChain |
| LLM Provider | Google Gemini |
| Realtime Transport | Server-Sent Events (SSE) |
| Database | Neon Postgres, Postgres-compatible databases |
| Vector Search | pgvector |
| ORM And Migrations | SQLAlchemy 2.0, Alembic |
| Validation And Config | Pydantic, Pydantic Settings |
| Package Management | npm, uv |
| Containerization | Docker |
| Deployment | Vercel (Frontend), Docker-ready container (Backend) |
| CI And Security | GitHub Actions, Dependabot, pip-audit, npm audit |

## Repository Layout

```text
.
|-- .github/
|   |-- dependabot.yml
|   `-- workflows/
|       |-- backend-ci.yml
|       `-- dependency-security.yml
|-- public/
|-- src/
|   |-- api/
|   |-- components/
|   |   |-- auth/
|   |   |-- chat/
|   |   |-- layout/
|   |   `-- lesson/
|   |-- context/
|   |-- data/
|   |   `-- lessons/
|   |-- hooks/
|   |-- pages/
|   |-- theme/
|   `-- utils/
|-- spanish_amigo_api/
|   |-- app/
|   |   |-- routers/
|   |   |-- services/
|   |   |-- config.py
|   |   |-- database.py
|   |   |-- models.py
|   |   `-- schemas.py
|   |-- migrations/
|   |-- tests/
|   |-- Dockerfile
|   |-- main.py
|   |-- pyproject.toml
|   `-- uv.lock
|-- index.html
|-- package.json
|-- package-lock.json
|-- vite.config.js
`-- vercel.json
```

Local-only files such as `.env`, `.env.local`, `dist/`, `node_modules/`, generated lesson data, and backend runbooks are intentionally ignored by Git.

## Local Development

### Prerequisites

- Node.js and npm.
- Python 3.12 or newer.
- `uv` for the backend Python environment.
- Firebase project with Authentication enabled.
- Postgres database.
- Gemini API key.
- Optional: Postgres database with `pgvector` enabled for lesson retrieval.

### Frontend Setup

Install dependencies from the repository root:

```bash
npm install
```

Create `.env.local`:

```env
VITE_FIREBASE_API_KEY=your_firebase_api_key
VITE_FIREBASE_AUTH_DOMAIN=your_firebase_auth_domain
VITE_FIREBASE_PROJECT_ID=your_firebase_project_id
VITE_FIREBASE_STORAGE_BUCKET=your_firebase_storage_bucket
VITE_FIREBASE_MESSAGING_SENDER_ID=your_firebase_messaging_sender_id
VITE_FIREBASE_APP_ID=your_firebase_app_id
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Run the frontend:

```bash
npm run dev
```

### Backend Setup

From the backend directory:

```bash
cd spanish_amigo_api
uv sync
```

Create `spanish_amigo_api/.env`:

```env
ENV=development
DATABASE_URL=postgresql+psycopg://user:password@host:5432/database
GEMINI_API_KEY=your_gemini_api_key
FIREBASE_PROJECT_ID=your_firebase_project_id
ALLOWED_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
AUTH_ALLOW_INSECURE_DEV_TOKENS=false
LOG_LEVEL=INFO
```

Optional model overrides:

```env
GEMINI_PRIMARY_MODEL=gemini-3.1-flash-lite
GEMINI_BACKUP_MODEL=gemma-4-31b
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
```

Apply migrations and start the API:

```bash
uv run alembic upgrade head
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Environment Variables

### Frontend

| Variable | Purpose |
| --- | --- |
| `VITE_FIREBASE_API_KEY` | Firebase web API key. |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase auth domain. |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project ID. |
| `VITE_FIREBASE_STORAGE_BUCKET` | Firebase storage bucket. |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Firebase sender ID. |
| `VITE_FIREBASE_APP_ID` | Firebase app ID. |
| `VITE_API_BASE_URL` | Base URL for the FastAPI backend. |

### Backend

| Variable | Purpose |
| --- | --- |
| `ENV` | Runtime environment name. |
| `DATABASE_URL` | Postgres connection string. |
| `GEMINI_API_KEY` | Gemini API key for tutor responses and embeddings. |
| `FIREBASE_PROJECT_ID` | Firebase project used for token verification. |
| `ALLOWED_CORS_ORIGINS` | Comma-separated frontend origins allowed by FastAPI CORS. |
| `AUTH_ALLOW_INSECURE_DEV_TOKENS` | Kept false. Firebase tokens are verified cryptographically. |
| `LOG_LEVEL` | Backend log level. |
| `GEMINI_PRIMARY_MODEL` | Primary Gemini chat model. |
| `GEMINI_BACKUP_MODEL` | Backup model used after quota or provider failures. |
| `GEMINI_EMBEDDING_MODEL` | Embedding model for lesson retrieval. |

## Database And Migrations

The backend uses SQLAlchemy models and Alembic migrations.

Run migrations locally:

```bash
cd spanish_amigo_api
uv run alembic upgrade head
```

The current schema includes:

- `users`
- `completed_lessons`
- `chat_sessions`
- `chat_messages`
- `lesson_slides`
- `system_status`

Apply migrations to target database:

```bash
cd spanish_amigo_api
uv run alembic upgrade head
```

## Optional Lesson Retrieval Seeding

The AI tutor can use lesson-slide context through `lesson_slides` embeddings. This path is optional for local development. The app can run without seeded lesson embeddings, but retrieval quality improves when embeddings are present.

The seeder is located at:

```text
spanish_amigo_api/seed_embeddings.py
```

It expects a generated `lessons_data.json` file at the repository root. That generated file is intentionally ignored because it is build data, not source code.

Run the seeder from the backend directory after the generated lesson JSON exists:

```bash
cd spanish_amigo_api
uv run python seed_embeddings.py
```

## Quality Checks

Frontend:

```bash
npm run lint
npm run build
```

Backend:

```bash
cd spanish_amigo_api
uv run python -m unittest discover -s tests -p "test_*.py"
```

Backend type checks used by CI:

```bash
cd spanish_amigo_api
uv run --with mypy mypy app/config.py app/services/auth.py app/services/health.py main.py --config-file mypy.ini
```

Dependency audits:

```bash
npm audit --omit=dev --audit-level=high

cd spanish_amigo_api
uv run --with pip-audit pip-audit --desc
```

## Deployment

### Frontend

The frontend is configured for Vercel. `vercel.json` rewrites all routes to `index.html` so React Router can handle client-side navigation. Production builds require `VITE_API_BASE_URL` pointing to the active backend API.

### Backend

The backend is containerized using `spanish_amigo_api/Dockerfile` (`uv`-based Python 3.12 image). It exposes the FastAPI application on port 8000 (or the environment-configured `$PORT`) with a built-in health check on `/health`.

## Security And Reliability Notes

- Firebase ID tokens are verified by the backend with Firebase Admin SDK.
- Progress, chat, history, session, explanation, and adaptive endpoints require authenticated Firebase users.
- The backend enforces Firebase UID ownership on user-scoped routes.
- Anonymous users are limited to three global Lumi chat messages before Google sign-in is required.
- Chat request payloads are validated with Pydantic, including a maximum message length.
- Chat history context is capped before being sent into AI workflows.
- Streaming chat logs SSE generator failures with exception details while still returning a user-facing fallback message.
- Background database work opens fresh SQLAlchemy sessions instead of reusing request-scoped sessions.
- AI guardrails classify longer inputs and block obvious off-topic, unsafe, or prompt-injection requests.
- Backend environments configure `DATABASE_URL` and `GEMINI_API_KEY`.
- Dependency security is checked with Dependabot, `npm audit`, `pip-audit`, and GitHub dependency review.

## Current Status

SpanishAmigo is feature-complete as a solo portfolio project. The main user journey works end to end:

1. Open the app as a guest.
2. Start lesson 1.
3. Sign in with Google to continue.
4. Complete lessons and sync progress.
5. Ask Lumi for explanations and chat help.
6. Return later and load saved chat sessions and progress.

The remaining work is product polish rather than missing infrastructure: more lesson content, richer analytics, broader browser testing, and optional rate limiting for expensive AI endpoints.
