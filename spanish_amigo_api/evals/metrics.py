from __future__ import annotations
from collections.abc import Sequence


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant_ids:
        return 0.0
    return len(set(retrieved_ids[:k]) & relevant_ids) / len(relevant_ids)


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    for position, identifier in enumerate(retrieved_ids, start=1):
        if identifier in relevant_ids:
            return 1.0 / position
    return 0.0


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def accuracy(expected: Sequence[object], observed: Sequence[object]) -> float | None:
    if len(expected) != len(observed):
        raise ValueError("expected and observed must have equal length")
    return mean([float(a == b) for a, b in zip(expected, observed)])


def binary_macro_f1(expected: list[bool], observed: list[bool]) -> float | None:
    if len(expected) != len(observed):
        raise ValueError("expected and observed must have equal length")
    if not expected:
        return None
    scores = []
    for label in (False, True):
        tp = sum(a == label and b == label for a, b in zip(expected, observed))
        fp = sum(a != label and b == label for a, b in zip(expected, observed))
        fn = sum(a == label and b != label for a, b in zip(expected, observed))
        denominator = 2 * tp + fp + fn
        scores.append((2 * tp / denominator) if denominator else 0.0)
    return sum(scores) / 2


def precision(expected: Sequence[bool], observed: Sequence[bool]) -> float | None:
    """Positive predictive value; None means there were no predicted positives."""
    predicted = sum(observed)
    return sum(a and b for a, b in zip(expected, observed)) / predicted if predicted else None


def recall(expected: Sequence[bool], observed: Sequence[bool]) -> float | None:
    """True-positive rate; None means the corpus has no positive labels."""
    positives = sum(expected)
    return sum(a and b for a, b in zip(expected, observed)) / positives if positives else None


def macro_f1(expected: Sequence[object], observed: Sequence[object]) -> float | None:
    if len(expected) != len(observed):
        raise ValueError("expected and observed must have equal length")
    labels = sorted(set(expected) | set(observed), key=str)
    if not labels:
        return None
    scores: list[float] = []
    for label in labels:
        tp = sum(a == label and b == label for a, b in zip(expected, observed))
        fp = sum(a != label and b == label for a, b in zip(expected, observed))
        fn = sum(a == label and b != label for a, b in zip(expected, observed))
        scores.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return mean(scores)
