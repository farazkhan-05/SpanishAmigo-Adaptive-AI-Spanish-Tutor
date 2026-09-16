# SpanishAmigo

SpanishAmigo is a full-stack Spanish language learning web application that combines structured beginner lessons with an AI tutor named Lumi, real-time conversational practice, semantic curriculum retrieval, and deterministic adaptive skill tracking.

The frontend is built with React, Vite, Material UI, and Tailwind CSS. The backend is a FastAPI service that verifies Firebase authentication tokens, persists learner progress and chat history in PostgreSQL, orchestrates Google Gemini models through LangGraph, and schedules spaced repetition reviews using the Free Spaced Repetition Scheduler (FSRS) algorithm.

Live application:
* Frontend: [https://spanishamigo.vercel.app](https://spanishamigo.vercel.app)
* Backend API: [https://spanish-amigo-api.vercel.app](https://spanish-amigo-api.vercel.app)
* Health endpoint: [https://spanish-amigo-api.vercel.app/health](https://spanish-amigo-api.vercel.app/health)

## Architecture

SpanishAmigo separates student interactions into two operational layers: an interactive curriculum interface and an asynchronous AI tutoring and evaluation pipeline.

```mermaid
flowchart TD
    Client["React / Vite Frontend (Vercel)"]
    Auth["Firebase Authentication"]
    API["FastAPI Backend (Vercel)"]
    DB[("Neon PostgreSQL 18 + pgvector")]
    Orch["LangGraph Tutor Engine"]
    LLM["Google Gemini (gemini-3.1-flash-lite)"]
    Embed["Google Gemini Embeddings (gemini-embedding-2)"]
    Validator["Deterministic Validator"]
    FSRS["FSRS Review Engine"]

    Client -->|"ID Token"| Auth
    Client -->|"REST / SSE Streaming"| API
    API -->|"Token Verification"| Auth
    API -->|"State & Session Storage"| DB
    API -->|"Chat & Turn Orchestration"| Orch
    Orch -->|"Slide Embeddings / Search"| DB
    Orch -->|"Contextual Chat / Assessment Proposals"| LLM
    Embed -->|"768-dim Vectors"| DB
    LLM -->|"Proposals"| Validator
    Validator -->|"Assessment Events (Audit / Policy)"| DB
    API -->|"Review Submissions & Practice"| FSRS
    FSRS -->|"Learner States & Review Cards"| DB
    DB -->|"Adaptive Skill Metrics"| API
    API -->|"My Spanish Dashboard"| Client
```

The system components interact as follows:

1. **Frontend interface**: The client renders lesson progression, exercise interactions, audio playback, voice capture, and a persistent chat interface for Lumi.
2. **Authentication**: Firebase Authentication manages anonymous guest sessions and Google account linking. ID tokens are passed in HTTP request authorization headers.
3. **Backend API**: FastAPI validates request payloads with Pydantic, verifies user identity against Firebase Admin SDK, and routes requests to database services or the LangGraph AI engine.
4. **Retrieval and vector search**: PostgreSQL with the `pgvector` extension stores 768-dimensional embeddings of all curriculum lesson slides. Queries retrieve relevant lesson content to ground tutor responses in taught material.
5. **Adaptive skill evaluation**: When a learner interacts with Lumi, Gemini proposes structured assessment events that a deterministic validator checks before recording audit events in the database to guide pedagogical decisions. For server-issued review exercises, accepted eligible practice attempts execute deterministic state transitions that update learner skill states and FSRS review schedules.

## Learner experience

The application provides a structured progression for beginner Spanish students:

* **Five core lessons**: Structured modules covering foundational Spanish (greetings, survival expressions, politeness, directions, and café ordering).
* **Course map**: Visual navigation path tracking lesson unlocking, progress metrics, completion status, and achievement badges.
* **Interactive lesson player**: Modular slide flow providing context cards, translation reveals with instant AI explanations, and practice quiz slides with immediate feedback and hints.
* **Lumi AI tutor**: Floating conversational tutor available globally across the application and within individual lessons.
* **Real-time streaming chat**: Tutor responses stream incrementally via Server-Sent Events (SSE) with error recovery fallbacks.
* **Voice input and speech output**: Web Speech API integration for microphone input and spoken tutor pronunciation.
* **Session management**: Multi-session chat history allowing learners to create, switch, rename, and delete conversation threads.
* **Authentication flexibility**: Immediate guest access with local storage backup, with seamless upgrade to Google sign-in to persist cross-device progress.
* **Visual customization**: Full support for light and dark themes, toggled manually or requested conversationally through Lumi.

## Adaptive learning system

SpanishAmigo implements an adaptive tracking architecture (Adaptive V2) that separates course completion from skill mastery. Completing slides advances course navigation, while skill mastery requires verified recall over time.

### Core curriculum taxonomy

The curriculum defines 14 stable educational skills across four currently used categories:

* **Pronunciation**: `pronunciation.silent-h` (speech required).
* **Communication**: `communication.greetings`, `communication.formal-informal-address`, `communication.introductions-farewells`, `communication.politeness`, `communication.asking-directions`, `communication.cafe-ordering` (contextual).
* **Grammar**: `grammar.gender-agreement`, `grammar.present-tense-querer`, `grammar.present-tense-tener`.
* **Vocabulary**: `vocabulary.survival-needs`, `vocabulary.dining-basics`, `vocabulary.places-directions`, `vocabulary.cafe-items`.

Across the 5 lessons containing 231 total slides, 222 slides participate in skill mappings through 382 explicit associations, with 9 slides left intentionally unmapped where content does not test an atomic skill.

### The validation boundary and adaptive pathways

A foundational architectural rule governs skill mastery: **the language model may propose an assessment, but application code decides whether that proposal is valid evidence, and only eligible practice attempts can mutate mastery state.**

```text
Conversational Assessment Flow (Path A):
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

Eligible Practice and Review Flow (Path B):
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

The system strictly distinguishes between two processing paths:

* **Path A: Conversational assessment**: During live chat with Lumi, learner messages pass through an assessability gate. If assessable Spanish production is present, Gemini proposes an assessment that is verified by the deterministic validator. Accepted outcomes are persisted to `assessment_events` as audit evidence and inform Lumi's pedagogical policy (such as providing explanations, hints, or practice prompts). Chat assessments do not directly create eligible `practice_attempts`, modify `learner_skill_states`, or change FSRS review cards. An accepted incorrect or partial atomic text assessment may instead produce one server-owned targeted-practice recommendation.
* **Path B: Eligible practice and review evidence**: State mutation and spaced repetition scheduling require an explicit, eligible `PracticeAttempt` linked to a server-issued exercise. Targeted practice and due-review submissions undergo the same deterministic validation. If accepted, `process_accepted_evidence` transactionally updates `learner_skill_states` (computing mastery estimates and confidence), calculates FSRS card stability and difficulty, updates `review_items`, and records an immutable log in `review_history`.

### Mastery eligibility rules

To prevent invalid state updates, `process_accepted_evidence` and the deterministic validator enforce strict eligibility constraints:

* **Active practice requirement**: State mutation requires an eligible `PracticeAttempt` with active recall (`support_level != "exposure"`).
* **Modality constraints**: Skills flagged as `speech_required` (such as `pronunciation.silent-h`) cannot gain text mastery from typed responses.
* **Non-atomic skill constraints**: Contextual transfer skills (such as `communication.cafe-ordering`) represent scenario integration rather than atomic mastery and do not mutate numeric mastery states.
* **Vocabulary domain boundaries**: Broad vocabulary category skills are rejected for atomic text mastery in the validator.

### Safety and validation examples

1. **Conversational grammar demonstration**:
   * Input: *"Yo quiero un café, por favor."*
   * Result: Validated and recorded as an accepted assessment event for `grammar.present-tense-querer`, providing a pedagogical signal in chat without mutating learner mastery state.
2. **Conversational grammar mistake**:
   * Input: *"Yo tener dos hermanos."*
   * Result: Validated and recorded as an accepted incorrect assessment event for `grammar.present-tense-tener`, informing Lumi's response without directly modifying skill mastery or review queues.
3. **Server-issued review practice**:
   * Input: Learner submits *"Yo tengo dos hermanos."* in response to a server-issued review prompt for `grammar.present-tense-tener`.
   * Result: Validated with an eligible `PracticeAttempt`, triggering `process_accepted_evidence` to update the learner skill state and advance the FSRS review schedule.
4. **Information request**:
   * Input: *"Why do we say buenos días instead of buenas días?"*
   * Result: Identified as a question by the assessability gate. It is answered by Lumi but excluded from assessment proposals and mastery tracking.
5. **Modality gating**:
   * Input: Learner types text explaining that the letter H is silent.
   * Result: Rejected for `pronunciation.silent-h` because pronunciation skills require speech audio evidence.

### Spaced repetition and "My Spanish"

* **FSRS scheduling**: Validated review submissions feed into the Free Spaced Repetition Scheduler (`py-fsrs` 6.3.2), which computes card stability, difficulty, and next due review timestamps upon completing server-issued exercises.
* **Review queue**: Due reviews are surfaced through dedicated endpoints (`/adaptive/reviews/due` and `/adaptive/reviews/next`), issuing taxonomy-grounded recall prompts (`/adaptive/reviews/{id}/start`) and evaluating submissions (`/adaptive/reviews/{id}/submit`).
* **My Spanish panel**: A dedicated dashboard organizing the 14 curriculum skills into actionable categories:
  * *Needs practice*: Assessed skills with low mastery estimates or overdue spaced repetition reviews.
  * *Going well*: Assessed skills with high stability and demonstrated recall.
  * *Not assessed*: Skills where the learner has not yet completed validated practice attempts.

## Retrieval-augmented generation (RAG)

Lumi uses contextual curriculum grounding to ensure responses remain aligned with the student's current learning stage.

1. **Embedding generation**: Lesson slides are vectorized using `gemini-embedding-2`, configured to 768 output dimensions.
2. **Vector search**: Slides are stored in PostgreSQL using the `pgvector` extension. Cosine distance queries retrieve the top 3 most relevant slides matching the learner's query or current lesson context (distance threshold < 0.65).
3. **Hybrid retrieval capability**: The repository implements reciprocal rank fusion (RRF, k=60) combining `pgvector` semantic similarity with PostgreSQL full-text search (`tsvector`, `websearch_to_tsquery`, and `ts_rank_cd`). Production retrieval operates on the baseline vector search strategy, while hybrid retrieval remains an evaluation-tested capability.
4. **Prompt orchestration**: Retrieved slide excerpts, conversation history, and learner skill contexts are injected into a LangGraph state graph to generate accurate, level-appropriate explanations.

## Technology inventory

### Frontend
* **React 19 & Vite**: Single-page application build tooling and runtime.
* **React Router 7**: Client-side declarative routing with SPA rewrite support.
* **Material UI & Tailwind CSS 4**: Design system, responsive layout primitives, and styling tokens.
* **Lucide React**: Vector iconography.
* **Firebase JS SDK**: Client-side authentication and session token handling.

### Backend
* **FastAPI & Uvicorn**: Asynchronous REST and Server-Sent Events API.
* **Pydantic & Pydantic Settings**: Strict data validation, schema enforcement, and environment parsing.
* **SQLAlchemy 2.0 & Alembic**: Object-relational mapping, connection pooling, and database schema migrations.
* **psycopg 3**: PostgreSQL database adapter.
* **Firebase Admin SDK**: Server-side cryptographic token verification.
* **LangChain & LangGraph**: AI agent orchestration, tool routing, state graphs, and memory management.
* **Google GenAI SDK & langchain-google-genai**: Model access for `gemini-3.1-flash-lite` and `gemini-embedding-2`.
* **py-fsrs**: Implementation of the Free Spaced Repetition Scheduler algorithm.

### Infrastructure and tooling
* **PostgreSQL 18 (Neon)**: Relational database with `pgvector` extension.
* **Vercel**: Production hosting for frontend and backend deployments.
* **uv**: Python package management and virtual environment management.
* **npm**: Node.js package management.
* **Docker**: Containerized deployment specification.
* **GitHub Actions**: Continuous integration, static analysis, unit testing, and dependency vulnerability scanning.
* **mypy**: Static type analysis for backend Python code.
* **pip-audit & npm audit**: Automated vulnerability auditing for Python and JavaScript dependencies.

## Database schema

The database schema is managed through Alembic. The release-candidate repository head is `e1782f3a4b5c`; the
previously deployed production head is `c6d7e8f9a0b1`.

```text
users
  |-- completed_lessons (user_id -> users.id)
  |-- chat_sessions (user_id -> users.id)
  |     `-- chat_messages (session_id -> chat_sessions.id)
  |-- learner_skill_states (user_id -> users.id, skill_id -> skills.skill_id)
  |-- assessment_events (user_id -> users.id, skill_id -> skills.skill_id)
  |-- practice_attempts (user_id -> users.id, skill_id -> skills.skill_id)
  |-- review_items (user_id -> users.id, skill_id -> skills.skill_id)
        `-- review_history (review_item_id -> review_items.id)

skills
  `-- lesson_slide_skills (skill_id -> skills.skill_id, lesson_slide_id -> lesson_slides.id)
        `-- lesson_slides (stores content, 768-dim embeddings, tsvector)

system_status (key-value application status and seed tracking)
```

### Table descriptions

* `users`: Stores user identity, primary key matching the Firebase UID string.
* `completed_lessons`: Records lesson completions per learner, constrained by unique `(user_id, lesson_id)`.
* `chat_sessions`: Named multi-session conversation threads belonging to users.
* `chat_messages`: Individual user and assistant turns linked to sessions.
* `lesson_slides`: Course curriculum slides, slide types, explanations, 768-dimensional `pgvector` embeddings, CEFR levels, difficulties, learning objectives, and `tsvector` full-text search columns.
* `skills`: The 14 stable curriculum skills with category, difficulty, CEFR level, and assessment mode constraints.
* `lesson_slide_skills`: Join table mapping lesson slides to curriculum skill IDs.
* `learner_skill_states`: Per-learner skill state tracking mastery estimates (0.0 to 1.0), confidence levels, accepted evidence counts, and attempt histories.
* `assessment_events`: Append-only audit log of proposed and validated assessment items, error classifications, evidence spans, and validator decisions.
* `practice_attempts`: Recorded practice submissions, snapshotting prompts, student answers, assistance levels, and recall outcomes.
* `review_items`: FSRS card state per user and skill, tracking card status, stability, difficulty, and next due timestamp.
* `review_history`: Immutable log of FSRS scheduler transitions and card rating changes.
* `system_status`: Application state keys and metadata tracking.

## Repository structure

```text
.
|-- .github/
|   |-- dependabot.yml              # Automated dependency update configuration
|   `-- workflows/
|       |-- backend-ci.yml          # Python tests, mypy, and lockfile validation
|       `-- dependency-security.yml # pip-audit, npm audit, and dependency review
|-- docs/                           # Architecture references and development guides
|-- public/                         # Static assets and favicon
|-- src/
|   |-- api/                        # Frontend API client endpoints
|   |-- components/
|   |   |-- auth/                   # Authentication modal and trigger components
|   |   |-- chat/                   # Floating chat widget, session manager, voice
|   |   |-- common/                 # Reusable UI components
|   |   |-- course/                 # Course map journey, panels, and My Spanish
|   |   |-- layout/                 # Main application shell and navigation
|   |   `-- lesson/                 # Context, reveal, quiz, and completion slides
|   |-- context/                    # React Context providers (Auth, Progress, Theme)
|   |-- data/
|   |   `-- lessons/                # Frontend lesson content definitions (Lessons 1-5)
|   |-- hooks/                      # Custom React hooks
|   |-- pages/                      # Top-level view routes (CourseMap, LessonPlayer)
|   `-- theme/                      # MUI and Tailwind design tokens
|-- spanish_amigo_api/
|   |-- app/
|   |   |-- routers/                # API routes (adaptive, chat, progress)
|   |   |-- services/               # Core services (adaptive, ai, auth, retrieval)
|   |   |-- config.py               # Pydantic Settings configuration
|   |   |-- curriculum_metadata.py  # 14 skills, taxonomy, and slide mappings
|   |   |-- database.py             # SQLAlchemy session and engine setup
|   |   |-- models.py               # SQLAlchemy database models
|   |   `-- schemas.py              # Pydantic request and response schemas
|   |-- evals/                      # Offline evaluation datasets and runners
|   |-- migrations/                 # Alembic migration versions (release-candidate head: e1782f3a4b5c)
|   |-- tests/                      # Unit and integration test suites
|   |-- Dockerfile                  # Container definition for backend service
|   |-- main.py                     # FastAPI application entry point
|   |-- pyproject.toml              # Python project metadata and dependencies
|   |-- seed_embeddings.py          # Idempotent curriculum and embedding backfill
|   `-- uv.lock                     # Deterministic Python dependency lockfile
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
GEMINI_PRIMARY_MODEL=gemini-3.1-flash-lite
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
| `ENV` | Application runtime environment name. | `development` |
| `DATABASE_URL` | PostgreSQL connection URI (`postgresql+psycopg://...`). | Required |
| `GEMINI_API_KEY` | Google Gemini API key for chat, RAG, and embeddings. | Required |
| `FIREBASE_PROJECT_ID` | Firebase project ID used for token verification. | `spanishamigo-8016a` |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Optional JSON string containing service account credentials. | `""` |
| `ALLOWED_CORS_ORIGINS` | Comma-separated list of allowed client origins. | `http://localhost:5173,http://127.0.0.1:5173` |
| `AUTH_ALLOW_INSECURE_DEV_TOKENS` | Permits mock authentication tokens for test suites. | `false` |
| `LOG_LEVEL` | Application logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | `INFO` |
| `GEMINI_PRIMARY_MODEL` | Primary model for conversational tutoring and assessment. | `gemini-3.1-flash-lite` |
| `GEMINI_BACKUP_MODEL` | Fallback model used upon primary quota exhaustion. | `gemma-4-31b-it` |
| `GEMINI_EMBEDDING_MODEL` | Embedding model for semantic slide retrieval. | `gemini-embedding-2` |
| `ADAPTIVE_V2_PLANNER_ENABLED` | Feature flag activating the Adaptive V2 assessment engine. | `false` |
| `TELEMETRY_ENABLED` | Enables persistent, content-free AI telemetry. | `true` |
| `TELEMETRY_SAMPLE_RATE` | Successful-event sampling rate from `0.0` to `1.0`; failures remain retained. | `1.0` |
| `TELEMETRY_RETENTION_DAYS` | Positive integer telemetry retention/pruning horizon. | `30` |

### Production state and activation order

The source default for `ADAPTIVE_V2_PLANNER_ENABLED` is `false`; the previously deployed Adaptive V2 baseline was
verified with the production environment value `true`. This does not mean the telemetry and targeted-practice changes
on this branch are deployed. The release-candidate migrations `d2e3f4a5b6c7` and `e1782f3a4b5c` remain pending.

When deploying to production, follow this sequence:

1. Deploy the backend API to the hosting platform.
2. Execute database schema migrations (`alembic upgrade head`).
3. Run the curriculum seeding script (`seed_embeddings.py`) to initialize skills and generate embeddings.
4. Verify backend connectivity via the `/health` endpoint.
5. Preserve the previously verified production environment value `ADAPTIVE_V2_PLANNER_ENABLED=true`; the source
   default remains `false`.
6. Verify adaptive endpoints (`/adaptive/state`, `/adaptive/reviews/due`).

## Authentication and security

* **Firebase token verification**: All protected endpoints require a valid Firebase bearer token. The backend verifies signature integrity, token expiration, and project claims via the Firebase Admin SDK.
* **Tenant data isolation**: The verified Firebase UID serves as the authoritative partition key for all database entities (completed lessons, chat sessions, messages, skill states, assessment events, and review items).
* **Anonymous usage quota**: Unauthenticated guest users are signed in anonymously and permitted up to three global chat interactions with Lumi before Google account sign-in is required.
* **Deterministic validation guardrails**: Assessment proposals from language models are subjected to strict deterministic validation rules, preventing ungrounded LLM output from corrupting learner skill states.
* **Input boundary constraints**: Request schemas enforce message character limits, string lengths, and parameter types using Pydantic.
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

### Offline evaluation framework

The repository includes an offline evaluation framework under `spanish_amigo_api/evals/` designed to test tutor behavior and assessment accuracy without external API calls:

* `golden_cases.jsonl`: Curated baseline cases verifying conversational and pedagogical boundaries.
* `phase5_cases.jsonl`: Validation cases verifying deterministic assessability gating, modality checks, and evidence extraction.
* `phase7_cases.jsonl`: End-to-end evaluation cases for turn planning and pedagogical action selection.

Run offline evaluation suites:

```bash
cd spanish_amigo_api
uv run --locked python evals/run_eval.py offline
```

## Deployment

The production deployment runs on serverless and managed cloud infrastructure:

* **Frontend hosting**: Vercel handles static site generation and client-side routing via `vercel.json`.
* **Backend hosting**: Vercel runs the FastAPI application.
* **Database**: Neon PostgreSQL 18 provides managed PostgreSQL with the `pgvector` extension.
* **Container configuration**: `spanish_amigo_api/Dockerfile` provides a standalone Python 3.12 container definition for container-based environments.

## Current scope and boundaries

SpanishAmigo currently provides five structured beginner lessons covering core A1 Spanish concepts. The underlying technical infrastructure (RAG retrieval pipeline, LangGraph state orchestration, deterministic assessment validation, and FSRS spaced repetition scheduling) is designed to support expanded curricula, while the authored lesson content remains focused on foundational beginner scenarios.
