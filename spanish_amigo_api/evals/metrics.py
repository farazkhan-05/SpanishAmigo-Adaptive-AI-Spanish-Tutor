from __future__ import annotations
import random
from collections.abc import Sequence


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant_ids:
        return 0.0
    return len(set(retrieved_ids[:k]) & relevant_ids) / len(relevant_ids)


def hit_rate_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Returns 1.0 if at least one relevant ID is present in top-k retrieved results, else 0.0."""
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant_ids:
        return 0.0
    return 1.0 if bool(set(retrieved_ids[:k]) & relevant_ids) else 0.0



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


def paired_bootstrap_ci(
    scores_a: list[float],
    scores_b: list[float],
    num_resamples: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> dict[str, float | bool | int]:
    """Lightweight paired bootstrap confidence interval for difference in metric scores (b - a).

    Returns observed mean delta and lower/upper percentile bounds.
    Distinguishes credible improvement from small noisy metric movement without large dependencies.
    """
    if len(scores_a) != len(scores_b):
        raise ValueError("scores_a and scores_b must have equal length")
    if not scores_a or num_resamples <= 0:
        return {"mean_delta": 0.0, "ci_lower": 0.0, "ci_upper": 0.0, "significant": False, "resamples": 0}

    deltas = [b - a for a, b in zip(scores_a, scores_b)]
    n = len(deltas)
    observed_mean = sum(deltas) / n

    rng = random.Random(seed)
    boot_means: list[float] = []
    for _ in range(num_resamples):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)

    boot_means.sort()
    alpha = 1.0 - confidence_level
    lower_idx = max(0, int((alpha / 2.0) * num_resamples))
    upper_idx = min(num_resamples - 1, int((1.0 - alpha / 2.0) * num_resamples) - 1)

    ci_lower = boot_means[lower_idx]
    ci_upper = boot_means[upper_idx]
    # Statistically significant if 0 is outside the confidence interval
    significant = bool(ci_lower > 0.0 or ci_upper < 0.0)

    return {
        "mean_delta": round(observed_mean, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "confidence_level": confidence_level,
        "resamples": num_resamples,
        "significant": significant,
    }
