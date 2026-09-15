"""Versioned, human-curated curriculum taxonomy and slide mappings.

Mappings are intentionally static: no model call is made at seed time and an omitted
slide is an explicit unresolved mapping, not a guessed skill.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

TAXONOMY_VERSION = "spanishamigo-v1"
VALID_CEFR = {"A1", "A2", "B1", "B2", "C1", "C2", "UNKNOWN"}
VALID_CATEGORIES = {"vocabulary", "grammar", "communication", "pronunciation", "culture"}
VALID_ASSESSMENT_MODES = {"text", "speech_required", "contextual", "domain_tag"}


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    display_label: str
    description: str
    category: str
    cefr_level: str
    difficulty: int
    learning_objective: str
    prerequisites: tuple[str, ...] = ()
    assessment_mode: str = "text"


SKILLS = (
    SkillDefinition("pronunciation.silent-h", "Silent H", "Recognize that Spanish h is silent in taught words.", "pronunciation", "A1", 1, "Pronounce hola and hasta without an h sound.", assessment_mode="speech_required"),
    SkillDefinition("communication.greetings", "Greetings by time of day", "Select common greetings appropriate to time and register.", "communication", "A1", 1, "Greet someone with hola, buenos días, buenas tardes, or buenas noches."),
    SkillDefinition("grammar.gender-agreement", "Basic gender agreement", "Notice masculine and feminine agreement in taught greeting phrases.", "grammar", "A1", 2, "Choose buenos or buenas for the taught noun phrases."),
    SkillDefinition("communication.formal-informal-address", "Formal and informal address", "Use tú and usted forms in basic greetings.", "communication", "A1", 2, "Choose an appropriate how-are-you or and-you phrase for the relationship.", ("communication.greetings",)),
    SkillDefinition("communication.introductions-farewells", "Introductions and farewells", "Exchange names, pleasantries, and basic farewells.", "communication", "A1", 1, "Introduce yourself and close a short interaction politely.", ("communication.greetings",)),
    SkillDefinition("grammar.present-tense-querer", "Present tense of querer", "Use the taught forms of querer for wants and questions.", "grammar", "A1", 2, "Express wants, negation, and a basic want question."),
    SkillDefinition("grammar.present-tense-tener", "Present tense of tener", "Use the taught forms of tener for possession and need.", "grammar", "A1", 2, "Say what you have or need in the taught survival contexts."),
    SkillDefinition("vocabulary.survival-needs", "Survival needs vocabulary", "Recognize taught drink, transport, help, reservation, and ticket words.", "vocabulary", "A1", 1, "Request a basic item or service using the lesson vocabulary."),
    SkillDefinition("communication.politeness", "Polite service interaction", "Use please, thanks, and excuse-me expressions in a service setting.", "communication", "A1", 1, "Open and close a simple service interaction politely."),
    SkillDefinition("vocabulary.dining-basics", "Dining basics vocabulary", "Recognize taught food, drink, and bill vocabulary.", "vocabulary", "A1", 1, "Order or identify the taught restaurant items."),
    SkillDefinition("communication.asking-directions", "Asking for locations", "Ask where a taught place is.", "communication", "A1", 2, "Ask for a location using ¿Dónde está...?"),
    SkillDefinition("vocabulary.places-directions", "Places and directions vocabulary", "Recognize taught locations and directional words.", "vocabulary", "A1", 1, "Understand or give a basic location/direction using taught vocabulary."),
    SkillDefinition("communication.cafe-ordering", "Café ordering", "A guided café-scenario transfer tag; it is not an atomic mastery claim.", "communication", "A1", 3, "Practice integrating taught ordering components in a guided café exchange.", ("grammar.present-tense-querer", "communication.politeness", "vocabulary.dining-basics"), "contextual"),
    SkillDefinition("vocabulary.cafe-items", "Café items vocabulary", "Recognize taught menu, food, utensil, Wi-Fi, and tip vocabulary.", "vocabulary", "A1", 2, "Identify the taught café items needed in the simulation."),
)

# Course order and co-occurrence are not prerequisites. The current five lessons
# establish no material skill-to-skill dependency under the Phase-3 definition.
SKILLS = tuple(replace(skill, prerequisites=()) for skill in SKILLS)

# Slide ranges are reviewed against lessons_data.json. They deliberately map only
# coherent lesson segments; no CEFR claim beyond the evident A1 beginner material.
_RANGES: tuple[tuple[int, int, int, tuple[str, ...]], ...] = (
    (1, 0, 4, ("pronunciation.silent-h", "communication.greetings")), (1, 5, 15, ("communication.greetings", "grammar.gender-agreement")),
    (1, 16, 34, ("communication.formal-informal-address", "communication.greetings")), (1, 35, 45, ("communication.introductions-farewells", "pronunciation.silent-h")), (1, 46, 54, ()),
    (2, 0, 15, ("grammar.present-tense-querer", "vocabulary.survival-needs")), (2, 16, 30, ("grammar.present-tense-tener", "vocabulary.survival-needs")), (2, 31, 41, ("grammar.present-tense-querer", "grammar.present-tense-tener")),
    (3, 0, 12, ("communication.politeness",)), (3, 13, 26, ("vocabulary.dining-basics",)), (3, 27, 40, ("communication.politeness", "vocabulary.dining-basics")),
    (4, 0, 5, ("communication.asking-directions",)), (4, 6, 22, ("vocabulary.places-directions", "communication.asking-directions")), (4, 23, 42, ("vocabulary.places-directions",)),
    (5, 0, 8, ("communication.cafe-ordering",)), (5, 9, 32, ("vocabulary.cafe-items", "communication.cafe-ordering")), (5, 33, 49, ("communication.cafe-ordering", "communication.politeness")),
)

SLIDE_SKILL_MAP = {(lesson, index): skills for lesson, start, end, skills in _RANGES for index in range(start, end + 1)}


def validate_taxonomy() -> None:
    ids = [skill.skill_id for skill in SKILLS]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate stable skill ID")
    known = set(ids)
    edges: dict[str, tuple[str, ...]] = {skill.skill_id: skill.prerequisites for skill in SKILLS}
    for skill in SKILLS:
        if skill.category not in VALID_CATEGORIES or skill.cefr_level not in VALID_CEFR or skill.assessment_mode not in VALID_ASSESSMENT_MODES or not 1 <= skill.difficulty <= 5:
            raise ValueError(f"invalid skill metadata: {skill.skill_id}")
        if skill.skill_id in skill.prerequisites or len(skill.prerequisites) != len(set(skill.prerequisites)) or not set(skill.prerequisites) <= known:
            raise ValueError(f"invalid prerequisites: {skill.skill_id}")
    visiting, visited = set(), set()
    def visit(skill_id: str) -> None:
        if skill_id in visiting: raise ValueError("cyclic prerequisites")
        if skill_id not in visited:
            visiting.add(skill_id); [visit(parent) for parent in edges[skill_id]]; visiting.remove(skill_id); visited.add(skill_id)
    for skill_id in known: visit(skill_id)


def metadata_for_slide(lesson_id: int, slide_index: int) -> tuple[tuple[str, ...], str, int, str]:
    skill_ids = SLIDE_SKILL_MAP.get((lesson_id, slide_index), ())
    definitions = {skill.skill_id: skill for skill in SKILLS}
    if not skill_ids:
        return (), "UNKNOWN", 1, "Curriculum slide has no confident skill mapping."
    matched = [definitions[skill_id] for skill_id in skill_ids]
    return skill_ids, "A1" if all(s.cefr_level == "A1" for s in matched) else "UNKNOWN", max(s.difficulty for s in matched), " / ".join(s.learning_objective for s in matched)
