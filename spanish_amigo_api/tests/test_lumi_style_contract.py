# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, SystemStatus
from app.services.ai import (
    _TUTOR_SYSTEM_PROMPT,
    _OFF_TOPIC_REPLY,
    _ASSESSMENT_SYSTEM_PROMPT,
    prepare_tutor_messages,
)


class TestLumiStyleContract(unittest.TestCase):
    """Regression test suite validating the Lumi conversational style contract invariants."""

    def test_tutor_prompt_contains_proportionality_and_length_rules(self):
        prompt = _TUTOR_SYSTEM_PROMPT
        self.assertTrue("Match your response length to the user's turn" in prompt)
        self.assertTrue("Casual conversation & greetings" in prompt)
        self.assertTrue("Greetings safeguard" in prompt)
        self.assertTrue("Never prepend \"¡Hola!\", \"Hola\", or other greetings" in prompt)
        self.assertTrue("Valid Spanish statements" in prompt)
        self.assertTrue("Explicit length modifiers" in prompt)
        self.assertTrue("Answer only what was asked" in prompt)
        self.assertTrue("Corrections" in prompt)
        self.assertTrue("Normal explanations" in prompt)

    def test_tutor_prompt_prevents_customer_support_tone(self):
        prompt = _TUTOR_SYSTEM_PROMPT
        self.assertTrue("not a customer-support bot" in prompt)
        self.assertTrue("Do NOT turn casual conversation or greetings into a service interaction" in prompt)
        self.assertTrue("never ask \"How can I help you?\"" in prompt)

    def test_tutor_prompt_prevents_over_correction(self):
        prompt = _TUTOR_SYSTEM_PROMPT
        self.assertTrue("Correct only the learner's actual error" in prompt)
        self.assertTrue("Do not invent secondary errors" in prompt)
        self.assertTrue("Distinguish actual errors from optional stylistic preferences" in prompt)

    def test_tutor_prompt_bans_emojis_by_default(self):
        prompt = _TUTOR_SYSTEM_PROMPT
        self.assertTrue("No emojis by default" in prompt)
        self.assertTrue("Do not use decorative emojis" in prompt)

    def test_tutor_prompt_bans_bracket_translations(self):
        prompt = _TUTOR_SYSTEM_PROMPT
        self.assertTrue("No mechanical bracket translations" in prompt)
        self.assertTrue("Never write bracketed glosses" in prompt)

    def test_tutor_prompt_bans_decorative_markdown_and_forced_followups(self):
        prompt = _TUTOR_SYSTEM_PROMPT
        self.assertTrue("No decorative Markdown" in prompt)
        self.assertTrue("Do NOT end every response with a question" in prompt)

    def test_tutor_prompt_regulates_learner_context_usage(self):
        prompt = _TUTOR_SYSTEM_PROMPT
        self.assertTrue("Use this context silently" in prompt)
        self.assertTrue("Do NOT greet the learner by name on every turn" in prompt)
        self.assertTrue("mention past lessons" in prompt)

    def test_tutor_prompt_preserves_spanish_accuracy_and_ai_truthfulness(self):
        prompt = _TUTOR_SYSTEM_PROMPT
        self.assertTrue("Maintain correct Spanish spelling" in prompt)
        self.assertTrue("answer honestly that you are an AI tutor" in prompt)

    def test_assessment_prompt_is_isolated_and_unmodified(self):
        self.assertTrue("Return only the declared structured schema" in _ASSESSMENT_SYSTEM_PROMPT)
        self.assertTrue("Assess only actual learner production" in _ASSESSMENT_SYSTEM_PROMPT)
        self.assertFalse("No emojis by default" in _ASSESSMENT_SYSTEM_PROMPT)

    def test_off_topic_reply_is_clean(self):
        self.assertTrue("I can only help with Spanish language learning" in _OFF_TOPIC_REPLY)
        for char in _OFF_TOPIC_REPLY:
            self.assertLess(ord(char), 0x1F000, f"Emoji character found in off-topic reply: {char}")

    def test_prepare_tutor_messages_formats_cleanly(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine, tables=[SystemStatus.__table__])
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            state = {
                "messages": [HumanMessage(content="hola")],
                "user_id": "test-user-1",
                "user_name": "Test Learner",
                "completed_lessons_count": 3,
            }
            with patch("app.services.ai.genai.Client") as mock_client:
                mock_emb = MagicMock()
                mock_emb.embeddings = [MagicMock(values=[0.0] * 768)]
                mock_client.return_value.models.embed_content.return_value = mock_emb
                with patch("app.services.ai.legacy_semantic", return_value=[]):
                    messages = prepare_tutor_messages(state, db)
            self.assertIsInstance(messages[0], SystemMessage)
            sys_content = messages[0].content
            self.assertTrue("Test Learner" in sys_content)
            self.assertTrue("Completed lessons: 3" in sys_content)
            self.assertTrue("No emojis by default" in sys_content)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
