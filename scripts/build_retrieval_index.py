"""Explicit local/real embedding index build; API and Worker never build on query."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ragcommerce_api.retrieval_config import configured_retrieval


async def main() -> None:
    index = configured_retrieval(Path(__file__).resolve().parents[1] / "data/demo/catalog.v3.jsonl")
    if index is None:
        raise RuntimeError("index build requires explicit RETRIEVAL_MODE=local or real")
    target = await index.build_index()
    print(f"indexed documents={len(index.documents)} alias={index.collection} collection={target}")


if __name__ == "__main__":
    asyncio.run(main())
