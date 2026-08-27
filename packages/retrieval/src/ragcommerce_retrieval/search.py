"""Deterministic lexical baseline with structured constraints and provenance."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

TOKEN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> tuple[str, ...]:
    normalized = text.lower()
    units = TOKEN.findall(normalized)
    han = "".join(unit for unit in units if len(unit) == 1 and "\u4e00" <= unit <= "\u9fff")
    bigrams = [han[index : index + 2] for index in range(max(0, len(han) - 1))]
    return tuple(units + bigrams)


class TrustLevel(StrEnum):
    DEVELOPMENT_SEED_UNTRUSTED = "DEVELOPMENT_SEED_UNTRUSTED"
    UNTRUSTED_EXTERNAL_TEXT = "UNTRUSTED_EXTERNAL_TEXT"


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    source_path: str
    source_sha256: str
    seed_id: str
    fields: tuple[str, ...]
    trust: TrustLevel = TrustLevel.DEVELOPMENT_SEED_UNTRUSTED


@dataclass(frozen=True, slots=True)
class SearchDocument:
    seed_id: str
    title: str
    brand: str | None
    category: str | None
    attributes: Mapping[str, str]
    scenarios: tuple[str, ...]
    evidence: EvidenceBundle
    historical_price_minor: int | None = None
    untrusted_description: str = ""
    highlights: tuple[str, ...] = ()
    development_rank_prior: tuple[int, int] = (0, 0)

    @property
    def searchable_text(self) -> str:
        weighted = [
            self.title,
            self.title,
            self.category or "",
            self.category or "",
            self.brand or "",
        ]
        weighted.extend(f"{key} {value}" for key, value in sorted(self.attributes.items()))
        weighted.extend(self.scenarios)
        weighted.extend(self.highlights)
        return " ".join(weighted)


@dataclass(frozen=True, slots=True)
class SearchHit:
    document: SearchDocument
    score: float
    matched_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    seed_id: str
    cited_facts: Mapping[str, object]
    untrusted_content: str
    evidence: EvidenceBundle


def assemble_evidence(hits: Iterable[SearchHit]) -> tuple[RetrievedEvidence, ...]:
    return tuple(
        RetrievedEvidence(
            seed_id=hit.document.seed_id,
            cited_facts={
                "title": hit.document.title,
                "brand": hit.document.brand,
                "category": hit.document.category,
                "attributes": dict(hit.document.attributes),
            },
            untrusted_content=hit.document.untrusted_description,
            evidence=hit.document.evidence,
        )
        for hit in hits
    )


class HybridIndex:
    """Local BM25 baseline; production embeddings are an explicit later gate."""

    def __init__(self, documents: Iterable[SearchDocument]) -> None:
        self.documents = tuple(sorted(documents, key=lambda item: item.seed_id))
        self._tokens = {item.seed_id: tokenize(item.searchable_text) for item in self.documents}
        self._description_tokens = {
            item.seed_id: frozenset(tokenize(item.untrusted_description)) for item in self.documents
        }
        self._df: Counter[str] = Counter()
        for tokens in self._tokens.values():
            self._df.update(set(tokens))
        self._average_length = sum(map(len, self._tokens.values())) / max(1, len(self.documents))

    def search(
        self, query: str, limit: int = 10, constraints: Mapping[str, object] | None = None
    ) -> tuple[SearchHit, ...]:
        query_tokens = tokenize(query)
        constraints = {key.lower(): value for key, value in (constraints or {}).items()}
        hits: list[SearchHit] = []
        for document in self.documents:
            if not self._satisfies(document, constraints):
                continue
            frequencies = Counter(self._tokens[document.seed_id])
            score = sum(
                self._bm25(term, frequencies[term], len(self._tokens[document.seed_id]))
                for term in query_tokens
            )
            score += 0.15 * len(set(query_tokens) & self._description_tokens[document.seed_id])
            if document.category and document.category.lower() in query.lower():
                score += 8.0
            if document.brand and document.brand.lower() in query.lower():
                score += 6.0
            if constraints:
                score += (
                    document.development_rank_prior[0] * 1000 + document.development_rank_prior[1]
                )
            matched = tuple(sorted(set(query_tokens) & set(frequencies)))
            if score > 0 or constraints:
                hits.append(SearchHit(document, score, matched))
        hits.sort(key=lambda item: (-item.score, item.document.seed_id))
        return tuple(hits[:limit])

    def _bm25(self, term: str, frequency: int, length: int) -> float:
        if not frequency:
            return 0.0
        count = len(self.documents)
        inverse = math.log(1 + (count - self._df[term] + 0.5) / (self._df[term] + 0.5))
        denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * length / self._average_length)
        return inverse * frequency * 2.5 / denominator

    @staticmethod
    def _satisfies(document: SearchDocument, constraints: Mapping[str, object]) -> bool:
        for key, raw in constraints.items():
            if key == "category" and str(raw).lower() not in (document.category or "").lower():
                return False
            if key == "price_max" and (
                document.historical_price_minor is None
                or document.historical_price_minor > float(raw) * 100
            ):
                return False
            if (
                key == "brand_candidates"
                and raw
                and not any(
                    str(value).lower() in (document.brand or "").lower()
                    or str(value).lower() in document.title.lower()
                    for value in raw
                )
            ):
                return False
            if key == "exclude_brands" and any(
                str(value).lower() in (document.brand or "").lower()
                or str(value).lower() in document.title.lower()
                for value in raw
            ):
                return False
            if key == "exclude_terms" and any(
                str(value).lower() in document.searchable_text.lower() for value in raw
            ):
                return False
            if (
                key in document.attributes
                and str(raw).lower() not in document.attributes[key].lower()
            ):
                return False
        return True
