"""Reproducible binary-relevance retrieval metrics."""

import math
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    recall_at_10: float
    ndcg_at_10: float
    hard_constraint_satisfaction: float
    cases: int


def recall(retrieved: Iterable[str], relevant: set[str]) -> float:
    return len(set(retrieved) & relevant) / len(relevant) if relevant else 1.0


def ndcg(retrieved: Iterable[str], relevant: set[str]) -> float:
    gains = [
        1.0 / math.log2(index + 2) for index, value in enumerate(retrieved) if value in relevant
    ]
    ideal = [1.0 / math.log2(index + 2) for index in range(min(10, len(relevant)))]
    return sum(gains) / sum(ideal) if ideal else 1.0
