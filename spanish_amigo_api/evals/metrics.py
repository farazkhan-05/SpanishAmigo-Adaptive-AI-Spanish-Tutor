from __future__ import annotations


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
