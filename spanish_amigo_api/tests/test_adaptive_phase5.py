import os
import sys
import unittest

from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.schemas import AssessmentProposal
from app.services.adaptive import (
    DEVELOPING_MASTERY_MAX,
    LOW_MASTERY_MAX,
    MIN_ACCEPTANCE_CONFIDENCE,
    AssessabilityDecision,
    EvidenceValidation,
    PedagogicalAction,
    PolicyInput,
    UserIntent,
    assessability_gate,
    normalize_evidence,
    select_pedagogical_action,
    source_turn_key,
    validate_assessment_proposal,
)


def proposal(**overrides):
    values = {
        "assessable": True,
        "skill_id": "grammar.present-tense-querer",
        "result": "correct",
        "error_type": None,
        "severity": None,
        "confidence": 0.92,
        "evidence": "Yo quiero un caf\u00e9",
        "correction": None,
        "misconception_id": None,
        "assessment_version": "phase5-v1",
    }
    values.update(overrides)
    return AssessmentProposal.model_validate(values)


ASSESSABLE = AssessabilityDecision(True, UserIntent.PRODUCTION, "test")


class AssessmentSchemaTests(unittest.TestCase):
    def test_valid_proposal_is_strict_and_reasoning_free(self):
        self.assertEqual(proposal().result, "correct")
        with self.assertRaises(ValidationError):
            proposal(chain_of_thought="secret")

    def test_malformed_enum_confidence_and_missing_evidence_are_rejected(self):
        for values in (
            {"result": "mostly_correct"},
            {"confidence": 1.01},
            {"confidence": "0.9"},
            {"evidence": ""},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                proposal(**values)


class AssessabilityTests(unittest.TestCase):
    def test_expected_gate_cases(self):
        cases = [
            ("Yo quiero un caf\u00e9.", False, (), True),
            ("Explain ser vs estar", False, (), False),
            ("Hola", False, (), False),
            ("Translate 'I need help' into Spanish", False, (), False),
            ("dark mode", False, (), False),
            ("Write a Python script", True, (), False),
            ("Yo quiere... perd\u00f3n, yo quiero.", False, (), True),
            ("casa", False, ("Translate house into Spanish. Your turn",), True),
            ("x", False, (), False),
        ]
        for text, blocked, prior, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(assessability_gate(text, guardrail_blocked=blocked, prior_messages=prior).assessable, expected)

    def test_user_intent_is_preserved(self):
        self.assertEqual(assessability_gate("Why is estar used here?").intent, UserIntent.QUESTION)
        self.assertEqual(assessability_gate("toggle theme").intent, UserIntent.UI_COMMAND)


class EvidenceNormalizationAndValidationTests(unittest.TestCase):
    def test_normalization_is_conservative(self):
        self.assertEqual(normalize_evidence("  YO   QUIERO,  caf\u00e9! "), "yo quiero caf\u00e9")
        self.assertNotEqual(normalize_evidence("si"), normalize_evidence("s\u00ed"))
        self.assertNotEqual(normalize_evidence("quiero caf\u00e9"), normalize_evidence("no quiero caf\u00e9"))

    def test_exact_and_safe_normalized_evidence_are_accepted(self):
        exact = validate_assessment_proposal(proposal(), learner_turn="Yo quiero un caf\u00e9.", gate=ASSESSABLE)
        safe = validate_assessment_proposal(proposal(evidence="yo   quiero un caf\u00e9"), learner_turn="YO QUIERO UN CAF\u00c9!", gate=ASSESSABLE)
        self.assertEqual(exact.status, "accepted")
        self.assertEqual((exact.span_start, exact.span_end), (0, 17))
        self.assertEqual(safe.status, "accepted")

    def test_invented_or_accent_changed_evidence_is_invalid(self):
        invented = validate_assessment_proposal(proposal(evidence="Yo quiero agua"), learner_turn="Yo quiero un caf\u00e9", gate=ASSESSABLE)
        accent = validate_assessment_proposal(proposal(evidence="Yo quiero cafe"), learner_turn="Yo quiero caf\u00e9", gate=ASSESSABLE)
        negation = validate_assessment_proposal(proposal(evidence="Yo quiero caf\u00e9"), learner_turn="Yo no quiero caf\u00e9", gate=ASSESSABLE)
        lexical_substring = validate_assessment_proposal(proposal(evidence="no"), learner_turn="Estoy bueno", gate=ASSESSABLE)
        self.assertEqual(invented.status, "invalid")
        self.assertEqual(accent.status, "invalid")
        # A shorter affirmative is not contiguous after conservative normalization.
        self.assertEqual(negation.status, "invalid")
        self.assertEqual(lexical_substring.status, "invalid")

    def test_taxonomy_mode_domain_confidence_and_modality_rules(self):
        cases = [
            (proposal(skill_id="missing.skill"), "text", "invalid", "unknown_skill"),
            (proposal(skill_id="pronunciation.silent-h"), "text", "rejected", "speech_required_skill_from_text"),
            (proposal(skill_id="communication.cafe-ordering"), "text", "rejected", "contextual_skill_not_atomic"),
            (proposal(skill_id="vocabulary.dining-basics"), "text", "rejected", "broad_vocabulary_domain_overclaim"),
            (proposal(confidence=MIN_ACCEPTANCE_CONFIDENCE - 0.01), "text", "low_confidence", "below_acceptance_threshold"),
            (proposal(), "speech", "invalid", "unsupported_evidence_modality"),
            (proposal(result="unknown"), "text", "ambiguous", "non_concrete_result"),
        ]
        for item, modality, status, reason in cases:
            with self.subTest(status=status, reason=reason):
                observed = validate_assessment_proposal(item, learner_turn="Yo quiero un caf\u00e9", gate=ASSESSABLE, evidence_modality=modality)
                self.assertEqual((observed.status, observed.reason), (status, reason))

    def test_gate_and_model_must_both_say_assessable(self):
        blocked_gate = AssessabilityDecision(False, UserIntent.GREETING, "greeting")
        self.assertEqual(validate_assessment_proposal(proposal(), learner_turn="Yo quiero un caf\u00e9", gate=blocked_gate).status, "rejected")
        self.assertEqual(validate_assessment_proposal(proposal(assessable=False), learner_turn="Yo quiero un caf\u00e9", gate=ASSESSABLE).status, "rejected")


class DeterministicPolicyTests(unittest.TestCase):
    def _input(self, *, validation_status="accepted", result="incorrect", mastery=None, intent=UserIntent.PRODUCTION, assessable=True, mode="text"):
        validation = EvidenceValidation(validation_status, None, None, "evidence")
        return PolicyInput(AssessabilityDecision(assessable, intent, "test"), validation, result, mastery, 0, mode)

    def test_explicit_user_intent_precedes_interruption(self):
        self.assertEqual(select_pedagogical_action(self._input(intent=UserIntent.QUESTION)), PedagogicalAction.ANSWER_NORMALLY)
        self.assertEqual(select_pedagogical_action(self._input(intent=UserIntent.TRANSLATION_REQUEST)), PedagogicalAction.ANSWER_NORMALLY)

    def test_unknown_invalid_and_contextual_policy(self):
        self.assertEqual(select_pedagogical_action(self._input(result="correct", mastery=None)), PedagogicalAction.COLLECT_MORE_EVIDENCE)
        self.assertEqual(select_pedagogical_action(self._input(validation_status="invalid")), PedagogicalAction.COLLECT_MORE_EVIDENCE)
        self.assertEqual(select_pedagogical_action(self._input(mode="contextual")), PedagogicalAction.CONTEXTUAL_TRANSFER)
        self.assertEqual(select_pedagogical_action(self._input(assessable=False)), PedagogicalAction.NO_ADAPTIVE_ACTION)

    def test_numeric_boundaries_are_explicit(self):
        self.assertEqual(select_pedagogical_action(self._input(mastery=LOW_MASTERY_MAX)), PedagogicalAction.TARGETED_PRACTICE_WITH_HINT)
        self.assertEqual(select_pedagogical_action(self._input(mastery=LOW_MASTERY_MAX + 0.001)), PedagogicalAction.EXPLAIN_AND_GUIDE)
        self.assertEqual(select_pedagogical_action(self._input(result="correct", mastery=DEVELOPING_MASTERY_MAX)), PedagogicalAction.TARGETED_PRACTICE)
        self.assertEqual(select_pedagogical_action(self._input(result="correct", mastery=DEVELOPING_MASTERY_MAX + 0.001)), PedagogicalAction.ANSWER_NORMALLY)

    def test_source_turn_key_is_stable_and_context_sensitive(self):
        first = source_turn_key(1, ["prompt", "Yo quiero caf\u00e9"])
        self.assertEqual(first, source_turn_key(1, ["prompt", "Yo quiero caf\u00e9"]))
        self.assertNotEqual(first, source_turn_key(2, ["prompt", "Yo quiero caf\u00e9"]))
        self.assertNotEqual(first, source_turn_key(1, ["different", "Yo quiero caf\u00e9"]))

    def test_send_and_stream_share_the_authoritative_planner(self):
        from app.routers import chat
        from app.services import ai

        self.assertIs(chat.plan_turn, ai.plan_turn)
        self.assertIn("plan_turn", ai.tutor_graph.nodes)


if __name__ == "__main__":
    unittest.main()
