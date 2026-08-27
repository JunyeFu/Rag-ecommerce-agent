"""Identifier-first entity resolution with conflict review."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class EntityDecision(StrEnum):
    MATCH = "MATCH"
    REVIEW = "REVIEW"
    DISTINCT = "DISTINCT"


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    seed_id: str
    gtin: str | None
    mpn: str | None
    model: str | None
    attributes: Mapping[str, str]


class EntityResolver:
    def compare(
        self, left: EntityCandidate, right: EntityCandidate
    ) -> tuple[EntityDecision, float, tuple[str, ...]]:
        conflicts = tuple(
            sorted(
                key
                for key in set(left.attributes) & set(right.attributes)
                if left.attributes[key] != right.attributes[key]
            )
        )
        if left.gtin and right.gtin:
            return (
                (EntityDecision.DISTINCT, 0.0, ("gtin_conflict",))
                if left.gtin != right.gtin
                else (EntityDecision.MATCH, 1.0, ())
            )
        if left.mpn and right.mpn:
            return (
                (EntityDecision.DISTINCT, 0.0, ("mpn_conflict",))
                if left.mpn != right.mpn
                else (
                    (EntityDecision.REVIEW, 0.7, conflicts)
                    if conflicts
                    else (EntityDecision.MATCH, 0.95, ())
                )
            )
        if left.model and right.model and left.model.casefold() == right.model.casefold():
            return (EntityDecision.REVIEW, 0.6, conflicts or ("identifier_missing",))
        return EntityDecision.DISTINCT, 0.1, ("identifier_missing",)
