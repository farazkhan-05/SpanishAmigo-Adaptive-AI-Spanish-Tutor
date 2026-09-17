# Phase 5 targeted practice lifecycle

## Confirmed gap before this change

The existing chat planner persisted accepted `AssessmentEvent` rows with
`source_type="chat_message"` and used them for deterministic pedagogy. It did
not create a `PracticeAttempt`, and the chat path did not call
`process_accepted_evidence()`. A fresh learner therefore had no mastery state,
FSRS card, or review history after accepted chat evidence. The only existing
practice-to-mastery path was a server-issued due-review submission.

## Implemented lifecycle

An authenticated learner can receive one recommendation from their own
accepted, incorrect or partial, text chat assessment for an atomic non-vocabulary
skill. Starting it creates one server-owned `PracticeAttempt` linked to the
source assessment event. The target skill, exercise ID, and curriculum-grounded
prompt are stored by the server; the client submits only the attempt ID and new
learner response.

The response is assessed through the existing structured proposal mechanism and
the deterministic evidence validator. An accepted response must match the
server-owned target skill. Only then does the attempt become eligible and call
`process_accepted_evidence()`. That existing path remains the sole writer for
learner mastery and FSRS state, including first-card creation and immutable
review history. Chat events, rejected or ambiguous evidence, speech-required
skills, contextual skills, and broad vocabulary domains cannot cross that
boundary.

Targeted endpoints are:

- `GET /adaptive/practice/recommendation`
- `POST /adaptive/practice/start`
- `POST /adaptive/practice/{attempt_id}/submit`

The source-event and submission keys make start and submit retries idempotent.
Telemetry reuses content-free adaptive failure fields without transmitting learner
response text. Course completion state is unchanged.
