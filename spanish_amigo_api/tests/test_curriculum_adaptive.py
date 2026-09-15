import os
import sys
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.curriculum_metadata import SKILLS, SLIDE_SKILL_MAP, TAXONOMY_VERSION, metadata_for_slide, validate_taxonomy
from app.services.retrieval import RetrievedSlide, reciprocal_rank_fusion


class CurriculumAdaptiveTests(unittest.TestCase):
    def test_taxonomy_is_valid_and_stable(self):
        validate_taxonomy()
        self.assertEqual(len(SKILLS), len({s.skill_id for s in SKILLS}))
        self.assertTrue(all("." in skill.skill_id for skill in SKILLS))
        self.assertEqual(next(s for s in SKILLS if s.skill_id == "pronunciation.silent-h").assessment_mode, "speech_required")
        self.assertEqual(next(s for s in SKILLS if s.skill_id == "communication.cafe-ordering").assessment_mode, "contextual")
        self.assertTrue(all(not skill.prerequisites for skill in SKILLS))

    def test_mapping_supports_many_to_many_and_unmapped(self):
        self.assertGreater(len(SLIDE_SKILL_MAP[(1, 0)]), 1)
        self.assertEqual(metadata_for_slide(1, 50)[0], ())
        self.assertEqual(metadata_for_slide(999, 1)[0], ())

    def test_mapping_is_deterministic(self):
        self.assertEqual(metadata_for_slide(5, 10), metadata_for_slide(5, 10))
        self.assertEqual(TAXONOMY_VERSION, "spanishamigo-v1")

    def test_rrf_deduplicates_and_has_stable_ties(self):
        a = RetrievedSlide("L2-S1", 2, 1, "a", None, sources=("semantic",), rank=1, scores={"semantic": .1})
        b = RetrievedSlide("L1-S1", 1, 1, "b", None, sources=("lexical",), rank=1, scores={"lexical": .2})
        lexical_a = RetrievedSlide("L2-S1", 2, 1, "a", None, sources=("lexical",), rank=1, scores={"lexical": .1})
        fused = reciprocal_rank_fusion([a], [lexical_a, b], limit=3)
        self.assertEqual([item.slide_id for item in fused], ["L2-S1", "L1-S1"])
        self.assertEqual(fused[0].sources, ("semantic", "lexical"))

    def test_rrf_validates_limits(self):
        with self.assertRaises(ValueError): reciprocal_rank_fusion([], limit=0)


if __name__ == "__main__": unittest.main()
