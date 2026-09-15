from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schemas import CaseValidationError, GoldenCase


EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = EVALS_DIR / "golden_cases.jsonl"


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
