# SpanishAmigo

SpanishAmigo is a full-stack Spanish language learning web application that combines structured beginner lessons with an AI conversational tutor named Lumi, semantic curriculum retrieval, and deterministic adaptive skill tracking.

The frontend is built with React 19, Vite, Material UI, and Tailwind CSS. The backend is a FastAPI service that verifies Firebase authentication tokens, persists learner progress and chat history in PostgreSQL with pgvector, orchestrates Google Gemini models through LangGraph, and schedules spaced repetition reviews using the Free Spaced Repetition Scheduler (FSRS).

Live application:
* Frontend: [https://spanishamigo.vercel.app](https://spanishamigo.vercel.app)
* Backend API: [https://spanish-amigo-api.vercel.app](https://spanish-amigo-api.vercel.app)
* Health endpoint: [https://spanish-amigo-api.vercel.app/health](https://spanish-amigo-api.vercel.app/health)

Production deployment status: The live URLs above now run the final engineering release from `main`, with the production database at Alembic revision `e1782f3a4b5c`. This release includes the model upgrade to `gemini-3.5-flash-lite`, AI telemetry from migration `d2e3f4a5b6c7`, and targeted practice linkages from migration `e1782f3a4b5c`.

## Architecture

SpanishAmigo separates student interactions into two operational layers: an interactive curriculum interface and an asynchronous AI tutoring and evaluation pipeline.

```mermaid
flowchart TD
    Client["React 19 / Vite Frontend (Vercel)"]
    Auth["Firebase Authentication"]
    API["FastAPI Backend (Vercel)"]
    DB[("Neon PostgreSQL 18 + pgvector")]
    Orch["LangGraph Tutor Engine"]
    LLM["Google Gemini (gemini-3.5-flash-lite)"]
    Embed["Google Gemini Embeddings (gemini-embedding-2)"]
    Validator["Deterministic Validator"]
    FSRS["FSRS Review Engine (py-fsrs)"]
    Telem["AI Telemetry Service"]

    Client -->|"ID Token"| Auth
    Client -->|"REST / SSE Streaming"| API
    API -->|"Token Verification"| Auth
    API -->|"State & Session Storage"| DB
    API -->|"Chat & Turn Orchestration"| Orch
    Orch -->|"Slide Embeddings / Search"| DB
    Orch -->|"Contextual Chat / Assessment Proposals"| LLM
    Embed -->|"768-dim Vectors"| DB
    LLM -->|"Proposals"| Validator
    Validator -->|"Assessment Events (Audit)"| DB
    API -->|"Review Submissions & Practice"| FSRS
    FSRS -->|"Learner States & Review Cards"| DB
    DB -->|"Adaptive Skill Metrics"| API
    API -->|"My Spanish Dashboard"| Client
    API -.->|"Non-fatal Metrics"| Telem
    Telem -.->|"Content-free Logs"| DB
```

System components:

1. **Frontend interface**: Renders lesson progression, exercise interactions, audio playback, voice capture, and a persistent chat interface for Lumi.
2. **Authentication**: Firebase Authentication manages anonymous guest sessions and Google account linking. ID tokens are transmitted in HTTP Authorization headers.
3. **Backend API**: FastAPI validates request payloads with Pydantic, verifies user identity against Firebase Admin SDK, and routes requests to database services or the LangGraph AI engine.
4. **Retrieval and vector search**: PostgreSQL with pgvector stores 768-dimensional embeddings of all curriculum lesson slides. Queries retrieve relevant lesson content to ground tutor responses in taught material.
5. **Adaptive skill evaluation**: When a learner converses with Lumi, Gemini proposes structured assessment events that a deterministic validator checks before recording audit events. For server-issued review exercises, accepted eligible practice attempts trigger deterministic state transitions that update learner skill states and FSRS review schedules.
6. **Telemetry service**: Asynchronous, non-fatal logging records operational metrics (latencies, TTFT, token usage, failure classifications) without persisting learner message content or user IDs.

## Learner experience and Lumi AI tutor

The application provides a structured progression for beginner Spanish students:

* **Five core lessons**: Modules covering foundational A1 Spanish (greetings, survival expressions, politeness, directions, and café ordering).
* **Course map**: Visual navigation path tracking lesson unlocking, progress metrics, completion status, and achievement badges.
* **Interactive lesson player**: Modular slide flow providing context cards, translation reveals with unmetered AI explanations, and practice quiz slides with immediate feedback and hints.
* **Lumi AI conversational tutor**: Conversational tutor available globally across the application and within individual lessons.
  * **Model configuration**: The production primary model is `gemini-3.5-flash-lite`, with automatic fallback to `gemma-4-31b-it` upon quota exhaustion.
  * **Conversational style**: Lumi produces concise, proportional responses matched to the learner's turn length. Casual greetings and small talk receive natural replies without turning into service interactions ("How can I help you?").
  * **Pedagogical boundaries**: Lumi answers specific questions directly without unsolicited mini-lessons, lectures, or unrequested grammar drills.
  * **Clean formatting**: Responses avoid decorative emojis, excessive bolding, and mechanical bracket translations (`palabra [word]`). Translations are woven naturally into prose.
  * **Direct corrections**: Lumi corrects actual errors concisely (1-3 sentences) without over-correcting acceptable Spanish variants (such as optional subject pronouns).
  * **Identity and transparency**: Lumi truthfully identifies as an AI tutor when asked.
  * **Clean start**: New chat sessions start with an empty transcript and a subtle hint ("Ask Lumi anything about Spanish.") rather than a synthetic greeting. The composer uses the placeholder "Message Lumi...".
* **Real-time streaming chat**: Tutor responses stream incrementally via Server-Sent Events (SSE) with fallback recovery.
* **Voice input and speech output**: Web Speech API integration for microphone input and spoken tutor pronunciation (with markdown and emoji stripped before speech synthesis).
* **Session management**: Multi-session chat history allowing learners to create, switch, rename, and delete conversation threads.
* **Authentication flexibility**: Immediate guest access with local storage backup, with seamless upgrade to Google sign-in to persist cross-device progress.
* **Theme customization**: Light and dark themes, toggled manually in the UI or conversationally through Lumi.

## AI and learning flow

SpanishAmigo maintains a strict safety boundary between language model generation and learner skill mastery:

```text
Conversational Assessment Flow (Audit Only):
Learner Chat Turn -> Assessability Gate -> Gemini Proposal -> Deterministic Validator
                                                                   |
                            +--------------------------------------+--------------------------------------+
                            |                                                                             |
                        [Accepted]                                                        [Rejected / Invalid / Low Confidence]
                            |                                                                             |
                            v                                                                             v
          Persisted to assessment_events as audit evidence              Persisted to assessment_events for audit logging;
          and active pedagogical signal; does NOT mutate                no pedagogical action or state mutation
          learner skill states or schedule FSRS reviews

Eligible Practice and Review Flow (Mastery Mutation):
Server-Issued Review Practice -> Learner Submission -> Validator Acceptance -> Eligible PracticeAttempt
                                                                                      |
                                                                                      v
                                                                          process_accepted_evidence
                                                                                      |
                                            +-----------------------------------------+-----------------------------------------+
                                            |                                                                                   |
                                            v                                                                                   v
                              LearnerSkillState Mutation                                                             FSRS ReviewItem & History
                             (mastery estimate & confidence)                                                       (stability, difficulty, due date)
```

The system execution flow proceeds through eight distinct stages:

1. **Learner message**: The learner sends a text or voice message to Lumi.
2. **Curriculum retrieval**: Semantic vector search retrieves up to 3 relevant lesson slides (cosine distance < 0.65) to ground the response when curriculum context is relevant.
3. **Tutor response generation**: The LangGraph engine invokes Gemini to generate a level-appropriate response, streaming tokens via SSE.
4. **Assessment proposal**: If the learner's turn contains assessable Spanish production, Gemini proposes a structured assessment (skill identifier, result classification, and evidence text).
5. **Deterministic validation**: Application logic validates the proposal against taxonomy rules, modality constraints, CEFR levels, and evidence spans.
6. **Chat safety boundary**: Accepted conversational proposals are stored in `assessment_events` as audit logs to inform pedagogical hints or server-owned targeted practice recommendations. Ordinary chat does not mutate learner skill mastery or schedule spaced repetition reviews.
7. **Eligible practice submission**: When a learner completes a server-issued targeted practice or due-review exercise, an eligible `PracticeAttempt` is submitted.
8. **Deterministic mastery mutation and FSRS scheduling**: Upon validator acceptance, `process_accepted_evidence` updates `learner_skill_states` (mastery estimate and confidence) and invokes `py-fsrs` to update `review_items` (stability, difficulty, and next due date) and append to `review_history`.

## Adaptive learning system

SpanishAmigo implements an adaptive tracking architecture (Adaptive V2) that separates course completion from skill mastery. Completing lesson slides advances course navigation, while skill mastery requires verified recall over time.

### Curriculum taxonomy

The curriculum defines 14 stable educational skills across four categories:

* **Pronunciation**: `pronunciation.silent-h` (requires speech audio evidence).
* **Communication**: `communication.greetings`, `communication.formal-informal-address`, `communication.introductions-farewells`, `communication.politeness`, `communication.asking-directions`, `communication.cafe-ordering` (contextual transfer).
* **Grammar**: `grammar.gender-agreement`, `grammar.present-tense-querer`, `grammar.present-tense-tener`.
* **Vocabulary**: `vocabulary.survival-needs`, `vocabulary.dining-basics`, `vocabulary.places-directions`, `vocabulary.cafe-items`.

Across the 5 lessons containing 231 total slides, 222 slides participate in skill mappings through 382 explicit associations, with 9 slides left intentionally unmapped where content does not test an atomic skill.

### Mastery eligibility rules

To prevent invalid state updates, `process_accepted_evidence` and the deterministic validator enforce strict eligibility constraints:

* **Active practice requirement**: State mutation requires an eligible `PracticeAttempt` with active recall (`support_level != "exposure"`).
* **Modality constraints**: Skills flagged as `speech_required` (such as `pronunciation.silent-h`) cannot gain text mastery from typed responses.
* **Non-atomic skill constraints**: Contextual transfer skills (such as `communication.cafe-ordering`) represent scenario integration rather than atomic mastery and do not mutate numeric mastery states.
* **Vocabulary domain boundaries**: Broad vocabulary category skills are rejected for atomic text mastery in the validator.

### Spaced repetition and "My Spanish"

* **FSRS scheduling**: Validated review submissions feed into the Free Spaced Repetition Scheduler (`py-fsrs` 6.3.2), which computes card stability, difficulty, and next due review timestamps upon completing server-issued exercises.
* **Review queue**: Due reviews are surfaced through dedicated endpoints (`/adaptive/reviews/due` and `/adaptive/reviews/next`), issuing taxonomy-grounded recall prompts (`/adaptive/reviews/{id}/start`) and evaluating submissions (`/adaptive/reviews/{id}/submit`).
* **Targeted practice lifecycle**: When a learner makes an assessable mistake in chat, the server may issue an optional targeted practice recommendation (`/adaptive/practice/recommendation`), start the exercise (`/adaptive/practice/start`), and evaluate the submission (`/adaptive/practice/{attempt_id}/submit`).
* **My Spanish panel**: A dedicated dashboard organizing the 14 curriculum skills into actionable categories:
  * *Needs practice*: Assessed skills with low mastery estimates or overdue spaced repetition reviews.
  * *Going well*: Assessed skills with high stability and demonstrated recall.
  * *Not assessed*: Skills where the learner has not yet completed validated practice attempts.

For detailed walkthroughs and technical specifications, see [docs/ADAPTIVE_LEARNING_DEMO.md](docs/ADAPTIVE_LEARNING_DEMO.md), [docs/ADAPTIVE_UPGRADE_CONTRACT.md](docs/ADAPTIVE_UPGRADE_CONTRACT.md), and [docs/ADAPTIVE_V2_PRE_RELEASE_AUDIT.md](docs/ADAPTIVE_V2_PRE_RELEASE_AUDIT.md).

## Retrieval-augmented generation (RAG)

Lumi uses contextual curriculum grounding to ensure responses remain aligned with the student's current learning stage:

1. **Embedding generation**: Lesson slides are vectorized using `gemini-embedding-2`, configured to 768 output dimensions.
2. **Vector search**: Slides are stored in PostgreSQL using the pgvector extension. Cosine distance queries retrieve the top 3 most relevant slides matching the learner's query or current lesson context (distance threshold < 0.65).
3. **Retrieval strategy**: Production retrieval operates on the baseline vector search strategy (`legacy_semantic`). Experimental hybrid retrieval combining pgvector semantic similarity with PostgreSQL full-text search (`tsvector` and reciprocal rank fusion) was benchmarked and evaluated; because evaluation demonstrated statistically distinguishable recall degradation under paired bootstrap analysis and higher latency, `legacy_semantic` remains the authoritative production strategy. Detailed benchmark data is documented in [EVALUATION.md](EVALUATION.md).
4. **Prompt orchestration**: Retrieved slide excerpts, conversation history, and learner skill contexts are injected into a LangGraph state graph to generate accurate, level-appropriate explanations.

## Observability and telemetry

The backend includes a lightweight, privacy-safe AI telemetry service for operational visibility:

* **Configuration**: Controlled via `TELEMETRY_ENABLED` (default `true`), `TELEMETRY_SAMPLE_RATE` (default `1.0`, sampling applied only to successful events; failures are always retained), and `TELEMETRY_RETENTION_DAYS` (default `30`).
* **Non-fatal execution**: Telemetry writes run in separate database sessions and catch write failures, ensuring database logging issues never disrupt learner-facing chat or review requests.
* **Recorded metrics**: Tracks total duration, time-to-first-token (TTFT measured on first non-empty text token), model execution time, retrieval time, assessment proposal time, embedding time, model name, fallback status, retry count, token counts (`input_tokens`, `output_tokens`, `total_tokens` from provider metadata when available), and failure classifications (structured output failures, assessment rejection reasons, adaptive update failures, review scheduling failures, error categories).
* **Privacy-safe design**: Telemetry explicitly avoids recording prompt text, completion text, learner messages, or user identifiers (UIDs).
* **Local CLI reporting and pruning**:
  ```powershell
  cd spanish_amigo_api
  uv run python -m app.telemetry_cli --hours 24
  uv run python -m app.telemetry_cli --prune
  ```

## Technology inventory

### Frontend
* **React 19 & Vite 7**: Single-page application build tooling and runtime (`react` 19.2.0, `vite` 7.2.4).
* **React Router 7**: Client-side declarative routing with SPA rewrite support (`react-router-dom` 7.13.0).
* **Material UI 7 & Tailwind CSS 4**: Component library, responsive layout primitives, and styling tokens (`@mui/material` 7.3.7, `tailwindcss` 4.1.18).
* **Lucide React**: Vector iconography (`lucide-react` 0.563.0).
* **Firebase JS SDK**: Client-side authentication and session token handling (`firebase` 12.9.0).
* **React Markdown**: Client-side Markdown rendering for tutor messages (`react-markdown` 10.1.0).

### Backend
* **FastAPI & Uvicorn**: Asynchronous REST and Server-Sent Events API (`fastapi` 0.136.1, `uvicorn` 0.47.0).
* **Pydantic & Pydantic Settings**: Data validation, schema enforcement, and environment parsing (`pydantic-settings` 2.14.2).
* **SQLAlchemy 2.0 & Alembic**: Typed ORM, connection pooling, and database schema migrations (`sqlalchemy` 2.0.49, `alembic` 1.18.4).
* **psycopg 3**: PostgreSQL database adapter (`psycopg` 3.3.4).
* **Firebase Admin SDK**: Server-side cryptographic token verification (`firebase-admin` 7.4.0).
* **LangChain & LangGraph**: AI agent orchestration, tool routing, state graphs, and memory management (`langgraph` 1.2.0, `langchain-google-genai` 4.2.2).
* **Google GenAI SDK**: Model access for `gemini-3.5-flash-lite` (primary default), `gemma-4-31b-it` (fallback), and `gemini-embedding-2`.
* **py-fsrs**: Implementation of the Free Spaced Repetition Scheduler algorithm (`fsrs` 6.3.2).

### Infrastructure and tooling
* **PostgreSQL 18 (Neon)**: Relational database with pgvector extension.
* **Vercel**: Production hosting for frontend and backend deployments.
* **uv**: Deterministic Python package management and virtual environment execution.
* **npm**: Node.js package management.
* **Docker**: Containerized deployment specification (`spanish_amigo_api/Dockerfile`).
* **GitHub Actions**: Continuous integration, static analysis, unit testing, and dependency vulnerability scanning.
* **mypy**: Static type analysis for backend Python code.
* **pip-audit & npm audit**: Automated vulnerability auditing for Python and JavaScript dependencies.

## Database schema and migrations

The database schema is managed through Alembic. The repository and production database are both at Alembic revision `e1782f3a4b5c`.

```text
users
  |-- completed_lessons (user_id -> users.id)
  |-- chat_sessions (user_id -> users.id)
  |     `-- chat_messages (session_id -> chat_sessions.id)
  |-- learner_skill_states (user_id -> users.id, skill_id -> skills.skill_id)
  |-- assessment_events (user_id -> users.id, skill_id -> skills.skill_id)
  |-- practice_attempts (user_id -> users.id, skill_id -> skills.skill_id, source_assessment_event_id -> assessment_events.id)
  |-- review_items (user_id -> users.id, skill_id -> skills.skill_id)
        `-- review_history (review_item_id -> review_items.id)

skills
  `-- lesson_slide_skills (skill_id -> skills.skill_id, lesson_slide_id -> lesson_slides.id)
        `-- lesson_slides (stores content, 768-dim embeddings, tsvector)

ai_telemetry_events (operational latency, token, and failure metrics; content-free)

system_status (key-value application status, fallback tracking, and anonymous quotas)
```

### Alembic migration sequence

1. `2abc84cbeaea`: Initial schema (`users`, `completed_lessons`, `chat_messages`).
2. `e0671c685099`: Add `chat_sessions` table and session foreign keys.
3. `f1a2c3d4e5f6`: Ensure `lesson_slides` and `system_status` tables exist.
4. `a3b4c5d6e7f8`: Adaptive curriculum metadata (`skills`, `lesson_slide_skills`, pgvector embeddings, full-text search).
5. `b4c5d6e7f8a9`: Adaptive learner evidence storage (`learner_skill_states`, `assessment_events`, `practice_attempts`).
6. `c6d7e8f9a0b1`: Adaptive mastery mutation and FSRS review scheduling (`review_items`, `review_history`).
7. `d2e3f4a5b6c7`: Privacy-safe AI telemetry events (`ai_telemetry_events`).
8. `e1782f3a4b5c`: Targeted practice linkage (`source_assessment_event_id` foreign key and unique index on `practice_attempts`) — **current repository and production head**.

### Table descriptions

* `users`: User records keyed by Firebase UID string.
* `completed_lessons`: Completed lesson records per learner, unique on `(user_id, lesson_id)`.
* `chat_sessions`: Named multi-session conversation threads belonging to users.
* `chat_messages`: Individual user and assistant turns linked to sessions.
* `lesson_slides`: Curriculum slide content, slide types, explanations, 768-dimensional pgvector embeddings, CEFR levels, and `tsvector` full-text search columns.
* `skills`: The 14 stable curriculum skills with category, difficulty, CEFR level, and assessment mode constraints.
* `lesson_slide_skills`: Join table mapping lesson slides to curriculum skill IDs.
* `learner_skill_states`: Per-learner skill state tracking mastery estimates (0.0 to 1.0), confidence levels, accepted evidence counts, and attempt histories.
* `assessment_events`: Append-only audit log of proposed and validated assessment items, error classifications, evidence spans, and validator decisions.
* `practice_attempts`: Recorded practice submissions, snapshotting prompts, student answers, assistance levels, recall outcomes, and optional source assessment event linkage.
* `review_items`: FSRS card state per user and skill, tracking stability, difficulty, and next due timestamp.
* `review_history`: Immutable log of FSRS scheduler transitions and card rating changes.
* `ai_telemetry_events`: Content-free operational metrics recording execution latencies, TTFT, token usage, fallback status, and failure categories.
* `system_status`: Application key-value status, model fallback expiration tracking, and anonymous chat quotas.

## Repository structure

```text
.
|-- .github/
|   |-- dependabot.yml              # Automated dependency update configuration
|   `-- workflows/
|       |-- backend-ci.yml          # Python tests, mypy, and lockfile validation
|       `-- dependency-security.yml # pip-audit, npm audit, and dependency review
|-- docs/                           # Architecture references, demo steps, and audits
|-- public/                         # Static assets and favicon
|-- src/
|   |-- api/                        # Frontend API client endpoints
|   |-- components/
|   |   |-- auth/                   # Authentication modal and trigger components
|   |   |-- chat/                   # Floating chat widget, session manager, voice input
|   |   |-- common/                 # Reusable UI primitives
|   |   |-- course/                 # Course map journey, panels, and My Spanish
|   |   |-- layout/                 # Main application shell and navigation
|   |   `-- lesson/                 # Context, reveal, quiz, and completion slides
|   |-- context/                    # React Context providers (Auth, Progress, Theme)
|   |-- data/
|   |   `-- lessons/                # Frontend lesson content definitions (Lessons 1-5)
|   |-- hooks/                      # Custom React hooks
|   |-- pages/                      # View routes (CourseMap, LessonPlayer)
|   `-- theme/                      # MUI and Tailwind design tokens
|-- spanish_amigo_api/
|   |-- app/
|   |   |-- routers/                # API routes (adaptive, chat, progress)
|   |   |-- services/               # Core services (adaptive, ai, auth, retrieval, telemetry)
|   |   |-- config.py               # Pydantic Settings configuration
|   |   |-- curriculum_metadata.py  # 14 skills, taxonomy, and slide mappings
|   |   |-- database.py             # SQLAlchemy session and engine setup
|   |   |-- models.py               # SQLAlchemy database models
|   |   |-- schemas.py              # Pydantic request and response schemas
|   |   `-- telemetry_cli.py        # Telemetry reporting and pruning CLI
|   |-- evals/                      # Offline evaluation datasets, test runners, and reports
|   |-- migrations/                 # Alembic migration versions (repository head: e1782f3a4b5c)
|   |-- tests/                      # Unit and integration test suites
|   |-- Dockerfile                  # Container definition for backend service
|   |-- main.py                     # FastAPI application entry point
|   |-- pyproject.toml              # Python project metadata and dependencies
|   |-- seed_embeddings.py          # Idempotent curriculum and embedding backfill
|   `-- uv.lock                     # Deterministic Python dependency lockfile
|-- EVALUATION.md                   # Authoritative evaluation benchmarks, methodology, and metrics
|-- index.html
|-- package.json
|-- package-lock.json
|-- vercel.json                     # Frontend SPA routing configuration
`-- vite.config.js
```

## Local development

### Prerequisites

* Node.js (v20 or newer) and npm.
* Python (v3.12 or newer) and `uv`.
* PostgreSQL instance with `pgvector` enabled (such as Neon).
* Firebase project with Authentication (Anonymous and Google Sign-in enabled).
* Google Gemini API key.

### 1. Clone repository

```bash
git clone https://github.com/farazkhan-05/SpanishAmigo-Production-RAG-Application-with-Real-Time-AI-Chat.git
cd SpanishAmigo-Production-RAG-Application-with-Real-Time-AI-Chat
```

### 2. Configure frontend

Install dependencies:

```bash
npm install
```

Create `.env.local` in the project root:

```env
VITE_FIREBASE_API_KEY=your_firebase_api_key
VITE_FIREBASE_AUTH_DOMAIN=your_firebase_auth_domain
VITE_FIREBASE_PROJECT_ID=your_firebase_project_id
VITE_FIREBASE_STORAGE_BUCKET=your_firebase_storage_bucket
VITE_FIREBASE_MESSAGING_SENDER_ID=your_firebase_messaging_sender_id
VITE_FIREBASE_APP_ID=your_firebase_app_id
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Start the Vite development server:

```bash
npm run dev
```

### 3. Configure backend

Navigate to the backend directory and synchronize dependencies:

```bash
cd spanish_amigo_api
uv sync --locked
```

Create `spanish_amigo_api/.env`:

```env
ENV=development
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/spanish_amigo
GEMINI_API_KEY=your_gemini_api_key
FIREBASE_PROJECT_ID=your_firebase_project_id
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

### 4. Database migrations and seeding

Apply Alembic migrations to create tables and vector indexes:

```bash
uv run --locked alembic upgrade head
```

Run the idempotent curriculum and embedding backfill script:

```bash
uv run --locked python seed_embeddings.py
```

The seeding script evaluates existing database records against the curriculum taxonomy. It upserts the 14 skills, populates lesson slides and slide-to-skill join tables, and generates 768-dimensional embeddings for any new or modified slides without recreating existing vectors.

### 5. Start backend server

```bash
uv run --locked uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Verify backend health:

```bash
curl http://127.0.0.1:8000/health
```

## Configuration and environment variables

### Frontend variables (`.env.local`)

| Variable | Description |
| --- | --- |
| `VITE_FIREBASE_API_KEY` | Firebase Web API key for client-side authentication. |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase Authentication domain. |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project identifier. |
| `VITE_FIREBASE_STORAGE_BUCKET` | Firebase storage bucket. |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Firebase Cloud Messaging sender ID. |
| `VITE_FIREBASE_APP_ID` | Firebase application identifier. |
| `VITE_API_BASE_URL` | Base URL pointing to the running FastAPI backend. |

### Backend variables (`spanish_amigo_api/.env`)

| Variable | Description | Default |
| --- | --- | --- |
| `ENV` | Application runtime environment name (`development`, `production`). | `development` |
| `DATABASE_URL` | PostgreSQL connection URI (`postgresql+psycopg://...`). | Required |
| `GEMINI_API_KEY` | Google Gemini API key for chat, RAG, and embeddings. | Required |
| `FIREBASE_PROJECT_ID` | Firebase project ID used for token verification. | `spanishamigo-8016a` |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Optional JSON string containing service account credentials. | `""` |
| `ALLOWED_CORS_ORIGINS` | Comma-separated list of allowed client origins. | `http://localhost:5173,http://127.0.0.1:5173` |
| `AUTH_ALLOW_INSECURE_DEV_TOKENS` | Permits mock authentication tokens for test suites. | `false` |
| `LOG_LEVEL` | Application logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | `INFO` |
| `GEMINI_PRIMARY_MODEL` | Primary model for conversational tutoring and assessment. | `gemini-3.5-flash-lite` |
| `GEMINI_BACKUP_MODEL` | Fallback model used upon primary quota exhaustion. | `gemma-4-31b-it` |
| `GEMINI_EMBEDDING_MODEL` | Embedding model for semantic slide retrieval. | `gemini-embedding-2` |
| `ADAPTIVE_V2_PLANNER_ENABLED` | Feature flag activating the Adaptive V2 assessment engine. | `false` (source default; `true` in verified production) |
| `TELEMETRY_ENABLED` | Enables persistent, content-free AI telemetry. | `true` |
| `TELEMETRY_SAMPLE_RATE` | Successful-event sampling rate from `0.0` to `1.0`; failures are always retained. | `1.0` |
| `TELEMETRY_RETENTION_DAYS` | Telemetry retention and pruning horizon in days. | `30` |

### Production deployment sequence

For releases that include database migrations:

1. Verify the production environment configuration and required secrets.
2. Apply backward-compatible Alembic migrations (`uv run --locked alembic upgrade head`) before deploying application code that depends on the new schema.
3. Merge and push the tested release to `main`.
4. Allow the configured Vercel production deployments to complete.
5. Verify the backend `/health` endpoint, database connectivity, and expected primary model.
6. Run targeted production smoke tests for Lumi, adaptive practice, review scheduling, and telemetry.

## Authentication and security

* **Firebase token verification**: Protected endpoints require a valid Firebase bearer token. The backend verifies signature integrity, token expiration, and project claims via the Firebase Admin SDK.
* **Tenant data isolation**: The verified Firebase UID serves as the authoritative partition key for all database entities (completed lessons, chat sessions, messages, skill states, assessment events, practice attempts, and review items).
* **Anonymous usage quota**: Unauthenticated guest users are signed in anonymously and permitted up to three global chat interactions with Lumi before Google sign-in is required. Lesson 1 is accessible anonymously; subsequent lessons require sign-in.
* **Deterministic validation guardrails**: Assessment proposals from language models are subjected to strict deterministic validation rules, preventing ungrounded LLM output from modifying learner skill states.
* **Content-free telemetry**: Telemetry logging excludes prompts, model completions, and user identifiers.
* **Input validation**: Request schemas enforce character limits, string lengths, and parameter types using Pydantic.
* **Dependency security audits**: Automated CI pipelines run `pip-audit`, `npm audit`, Dependabot updates, and GitHub Dependency Review against pinned lockfiles (`uv.lock`, `package-lock.json`).

## Quality assurance and evaluation

### Automated testing

Frontend linting and production build verification:

```bash
npm run lint
npm run build
```

Backend unit and integration test suite:

```bash
cd spanish_amigo_api
uv run --locked python -m unittest discover -s tests -p "test_*.py"
```

Backend static type checking:

```bash
cd spanish_amigo_api
uv run --locked --with mypy mypy app/config.py app/services/auth.py app/services/health.py main.py --config-file mypy.ini
```

Dependency security scanning:

```bash
npm audit --omit=dev --audit-level=high

cd spanish_amigo_api
uv run --locked --with pip-audit pip-audit --desc
```

### Evaluation framework

The repository includes offline evaluation suites under `spanish_amigo_api/evals/` to test tutor behavior and assessment accuracy without external API calls:

* `golden_cases.jsonl`: Baseline cases verifying conversational and pedagogical boundaries.
* `phase5_cases.jsonl`: Validation cases verifying deterministic assessability gating, modality checks, and evidence extraction.
* `phase7_cases.jsonl`: End-to-end evaluation cases for turn planning and pedagogical action selection.

Run offline evaluation suites:

```powershell
cd spanish_amigo_api
uv run --locked python -m evals.run_eval phase7-offline --report evals/reports/phase7-offline.json
uv run --locked python -m evals.run_eval planner-offline --report evals/reports/phase5-planner.json
```

For comprehensive evaluation methodology, retrieval benchmarks, live Gemini 3.5 upgrade regression results against the historical Gemini 3.1 baseline, and hard safety invariant verification, see [EVALUATION.md](EVALUATION.md).

## Production deployment

* **Frontend hosting**: Vercel handles static site hosting and client-side routing via `vercel.json`.
* **Backend hosting**: Vercel runs the FastAPI application.
* **Database**: Neon PostgreSQL 18 provides managed PostgreSQL with the pgvector extension.
* **Container configuration**: `spanish_amigo_api/Dockerfile` provides a standalone Python 3.12 container definition using `uv` for frozen dependency synchronization.
