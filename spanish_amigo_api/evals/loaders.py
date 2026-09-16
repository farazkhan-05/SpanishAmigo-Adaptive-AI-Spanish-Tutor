from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schemas import CaseValidationError, GoldenCase, Phase5Case, Phase7Case, RetrievalBenchmarkCase


EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = EVALS_DIR / "golden_cases.jsonl"
PHASE5_CASES_PATH = EVALS_DIR / "phase5_cases.jsonl"
PHASE7_CASES_PATH = EVALS_DIR / "phase7_cases.jsonl"
RETRIEVAL_BENCHMARK_PATH = EVALS_DIR / "retrieval_benchmark.jsonl"


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise CaseValidationError("case must be a JSON object")
            case = GoldenCase.from_dict(raw)
        except (json.JSONDecodeError, CaseValidationError) as error:
            raise CaseValidationError(f"{path}:{line_number}: {error}") from error
        if case.id in seen:
            raise CaseValidationError(f"{path}:{line_number}: duplicate case id '{case.id}'")
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise CaseValidationError(f"{path}: no cases found")
    return cases


def dataset_sha256(path: Path = DEFAULT_CASES_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_phase5_cases(path: Path = PHASE5_CASES_PATH) -> list[Phase5Case]:
    cases: list[Phase5Case] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise CaseValidationError("case must be a JSON object")
            case = Phase5Case.from_dict(raw)
        except (json.JSONDecodeError, CaseValidationError) as error:
            raise CaseValidationError(f"{path}:{line_number}: {error}") from error
        if case.id in seen:
            raise CaseValidationError(f"{path}:{line_number}: duplicate case id '{case.id}'")
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise CaseValidationError(f"{path}: no cases found")
    return cases


def load_phase7_cases(path: Path = PHASE7_CASES_PATH) -> list[Phase7Case]:
    cases: list[Phase7Case] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise CaseValidationError("case must be a JSON object")
            case = Phase7Case.from_dict(raw)
        except (json.JSONDecodeError, CaseValidationError) as error:
            raise CaseValidationError(f"{path}:{line_number}: {error}") from error
        if case.id in seen:
            raise CaseValidationError(f"{path}:{line_number}: duplicate case id '{case.id}'")
        seen.add(case.id); cases.append(case)
    if not cases:
        raise CaseValidationError(f"{path}: no cases found")
    return cases


def load_retrieval_cases(path: Path = RETRIEVAL_BENCHMARK_PATH) -> list[RetrievalBenchmarkCase]:
    cases: list[RetrievalBenchmarkCase] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise CaseValidationError("case must be a JSON object")
            case = RetrievalBenchmarkCase.from_dict(raw)
        except (json.JSONDecodeError, CaseValidationError) as error:
            raise CaseValidationError(f"{path}:{line_number}: {error}") from error
        if case.id in seen:
            raise CaseValidationError(f"{path}:{line_number}: duplicate case id '{case.id}'")
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise CaseValidationError(f"{path}: no cases found")
    return cases


def validate_retrieval_cases_against_curriculum(
    cases: list[RetrievalBenchmarkCase],
    valid_slide_ids: set[str] | None = None,
    valid_skill_ids: set[str] | None = None,
) -> None:
    """Ensure every referenced slide ID and skill ID exists in authoritative curriculum metadata."""
    if valid_slide_ids is None:
        lessons_data_path = EVALS_DIR.parent.parent / "lessons_data.json"
        if lessons_data_path.exists():
            slides_data = json.loads(lessons_data_path.read_text(encoding="utf-8"))
            valid_slide_ids = {f"L{s['lesson_id']}-S{s['slide_index']}" for s in slides_data}
        else:
            from app.curriculum_metadata import SLIDE_SKILL_MAP
            valid_slide_ids = {f"L{lid}-S{sidx}" for lid, sidx in SLIDE_SKILL_MAP.keys()}

    if valid_skill_ids is None:
        from app.curriculum_metadata import SKILLS
        valid_skill_ids = {s.skill_id for s in SKILLS}

    for case in cases:
        for sid in case.expected_relevant_slide_ids:
            if sid not in valid_slide_ids:
                raise CaseValidationError(
                    f"case '{case.id}': expected slide '{sid}' does not exist in curriculum"
                )
        for skid in case.expected_relevant_skill_ids:
            if skid not in valid_skill_ids:
                raise CaseValidationError(
                    f"case '{case.id}': expected skill '{skid}' does not exist in curriculum taxonomy"
                )
