from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schemas import CaseValidationError, GoldenCase, Phase5Case, Phase7Case


EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = EVALS_DIR / "golden_cases.jsonl"
PHASE5_CASES_PATH = EVALS_DIR / "phase5_cases.jsonl"
PHASE7_CASES_PATH = EVALS_DIR / "phase7_cases.jsonl"


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
