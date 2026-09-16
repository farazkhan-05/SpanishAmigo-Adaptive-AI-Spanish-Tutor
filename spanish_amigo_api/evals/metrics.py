from __future__ import annotations
import random
from collections.abc import Sequence
from typing import Any


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Recall@k computed exclusively over positive cases with non-empty relevant_ids."""
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant_ids:
        raise ValueError("recall_at_k is undefined for empty relevant_ids; use abstention metrics for negative cases")
    return len(set(retrieved_ids[:k]) & relevant_ids) / len(relevant_ids)


def hit_rate_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Hit Rate@k computed exclusively over positive cases with non-empty relevant_ids."""
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant_ids:
        raise ValueError("hit_rate_at_k is undefined for empty relevant_ids; use abstention metrics for negative cases")
    return 1.0 if bool(set(retrieved_ids[:k]) & relevant_ids) else 0.0


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """Reciprocal rank computed exclusively over positive cases with non-empty relevant_ids."""
    if not relevant_ids:
        raise ValueError("reciprocal_rank is undefined for empty relevant_ids; use abstention metrics for negative cases")
    for position, identifier in enumerate(retrieved_ids, start=1):
        if identifier in relevant_ids:
            return 1.0 / position
    return 0.0


def is_correct_abstention(retrieved_ids: list[str]) -> bool:
    """Returns True if zero slides were retrieved for an out-of-scope/negative query."""
    return len(retrieved_ids) == 0


def is_false_positive(retrieved_ids: list[str]) -> bool:
    """Returns True if one or more slides were incorrectly retrieved for an out-of-scope query."""
    return len(retrieved_ids) > 0


def abstention_accuracy(retrieved_per_case: Sequence[list[str]]) -> float:
    """Proportion of out-of-scope cases where the retriever correctly returned zero slides."""
    if not retrieved_per_case:
        return 0.0
    return sum(1.0 for r in retrieved_per_case if is_correct_abstention(r)) / len(retrieved_per_case)


def false_positive_rate(retrieved_per_case: Sequence[list[str]]) -> float:
    """Proportion of out-of-scope cases where the retriever incorrectly returned one or more slides."""
    if not retrieved_per_case:
        return 0.0
    return sum(1.0 for r in retrieved_per_case if is_false_positive(r)) / len(retrieved_per_case)


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
    Evaluates whether the bootstrap confidence interval excludes zero (statistically distinguishable from zero).
    Note: Computes percentile confidence bounds directly; does not compute an asymptotic p-value.
    """
    if len(scores_a) != len(scores_b):
        raise ValueError("scores_a and scores_b must have equal length")
    if not scores_a or num_resamples <= 0:
        return {
            "mean_delta": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "ci_excludes_zero": False,
            "significant": False,
            "resamples": 0,
        }

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
    # Distinguishable from zero if 0 is outside the percentile confidence interval
    ci_excludes_zero = bool(ci_lower > 0.0 or ci_upper < 0.0)

    return {
        "mean_delta": round(observed_mean, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "confidence_level": confidence_level,
        "resamples": num_resamples,
        "ci_excludes_zero": ci_excludes_zero,
        "significant": ci_excludes_zero,
    }


def percentile(values: Sequence[float], p: float) -> float | None:
    """Compute the p-th percentile (0 <= p <= 100) using linear interpolation."""
    if not values:
        return None
    if not (0.0 <= p <= 100.0):
        raise ValueError("percentile must be between 0 and 100")
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    idx = (p / 100.0) * (n - 1)
    lower = int(idx)
    upper = min(lower + 1, n - 1)
    weight = idx - lower
    return round((1.0 - weight) * sorted_vals[lower] + weight * sorted_vals[upper], 3)


def latency_summary(values: list[float]) -> dict[str, float | int | None]:
    """Summary of evaluation-run latency: count, mean, P50, P95 in milliseconds."""
    if not values:
        return {"count": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None}
    m = mean(values)
    return {
        "count": len(values),
        "mean_ms": round(m, 3) if m is not None else None,
        "p50_ms": percentile(values, 50.0),
        "p95_ms": percentile(values, 95.0),
    }


def token_summary(usages: Sequence[Any]) -> dict[str, int | float | None]:
    """Summary of genuine provider token usage. Returns None if provider supplied no tokens."""
    prompt_tokens: list[int] = []
    candidate_tokens: list[int] = []
    total_tokens: list[int] = []

    for u in usages:
        inp = getattr(u, "input_tokens", None)
        out = getattr(u, "output_tokens", None)
        tot = getattr(u, "total_tokens", None)
        if isinstance(inp, int):
            prompt_tokens.append(inp)
        if isinstance(out, int):
            candidate_tokens.append(out)
        if isinstance(tot, int):
            total_tokens.append(tot)

    if not total_tokens:
        return {
            "sample_count": len(usages),
            "measured_samples": 0,
            "prompt_tokens_total": None,
            "candidates_tokens_total": None,
            "total_tokens": None,
            "mean_total_tokens_per_case": None,
        }

    tot_sum = sum(total_tokens)
    return {
        "sample_count": len(usages),
        "measured_samples": len(total_tokens),
        "prompt_tokens_total": sum(prompt_tokens) if prompt_tokens else None,
        "candidates_tokens_total": sum(candidate_tokens) if candidate_tokens else None,
        "total_tokens": tot_sum,
        "mean_total_tokens_per_case": round(tot_sum / len(total_tokens), 2),
    }


def confusion_matrix(
    expected: Sequence[str],
    observed: Sequence[str],
    labels: Sequence[str] | None = None,
) -> dict[str, dict[str, int]]:
    """Multiclass confusion matrix {expected_label: {observed_label: count}}."""
    if len(expected) != len(observed):
        raise ValueError("expected and observed must have equal length")
    all_labels = sorted(set(labels or ()) | set(expected) | set(observed))
    matrix: dict[str, dict[str, int]] = {
        exp: {obs: 0 for obs in all_labels} for exp in all_labels
    }
    for exp, obs in zip(expected, observed):
        matrix[exp][obs] += 1
    return matrix


def score_distribution(scores: Sequence[float | int]) -> dict[str, Any]:
    """Compute count, mean, median, min, max for judge score dimensions."""
    if not scores:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    sorted_s = sorted(float(s) for s in scores)
    n = len(sorted_s)
    med = sorted_s[n // 2] if n % 2 != 0 else round((sorted_s[n // 2 - 1] + sorted_s[n // 2]) / 2.0, 2)
    return {
        "count": n,
        "mean": round(sum(sorted_s) / n, 3),
        "median": med,
        "min": sorted_s[0],
        "max": sorted_s[-1],
    }
