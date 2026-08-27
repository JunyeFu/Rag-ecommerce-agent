"""Load development seed projections without turning seed price into a quote."""

import json
from pathlib import Path

from .search import EvidenceBundle, SearchDocument


def load_seed_documents(path: Path) -> tuple[SearchDocument, ...]:
    documents = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        provenance = item["provenance"]
        documents.append(
            SearchDocument(
                seed_id=item["seed_id"],
                title=item["canonical_name_candidate"],
                brand=item["brand_candidate"],
                category=item["category_candidate"],
                attributes=item["attributes"],
                scenarios=tuple(item["scenarios"]),
                evidence=EvidenceBundle(
                    provenance["source_path"],
                    provenance["source_sha256"],
                    item["seed_id"],
                    ("title", "brand", "category", "attributes", "scenarios"),
                ),
                historical_price_minor=item["historical_price"]["amount_minor"],
                untrusted_description=item["description_candidate"],
                highlights=tuple(item["highlights"]),
                development_rank_prior=(
                    item["development_rank_prior"]["rating_milli"],
                    item["development_rank_prior"]["rating_count"],
                ),
            )
        )
    return tuple(documents)
