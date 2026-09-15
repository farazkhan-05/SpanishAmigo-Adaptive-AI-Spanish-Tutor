import os
import sys
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine, delete, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db
from app.models import AssessmentEvent, ChatMessage, ChatSession, CompletedLesson, LearnerSkillState, PracticeAttempt, Skill, SystemStatus, User
from app.curriculum_metadata import SKILLS
from app.services.adaptive import create_assessment_event, create_practice_attempt, create_unknown_state
from app.services.ai import save_memory_node
from app.services.auth import get_current_user
from main import app


CURRENT_TEST_USER: dict[str, Any] = {
    "uid": "user-a",
    "email": "user-a@example.com",
    "firebase": {"sign_in_provider": "google.com"},
}


def _override_current_user() -> dict[str, Any]:
    return CURRENT_TEST_USER


class TestBackendIntegrationFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "integration.sqlite3")
        cls.engine = create_engine(
            f"sqlite:///{cls.db_path}",
            connect_args={"check_same_thread": False},
        )
        @event.listens_for(cls.engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
        cls.TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

        # Create only tables needed by these tests.
        User.__table__.create(bind=cls.engine, checkfirst=True)
        CompletedLesson.__table__.create(bind=cls.engine, checkfirst=True)
        ChatSession.__table__.create(bind=cls.engine, checkfirst=True)
        ChatMessage.__table__.create(bind=cls.engine, checkfirst=True)
        Skill.__table__.create(bind=cls.engine, checkfirst=True)
        LearnerSkillState.__table__.create(bind=cls.engine, checkfirst=True)
        AssessmentEvent.__table__.create(bind=cls.engine, checkfirst=True)
        PracticeAttempt.__table__.create(bind=cls.engine, checkfirst=True)
        SystemStatus.__table__.create(bind=cls.engine, checkfirst=True)

        def _override_db():
            db = cls.TestSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_current_user
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.temp_dir.cleanup()

    def setUp(self):
        self._set_current_user("user-a", provider="google.com", email="user-a@example.com")
        self._reset_db()

    def _set_current_user(self, uid: str, provider: str = "google.com", email: str | None = None) -> None:
        CURRENT_TEST_USER.clear()
        CURRENT_TEST_USER.update(
            {
                "uid": uid,
                "email": email or f"{uid}@example.com",
                "firebase": {"sign_in_provider": provider},
            }
        )

    def _reset_db(self) -> None:
        db = self.TestSessionLocal()
        try:
            db.execute(delete(ChatMessage))
            db.execute(delete(ChatSession))
            db.execute(delete(PracticeAttempt))
            db.execute(delete(AssessmentEvent))
            db.execute(delete(LearnerSkillState))
            db.execute(delete(CompletedLesson))
            db.execute(delete(SystemStatus))
            db.execute(delete(Skill))
            db.execute(delete(User))
            db.add_all([Skill(skill_id=s.skill_id, display_label=s.display_label, description=s.description, category=s.category, cefr_level=s.cefr_level, difficulty=s.difficulty, learning_objective=s.learning_objective, assessment_mode=s.assessment_mode, taxonomy_version="spanishamigo-v1") for s in SKILLS])
            db.commit()
        finally:
            db.close()

    def _seed_user(self, user_id: str, email: str | None = None) -> None:
        db = self.TestSessionLocal()
        try:
            db.add(User(id=user_id, email=email or f"{user_id}@example.com"))
            db.commit()
        finally:
            db.close()

    def _seed_progress(self, user_id: str, lesson_id: str) -> None:
        db = self.TestSessionLocal()
        try:
            if not db.get(User, user_id):
                db.add(User(id=user_id, email=f"{user_id}@example.com"))
                db.commit()
            db.add(CompletedLesson(user_id=user_id, lesson_id=lesson_id))
            db.commit()
        finally:
            db.close()

    def _seed_session_with_messages(self, user_id: str, title: str = "Chat") -> int:
        db = self.TestSessionLocal()
        try:
            if not db.get(User, user_id):
                db.add(User(id=user_id, email=f"{user_id}@example.com"))
                db.commit()

            session = ChatSession(user_id=user_id, title=title)
            db.add(session)
            db.commit()
            db.refresh(session)

            db.add(ChatMessage(user_id=user_id, session_id=session.id, role="user", content="hola"))
            db.add(ChatMessage(user_id=user_id, session_id=session.id, role="assistant", content="¡hola!"))
            db.commit()
            return session.id
        finally:
            db.close()

    @staticmethod
    def _fake_tutor_invoke(state_input: dict[str, Any]) -> dict[str, Any]:
        reply_text = "Lumi test reply"
        memory_state = {
            **state_input,
            "messages": [*state_input["messages"], AIMessage(content=reply_text)],
        }
        save_memory_node(memory_state, state_input["db"])
        return {"messages": [AIMessage(content=reply_text)]}

    def test_tenancy_user_a_cannot_read_user_b_progress(self):
        self._seed_progress("user-b", "lesson-1")
        self._set_current_user("user-a")

        response = self.client.get("/progress/user-b")

        self.assertEqual(response.status_code, 403)
        self.assertIn("Cannot view another user's progress", response.json()["detail"])

    def test_client_progress_user_id_cannot_override_verified_uid(self):
        self._set_current_user("user-a")

        response = self.client.post(
            "/progress/complete",
            json={"user_id": "user-b", "lesson_id": "1"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("Cannot submit progress on behalf of another user", response.json()["detail"])

    def test_anonymous_user_can_persist_the_current_progress_contract(self):
        self._set_current_user("anonymous-user", provider="anonymous")

        response = self.client.post(
            "/progress/complete",
            json={"user_id": "anonymous-user", "lesson_id": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lesson_id"], "1")

    def test_adaptive_state_is_authenticated_tenant_scoped_and_unknown(self):
        self._seed_user("user-a")
        self._seed_user("user-b")
        db = self.TestSessionLocal()
        try:
            create_unknown_state(db, "user-b", "grammar.present-tense-tener")
            db.commit()
        finally:
            db.close()
        self._set_current_user("user-a")

        response = self.client.get("/adaptive/state?skill_id=grammar.present-tense-tener")

        self.assertEqual(response.status_code, 200)
        item = response.json()[0]
        self.assertIsNone(item["mastery_estimate"])
        self.assertEqual(item["status"], "not_assessed")
        self.assertEqual(item["accepted_evidence_count"], 0)

    def test_adaptive_state_rejects_invalid_skill_and_supports_anonymous_uid(self):
        self._set_current_user("anonymous-user", provider="anonymous")
        invalid = self.client.get("/adaptive/state?skill_id=not-a-skill")
        response = self.client.get("/adaptive/state?skill_id=pronunciation.silent-h")
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["assessment_mode"], "speech_required")

    def test_adaptive_storage_idempotency_and_contextual_guardrail(self):
        self._seed_user("user-a")
        db = self.TestSessionLocal()
        try:
            first = create_assessment_event(db, verified_uid="user-a", skill_id="grammar.present-tense-tener", source_type="chat_message", evidence_snapshot="Tengo un boleto.", proposed_result="correct", source_event_key="trusted-message-1")
            same = create_assessment_event(db, verified_uid="user-a", skill_id="grammar.present-tense-tener", source_type="chat_message", evidence_snapshot="ignored duplicate", proposed_result="correct", source_event_key="trusted-message-1")
            attempt = create_practice_attempt(db, verified_uid="user-a", skill_id="grammar.present-tense-tener", exercise_type="recall", source_event_key="trusted-attempt-1", learner_response_snapshot="Tengo un boleto.")
            duplicate_attempt = create_practice_attempt(db, verified_uid="user-a", skill_id="grammar.present-tense-tener", exercise_type="recall", source_event_key="trusted-attempt-1")
            self.assertEqual(first.id, same.id)
            self.assertEqual(attempt.id, duplicate_attempt.id)
            with self.assertRaises(ValueError):
                create_unknown_state(db, "user-a", "communication.cafe-ordering")
            db.commit()
            self.assertEqual(db.query(AssessmentEvent).count(), 1)
            self.assertEqual(db.query(PracticeAttempt).count(), 1)
            self.assertIsNone(db.query(LearnerSkillState).first())
        finally:
            db.close()

    def test_adaptive_constraints_and_assessment_mode_foundation(self):
        self._seed_user("user-a")
        db = self.TestSessionLocal()
        try:
            db.add(LearnerSkillState(user_id="user-a", skill_id="grammar.present-tense-tener", mastery_estimate=1.1))
            with self.assertRaises(IntegrityError):
                db.flush()
            db.rollback()
            with self.assertRaises(ValueError):
                create_assessment_event(db, verified_uid="user-a", skill_id="grammar.present-tense-tener", source_type="chat_message", evidence_snapshot="", proposed_result="unknown", validation_status="accepted")
            from app.services.adaptive import mastery_eligibility
            self.assertTrue(mastery_eligibility("grammar.present-tense-tener", "text"))
            self.assertFalse(mastery_eligibility("pronunciation.silent-h", "text"))
            # A vocabulary event stays an event: it creates no whole-domain state row.
            create_assessment_event(db, verified_uid="user-a", skill_id="vocabulary.dining-basics", source_type="chat_message", evidence_snapshot="agua", proposed_result="correct")
            db.commit()
            self.assertIsNone(db.query(LearnerSkillState).filter_by(skill_id="vocabulary.dining-basics").first())
        finally:
            db.close()

    def test_chat_deletion_keeps_evidence_snapshot_and_nulls_provenance(self):
        session_id = self._seed_session_with_messages("user-a")
        db = self.TestSessionLocal()
        try:
            message = db.query(ChatMessage).filter_by(session_id=session_id, role="user").first()
            assessment = create_assessment_event(db, verified_uid="user-a", skill_id="grammar.present-tense-tener", source_type="chat_message", evidence_snapshot="Tengo un boleto.", proposed_result="correct", chat_session_id=session_id, chat_message_id=message.id)
            assessment_id = assessment.id
            db.commit()
            db.delete(db.get(ChatSession, session_id))
            db.commit()
            retained = db.get(AssessmentEvent, assessment_id)
            self.assertEqual(retained.evidence_snapshot, "Tengo un boleto.")
            self.assertIsNone(retained.chat_session_id)
            self.assertIsNone(retained.chat_message_id)
        finally:
            db.close()

    def test_tenancy_user_a_cannot_access_user_b_chat_history(self):
        session_id = self._seed_session_with_messages("user-b")
        self._set_current_user("user-a")

        by_session = self.client.get(f"/chat/history/session/{session_id}")
        by_user = self.client.get("/chat/history/user-b")

        self.assertEqual(by_session.status_code, 403)
        self.assertIn("Cannot access another user's chat history", by_session.json()["detail"])
        self.assertEqual(by_user.status_code, 403)
        self.assertIn("Cannot access another user's chat history", by_user.json()["detail"])

    def test_tenancy_user_a_cannot_rename_or_delete_user_b_session(self):
        session_id = self._seed_session_with_messages("user-b")
        self._set_current_user("user-a")

        rename_response = self.client.put(
            f"/chat/sessions/{session_id}",
            json={"title": "Hacked title"},
        )
        delete_response = self.client.delete(f"/chat/sessions/{session_id}")

        self.assertEqual(rename_response.status_code, 403)
        self.assertIn("Cannot modify another user's session", rename_response.json()["detail"])
        self.assertEqual(delete_response.status_code, 403)
        self.assertIn("Cannot delete another user's session", delete_response.json()["detail"])

    def test_session_list_only_returns_verified_users_sessions(self):
        user_a_session = self._seed_session_with_messages("user-a", "User A")
        self._seed_session_with_messages("user-b", "User B")
        self._set_current_user("user-a")

        response = self.client.get("/chat/sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([session["id"] for session in response.json()], [user_a_session])

    @patch("app.routers.chat.update_session_title_in_background", return_value=None)
    @patch("app.routers.chat.tutor_graph.invoke")
    def test_send_rejects_another_users_session_and_client_uid(self, mock_invoke, _mock_bg_title):
        mock_invoke.side_effect = self._fake_tutor_invoke
        session_id = self._seed_session_with_messages("user-b")
        self._set_current_user("user-a")

        mismatched_uid = self.client.post(
            "/chat/send",
            json={"user_id": "user-b", "message": "Hola", "session_id": None},
        )
        foreign_session = self.client.post(
            "/chat/send",
            json={"user_id": "user-a", "message": "Hola", "session_id": session_id},
        )

        self.assertEqual(mismatched_uid.status_code, 403)
        self.assertEqual(foreign_session.status_code, 403)
        self.assertIn("Invalid session ID", foreign_session.json()["detail"])
        mock_invoke.assert_not_called()

    @patch("app.routers.chat.update_session_title_in_background", return_value=None)
    @patch("app.routers.chat.tutor_graph.invoke")
    def test_session_lifecycle_create_fetch_rename_delete(self, mock_invoke, _mock_bg_title):
        mock_invoke.side_effect = self._fake_tutor_invoke
        self._set_current_user("user-a")

        create_response = self.client.post(
            "/chat/send",
            json={
                "user_id": "user-a",
                "message": "Hola Lumi",
                "user_name": "Amigo",
                "session_id": None,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created_session_id = create_response.json()["session_id"]
        self.assertIsInstance(created_session_id, int)

        history_response = self.client.get(f"/chat/history/session/{created_session_id}")
        self.assertEqual(history_response.status_code, 200)
        history = history_response.json()
        self.assertGreaterEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "model")

        rename_response = self.client.put(
            f"/chat/sessions/{created_session_id}",
            json={"title": "Renamed session"},
        )
        self.assertEqual(rename_response.status_code, 200)
        self.assertEqual(rename_response.json()["title"], "Renamed session")

        delete_response = self.client.delete(f"/chat/sessions/{created_session_id}")
        self.assertEqual(delete_response.status_code, 200)

        sessions_response = self.client.get("/chat/sessions")
        self.assertEqual(sessions_response.status_code, 200)
        remaining_ids = {session["id"] for session in sessions_response.json()}
        self.assertNotIn(created_session_id, remaining_ids)

    @patch("app.routers.chat.generate_explanation", return_value="Short explanation")
    def test_explain_endpoint_valid_request_returns_200(self, _mock_explain):
        response = self.client.post(
            "/chat/explain",
            json={
                "spanish_sentence": "Tengo hambre",
                "english_translation": "I am hungry",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["explanation"], "Short explanation")

    @patch("app.routers.chat.generate_explanation", return_value="Short explanation")
    def test_explain_endpoint_requires_authentication(self, _mock_explain):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            response = self.client.post(
                "/chat/explain",
                json={
                    "spanish_sentence": "Tengo hambre",
                    "english_translation": "I am hungry",
                },
            )
        finally:
            app.dependency_overrides[get_current_user] = _override_current_user

        self.assertIn(response.status_code, {401, 403})
        _mock_explain.assert_not_called()

    def test_explain_endpoint_invalid_payload_returns_422(self):
        response = self.client.post(
            "/chat/explain",
            json={"spanish_sentence": "Tengo hambre"},
        )
        self.assertEqual(response.status_code, 422)

    @patch("app.routers.chat.generate_explanation", side_effect=Exception("model down"))
    def test_explain_endpoint_error_path_returns_controlled_500(self, _mock_explain):
        response = self.client.post(
            "/chat/explain",
            json={
                "spanish_sentence": "Tengo hambre",
                "english_translation": "I am hungry",
            },
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"],
            "Unable to generate explanation right now. Please try again.",
        )

    @patch("app.routers.chat.update_session_title_in_background", return_value=None)
    @patch("app.services.ai.save_memory_node", return_value={})
    @patch("app.services.ai.prepare_tutor_messages", return_value=[HumanMessage(content="hola")])
    @patch("app.services.ai.guardrails_node", return_value={"guardrail_blocked": False})
    @patch("app.routers.chat.astream_with_fallback")
    def test_stream_endpoint_returns_chunks_and_done(
        self,
        mock_astream,
        _mock_guardrails,
        _mock_prepare,
        _mock_save_memory,
        _mock_bg_title,
    ):
        async def _fake_stream(*_args, **_kwargs):
            class Chunk:
                def __init__(self, content):
                    self.content = content
                    self.tool_calls = []

            yield Chunk("Hola")
            yield Chunk(" amigo")

        mock_astream.side_effect = _fake_stream

        response = self.client.post(
            "/chat/send_stream",
            json={
                "user_id": "user-a",
                "message": "Hola",
                "user_name": "Amigo",
                "session_id": None,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("session_id", body)
        self.assertIn('"token": "Hola"', body)
        self.assertIn('"token": " amigo"', body)
        self.assertIn("[DONE]", body)

    @patch("app.routers.chat.update_session_title_in_background", return_value=None)
    @patch("app.services.ai.save_memory_node", return_value={})
    @patch("app.services.ai.prepare_tutor_messages", return_value=[HumanMessage(content="hola")])
    @patch("app.services.ai.guardrails_node", return_value={"guardrail_blocked": False})
    @patch("app.routers.chat.astream_with_fallback")
    def test_stream_endpoint_preserves_theme_action_frame(
        self,
        mock_astream,
        _mock_guardrails,
        _mock_prepare,
        _mock_save_memory,
        _mock_bg_title,
    ):
        async def _fake_stream(*_args, **_kwargs):
            class Chunk:
                content = ""
                tool_calls = [{"name": "toggle_theme"}]

            yield Chunk()

        mock_astream.side_effect = _fake_stream

        response = self.client.post(
            "/chat/send_stream",
            json={"user_id": "user-a", "message": "dark mode", "session_id": None},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('"action_required": "TOGGLE_THEME"', response.text)
        self.assertIn("[DONE]", response.text)

    @patch("app.routers.chat.update_session_title_in_background", return_value=None)
    @patch("app.services.ai.save_memory_node", return_value={})
    @patch("app.services.ai.prepare_tutor_messages", return_value=[HumanMessage(content="hola")])
    @patch("app.services.ai.guardrails_node", return_value={"guardrail_blocked": False})
    @patch("app.routers.chat.astream_with_fallback")
    def test_stream_endpoint_model_error_returns_graceful_fallback_token(
        self,
        mock_astream,
        _mock_guardrails,
        _mock_prepare,
        _mock_save_memory,
        _mock_bg_title,
    ):
        async def _boom_stream(*_args, **_kwargs):
            if False:
                yield None
            raise RuntimeError("stream failed")

        mock_astream.side_effect = _boom_stream

        response = self.client.post(
            "/chat/send_stream",
            json={
                "user_id": "user-a",
                "message": "Hola",
                "user_name": "Amigo",
                "session_id": None,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("unexpected error during response generation", body)
        self.assertIn("[DONE]", body)


if __name__ == "__main__":
    unittest.main()
