"""Load evidence-carrying catalog projections."""

import hashlib
import json
from pathlib import Path

from .search import EvidenceBundle, SearchDocument, TrustLevel


def load_demo_documents(path: Path) -> tuple[SearchDocument, ...]:
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    documents = []
    for line in content.decode("utf-8").splitlines():
        item = json.loads(line)
        documents.append(
            SearchDocument(
                seed_id=item["product_id"],
                title=item["title"],
                brand=item["brand"],
                category=item["category"],
                attributes={key: str(value) for key, value in item["attributes"].items()},
                scenarios=tuple(item["scenarios"]),
                evidence=EvidenceBundle(
                    "data/demo/catalog.v3.jsonl",
                    digest,
                    item["product_id"],
                    ("title", "brand", "category", "attributes", "scenarios", "fit_tags"),
                    TrustLevel.PROJECT_AUTHORED_DEMO,
                ),
                historical_price_minor=item["offer"]["price_minor"],
            )
        )
    return tuple(documents)


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
