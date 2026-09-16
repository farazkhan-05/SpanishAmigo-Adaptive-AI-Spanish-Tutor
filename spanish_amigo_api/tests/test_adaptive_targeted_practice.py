import os
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.curriculum_metadata import SKILLS, TAXONOMY_VERSION
from app.database import Base, get_db
from main import app
from app.models import (
    AssessmentEvent,
    ChatMessage,
    ChatSession,
    CompletedLesson,
    LearnerSkillState,
    PracticeAttempt,
    ReviewHistory,
    ReviewItem,
    Skill,
    User,
)
from app.schemas import AssessmentProposal
from app.services.adaptive import (
    assess_targeted_practice_submission,
    create_assessment_event,
    create_practice_attempt,
    get_targeted_practice_recommendation,
    process_accepted_evidence,
    start_targeted_practice,
)
from app.services.auth import get_current_user


class TargetedPracticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(cls.engine, "connect")
        def _foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        cls.SessionLocal = sessionmaker(bind=cls.engine)
        cls.tables = (
            User.__table__,
            CompletedLesson.__table__,
            ChatSession.__table__,
            ChatMessage.__table__,
            Skill.__table__,
            LearnerSkillState.__table__,
            AssessmentEvent.__table__,
            ReviewItem.__table__,
            PracticeAttempt.__table__,
            ReviewHistory.__table__,
        )
        for table in cls.tables:
            table.create(bind=cls.engine, checkfirst=True)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self):
        self.db = self.SessionLocal()
        self.db.add_all([User(id="learner-a"), User(id="learner-b")])
        self.db.add(CompletedLesson(user_id="learner-a", lesson_id="lesson-1"))
        self.db.add_all([
            Skill(
                skill_id=skill.skill_id,
                display_label=skill.display_label,
                description=skill.description,
                category=skill.category,
                cefr_level=skill.cefr_level,
                difficulty=skill.difficulty,
                learning_objective=skill.learning_objective,
                assessment_mode=skill.assessment_mode,
                taxonomy_version=TAXONOMY_VERSION,
            )
            for skill in SKILLS
        ])
        self.db.commit()
        app.dependency_overrides[get_db] = self._get_db
        app.dependency_overrides[get_current_user] = lambda: {"uid": "learner-a"}

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        app.dependency_overrides.clear()
        with self.engine.begin() as connection:
            for table in reversed(self.tables):
                connection.exec_driver_sql(f"DELETE FROM {table.name}")

    def _get_db(self):
        yield self.db

    def _proposal(self, **overrides):
        values = {
            "assessable": True,
            "skill_id": "grammar.present-tense-querer",
            "result": "correct",
            "error_type": None,
            "severity": None,
            "confidence": 0.95,
            "evidence": "Yo quiero un café",
            "correction": None,
            "misconception_id": None,
            "assessment_version": "phase5-v1",
        }
        values.update(overrides)
        return AssessmentProposal.model_validate(values)

    def _chat_event(self, *, user="learner-a", skill_id="grammar.present-tense-querer", result="incorrect", modality="text", status="accepted"):
        event = create_assessment_event(
            self.db,
            verified_uid=user,
            skill_id=skill_id,
            source_type="chat_message",
            evidence_snapshot="Yo quiero un café",
            proposed_result=result,
            validation_status=status,
            evidence_modality=modality,
            proposal_confidence=0.95,
            source_event_key=f"chat-{uuid4()}",
        )
        self.db.commit()
        return event

    def test_fresh_learner_api_lifecycle_creates_first_state_card_and_history(self):
        source = self._chat_event()
        completion_count = self.db.query(CompletedLesson).filter_by(user_id="learner-a").count()
        self.assertIsNone(self.db.query(LearnerSkillState).first())
        self.assertIsNone(self.db.query(ReviewItem).first())
        self.assertIsNone(self.db.query(ReviewHistory).first())

        recommendation = self.client.get("/adaptive/practice/recommendation")
        self.assertEqual(recommendation.status_code, 200)
        self.assertTrue(recommendation.json()["available"])
        self.assertEqual(recommendation.json()["source_event_id"], source.id)

        started = self.client.post("/adaptive/practice/start", json={"source_event_id": source.id})
        self.assertEqual(started.status_code, 200)
        attempt_id = started.json()["attempt_id"]
        self.assertEqual(started.json()["skill_id"], source.skill_id)
        self.assertNotIn("Yo quiero", started.json()["exercise_text"])
        duplicate_start = self.client.post("/adaptive/practice/start", json={"source_event_id": source.id})
        self.assertEqual(duplicate_start.json()["attempt_id"], attempt_id)
        self.assertEqual(self.db.query(PracticeAttempt).count(), 1)

        with patch("app.services.ai.propose_assessment", return_value=(self._proposal(), "mock")):
            submitted = self.client.post(
                f"/adaptive/practice/{attempt_id}/submit",
                json={"learner_answer": "Yo quiero un café"},
            )
        self.assertEqual(submitted.status_code, 200)
        self.assertTrue(submitted.json()["mastery_updated"])
        self.assertIsNotNone(submitted.json()["due_at"])
        self.assertIsNotNone(self.db.query(LearnerSkillState).one().mastery_estimate)
        item = self.db.query(ReviewItem).one()
        history = self.db.query(ReviewHistory).one()
        self.assertEqual(history.review_item_id, item.id)
        self.assertEqual(history.due_at, item.due_at)
        self.assertEqual(history.assessment_event_id, self.db.query(PracticeAttempt).one().assessment_event_id)
        self.assertEqual(self.db.query(PracticeAttempt).one().outcome, "correct")
        self.assertEqual(
            self.db.query(CompletedLesson).filter_by(user_id="learner-a").count(),
            completion_count,
        )

        duplicate_submit = self.client.post(
            f"/adaptive/practice/{attempt_id}/submit",
            json={"learner_answer": "a different answer"},
        )
        self.assertEqual(duplicate_submit.status_code, 200)
        self.assertEqual(duplicate_submit.json()["learner_status"], "already_completed")
        self.assertEqual(self.db.query(ReviewHistory).count(), 1)
        self.assertEqual(self.db.query(LearnerSkillState).one().accepted_evidence_count, 1)

    def test_chat_evidence_cannot_directly_mutate_mastery(self):
        source = self._chat_event()
        attempt = create_practice_attempt(
            self.db,
            verified_uid="learner-a",
            skill_id=source.skill_id,
            exercise_type="forged",
            assessment_event_id=source.id,
            outcome="incorrect",
            support_level="independent",
            independent_recall=True,
            source_event_key="forged-chat-attempt",
        )
        with self.assertRaisesRegex(ValueError, "chat evidence"):
            process_accepted_evidence(self.db, verified_uid="learner-a", event_id=source.id, practice_attempt_id=attempt.id)
        self.assertIsNone(self.db.query(LearnerSkillState).first())
        self.assertIsNone(self.db.query(ReviewHistory).first())

    def test_recommendation_filters_rejected_intent_and_unsafe_skill_classes(self):
        self._chat_event(skill_id="grammar.present-tense-querer", status="rejected")
        self._chat_event(skill_id="pronunciation.silent-h", modality="text")
        self._chat_event(skill_id="communication.cafe-ordering")
        self._chat_event(skill_id="vocabulary.dining-basics")
        self._chat_event(skill_id="grammar.present-tense-tener", result="correct")
        self.assertIsNone(get_targeted_practice_recommendation(self.db, verified_uid="learner-a"))

    def test_foreign_source_and_attempt_are_not_usable(self):
        source = self._chat_event(user="learner-b")
        with self.assertRaisesRegex(ValueError, "not found"):
            start_targeted_practice(self.db, verified_uid="learner-a", source_event_id=source.id)
        self.assertFalse(self.client.get("/adaptive/practice/recommendation").json()["available"])

        own_source = self._chat_event()
        attempt = start_targeted_practice(self.db, verified_uid="learner-a", source_event_id=own_source.id)
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "not found"):
            assess_targeted_practice_submission(self.db, verified_uid="learner-b", attempt_id=attempt.id, learner_answer="Yo quiero un café")

    def test_source_link_is_database_unique_but_historical_null_links_remain_valid(self):
        historical_one = create_practice_attempt(
            self.db, verified_uid="learner-a", skill_id="grammar.present-tense-querer",
            exercise_type="historical", source_event_key="historical-one",
        )
        historical_two = create_practice_attempt(
            self.db, verified_uid="learner-a", skill_id="grammar.present-tense-querer",
            exercise_type="historical", source_event_key="historical-two",
        )
        self.db.commit()
        self.assertIsNone(historical_one.source_assessment_event_id)
        self.assertIsNone(historical_two.source_assessment_event_id)

        source = self._chat_event()
        winner = start_targeted_practice(self.db, verified_uid="learner-a", source_event_id=source.id)
        self.db.commit()
        with self.assertRaises(IntegrityError):
            create_practice_attempt(
                self.db, verified_uid="learner-a", skill_id=source.skill_id,
                exercise_type="duplicate", source_assessment_event_id=source.id,
                source_event_key="duplicate-source-link",
            )
        self.db.rollback()
        self.assertEqual(self.db.query(PracticeAttempt).filter_by(source_assessment_event_id=source.id).one().id, winner.id)

    def test_client_cannot_replace_server_skill_and_mismatch_does_not_mutate(self):
        source = self._chat_event()
        response = self.client.post(
            "/adaptive/practice/start",
            json={"source_event_id": source.id, "skill_id": "grammar.present-tense-tener"},
        )
        self.assertEqual(response.status_code, 422)
        attempt = start_targeted_practice(self.db, verified_uid="learner-a", source_event_id=source.id)
        with patch("app.services.ai.propose_assessment", return_value=(self._proposal(skill_id="grammar.present-tense-tener", evidence="Tengo un boleto"), "mock")):
            result = assess_targeted_practice_submission(
                self.db, verified_uid="learner-a", attempt_id=attempt.id, learner_answer="Tengo un boleto"
            )
        self.assertEqual(result.event.validation_status, "rejected")
        self.assertEqual(result.event.rejection_reason, "targeted_practice_skill_mismatch")
        self.assertIsNone(self.db.query(LearnerSkillState).first())
        self.assertIsNone(self.db.query(ReviewHistory).first())

    def test_invalid_and_provider_failure_practice_responses_do_not_mutate(self):
        for index, patcher in enumerate((
            patch("app.services.ai.propose_assessment", return_value=(self._proposal(evidence="invented answer"), "mock")),
            patch("app.services.ai.propose_assessment", side_effect=RuntimeError("model unavailable")),
        )):
            with self.subTest(index=index):
                source = self._chat_event(result="partial")
                attempt = start_targeted_practice(self.db, verified_uid="learner-a", source_event_id=source.id)
                with patcher:
                    result = assess_targeted_practice_submission(
                        self.db, verified_uid="learner-a", attempt_id=attempt.id, learner_answer="Yo quiero un café"
                    )
                self.assertEqual(result.event.validation_status, "invalid")
                self.assertIsNone(self.db.query(LearnerSkillState).first())
                self.assertEqual(self.db.query(ReviewHistory).count(), 0)
                self.db.rollback()


if __name__ == "__main__":
    unittest.main()
