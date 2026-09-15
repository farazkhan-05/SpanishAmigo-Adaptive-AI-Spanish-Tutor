import os
import sys
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import User, Skill, LearnerSkillState, AssessmentEvent, PracticeAttempt, ReviewHistory, ReviewItem, ChatSession, ChatMessage
from app.curriculum_metadata import SKILLS, TAXONOMY_VERSION
from app.services.adaptive import (fsrs_rating_for_event, create_assessment_event, create_practice_attempt,
    process_accepted_evidence, review_rationale, update_mastery, start_due_review, assess_review_submission)
from app.schemas import AssessmentProposal


class Phase6Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        for table in (User.__table__, ChatSession.__table__, ChatMessage.__table__, Skill.__table__, LearnerSkillState.__table__, AssessmentEvent.__table__, ReviewItem.__table__, PracticeAttempt.__table__, ReviewHistory.__table__):
            table.create(bind=self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add_all([User(id="a"), User(id="b")]); self.db.commit()
        self.db.add_all([Skill(skill_id=s.skill_id, display_label=s.display_label, description=s.description, category=s.category, cefr_level=s.cefr_level, difficulty=s.difficulty, learning_objective=s.learning_objective, assessment_mode=s.assessment_mode, taxonomy_version=TAXONOMY_VERSION) for s in SKILLS]); self.db.commit()

    def tearDown(self): self.db.close()

    def _event(self, user="a", result="correct", support="independent", independent=True, confidence=.9):
        event = create_assessment_event(self.db, verified_uid=user, skill_id="grammar.present-tense-tener", source_type="practice_attempt", evidence_snapshot="Tengo un boleto", proposed_result=result, validation_status="accepted", proposal_confidence=confidence, source_event_key=f"event-{user}-{result}-{support}-{self.db.query(ReviewHistory).count()}")
        attempt = create_practice_attempt(self.db, verified_uid=user, skill_id=event.skill_id, exercise_type="recall", assessment_event_id=event.id, outcome=result, support_level=support, independent_recall=independent, source_event_key=f"attempt-{event.id}")
        self.db.flush(); return event, attempt

    def _review(self, user="a", skill="grammar.present-tense-tener"):
        item = ReviewItem(id=f"review-{user}", user_id=user, skill_id=skill, card_state=1, card_step=None,
            stability=None, difficulty=None, due_at=datetime.now(UTC) - timedelta(minutes=1), last_review_at=None,
            fsrs_version="6.3.2", scheduler_version="test", created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
        self.db.add(item); self.db.commit(); return item

    def _proposal(self, **overrides):
        value = {"assessable": True, "skill_id": "grammar.present-tense-tener", "result": "correct", "error_type": None,
            "severity": None, "confidence": .95, "evidence": "Tengo un boleto", "correction": None,
            "misconception_id": None, "assessment_version": "phase5-v1"}
        value.update(overrides); return AssessmentProposal.model_validate(value)

    def test_first_accepted_evidence_creates_review_item_before_dependent_history_without_fk_violation(self):
        event, attempt = self._event(user="a", result="correct", support="independent", independent=True)
        # Ensure no pre-existing review item or history exists
        self.assertIsNone(self.db.query(ReviewItem).filter_by(user_id="a", skill_id=event.skill_id).first())
        self.assertEqual(self.db.query(ReviewHistory).filter_by(user_id="a").count(), 0)
        state = process_accepted_evidence(self.db, verified_uid="a", event_id=event.id, practice_attempt_id=attempt.id)
        self.assertIsNotNone(state.mastery_estimate)
        item = self.db.query(ReviewItem).filter_by(user_id="a", skill_id=event.skill_id).one()
        history = self.db.query(ReviewHistory).filter_by(user_id="a").one()
        self.assertEqual(history.review_item_id, item.id)
        self.assertEqual(history.assessment_event_id, event.id)

    def test_unknown_first_evidence_and_duplicate_are_safe(self):
        event, attempt = self._event()
        first = process_accepted_evidence(self.db, verified_uid="a", event_id=event.id, practice_attempt_id=attempt.id)
        second = process_accepted_evidence(self.db, verified_uid="a", event_id=event.id, practice_attempt_id=attempt.id)
        self.assertIsNotNone(first.mastery_estimate); self.assertGreater(first.mastery_estimate, .5)
        self.assertEqual(second.accepted_evidence_count, 1); self.assertEqual(self.db.query(ReviewHistory).count(), 1)

    def test_rating_mapping_and_bounds(self):
        self.assertEqual(fsrs_rating_for_event(result="incorrect", support_level="independent", independent_recall=True).value, 1)
        self.assertEqual(fsrs_rating_for_event(result="correct", support_level="hinted", independent_recall=False).value, 2)
        self.assertEqual(fsrs_rating_for_event(result="partial", support_level="independent", independent_recall=True).value, 2)
        self.assertEqual(fsrs_rating_for_event(result="correct", support_level="independent", independent_recall=True).value, 3)
        state = None
        for _ in range(30): state = update_mastery(previous=state.estimate if state else None, accepted_count=30, result="incorrect", support_level="independent", independent_recall=True, validation_confidence=.8)
        self.assertGreaterEqual(state.estimate, 0); self.assertLessEqual(state.confidence, .9)

    def test_rejects_non_atomic_and_other_user(self):
        event, attempt = self._event()
        with self.assertRaises(ValueError): process_accepted_evidence(self.db, verified_uid="b", event_id=event.id, practice_attempt_id=attempt.id)
        event.validation_status = "rejected"
        with self.assertRaises(ValueError): process_accepted_evidence(self.db, verified_uid="a", event_id=event.id, practice_attempt_id=attempt.id)

    def test_rationale_is_stored_fact_only(self):
        event, attempt = self._event(result="incorrect")
        process_accepted_evidence(self.db, verified_uid="a", event_id=event.id, practice_attempt_id=attempt.id)
        item = self.db.query(ReviewItem).one(); history = self.db.query(ReviewHistory).one()
        self.assertEqual(review_rationale(item, history, datetime.now(UTC) + timedelta(days=2)), "review is due")

    @patch("app.services.ai.propose_assessment")
    def test_review_start_submit_and_retry_are_end_to_end(self, propose):
        review = self._review(); attempt = start_due_review(self.db, verified_uid="a", review_id=review.id)
        self.assertIsNone(self.db.query(LearnerSkillState).first())
        propose.return_value = (self._proposal(), "mock")
        result = assess_review_submission(self.db, verified_uid="a", review_id=review.id, attempt_id=attempt.id, learner_answer="Tengo un boleto")
        retry = assess_review_submission(self.db, verified_uid="a", review_id=review.id, attempt_id=attempt.id, learner_answer="ignored")
        self.assertEqual(result.event.validation_status, "accepted"); self.assertEqual(retry.event.id, result.event.id)
        self.assertEqual(self.db.query(ReviewHistory).count(), 1); self.assertEqual(self.db.query(ReviewHistory).one().rating, 3)
        self.assertGreater(self.db.query(LearnerSkillState).one().mastery_estimate, .5)

    @patch("app.services.ai.propose_assessment")
    def test_review_rejected_low_confidence_does_not_mutate(self, propose):
        review = self._review(); attempt = start_due_review(self.db, verified_uid="a", review_id=review.id)
        propose.return_value = (self._proposal(confidence=.79), "mock")
        result = assess_review_submission(self.db, verified_uid="a", review_id=review.id, attempt_id=attempt.id, learner_answer="Tengo un boleto")
        self.assertEqual(result.event.validation_status, "low_confidence")
        self.assertIsNone(self.db.query(LearnerSkillState).first()); self.assertEqual(self.db.query(ReviewHistory).count(), 0)

    def test_review_start_and_attempt_are_tenant_scoped(self):
        review = self._review("b")
        with self.assertRaises(ValueError): start_due_review(self.db, verified_uid="a", review_id=review.id)

    @patch("app.services.ai.propose_assessment")
    def test_incorrect_review_is_again_and_reschedules(self, propose):
        review = self._review(); attempt = start_due_review(self.db, verified_uid="a", review_id=review.id)
        propose.return_value = (self._proposal(result="incorrect"), "mock")
        result = assess_review_submission(self.db, verified_uid="a", review_id=review.id, attempt_id=attempt.id, learner_answer="Tengo un boleto")
        self.assertEqual(result.event.validation_status, "accepted"); self.assertEqual(self.db.query(ReviewHistory).one().rating, 1)
        self.assertLess(self.db.query(LearnerSkillState).one().mastery_estimate, .5)

    @patch("app.services.ai.propose_assessment")
    def test_partial_independent_review_is_hard_and_completes(self, propose):
        review = self._review(); attempt = start_due_review(self.db, verified_uid="a", review_id=review.id)
        propose.return_value = (self._proposal(result="partial"), "mock")
        result = assess_review_submission(self.db, verified_uid="a", review_id=review.id, attempt_id=attempt.id, learner_answer="Tengo un boleto")
        self.assertEqual(result.event.validation_status, "accepted")
        self.assertEqual(self.db.query(ReviewHistory).one().rating, 2)
        self.assertIsNotNone(self.db.query(LearnerSkillState).one().mastery_estimate)

    @patch("app.services.ai.propose_assessment")
    def test_review_validator_protects_invalid_skill_classes(self, propose):
        for skill_id in ("communication.cafe-ordering", "pronunciation.silent-h", "vocabulary.dining-basics"):
            with self.subTest(skill_id=skill_id):
                review = self._review("a")
                attempt = start_due_review(self.db, verified_uid="a", review_id=review.id)
                propose.return_value = (self._proposal(skill_id=skill_id), "mock")
                result = assess_review_submission(self.db, verified_uid="a", review_id=review.id, attempt_id=attempt.id, learner_answer="Tengo un boleto")
                self.assertNotEqual(result.event.validation_status, "accepted")
                self.assertEqual(self.db.query(ReviewHistory).count(), 0)
                self.db.rollback(); self.db.query(ReviewItem).delete(); self.db.query(PracticeAttempt).delete(); self.db.query(AssessmentEvent).delete(); self.db.commit()


if __name__ == "__main__": unittest.main()
