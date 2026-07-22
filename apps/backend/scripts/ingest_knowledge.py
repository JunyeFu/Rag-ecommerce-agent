"""
知识库入库 — 文档 → chunk → 向量化 → PostgreSQL
用法: python scripts/ingest_knowledge.py
"""
import os, asyncio
from app.services.ingestion import ingest_document


async def main():
    docs_dir = "data/documents"
    total_chunks = 0
    for filename in os.listdir(docs_dir):
        if filename.endswith((".md", ".txt")):
            with open(os.path.join(docs_dir, filename), "r", encoding="utf-8") as f:
                text = f.read()
            chunks = await ingest_document(doc_id=filename, text=text)
            total_chunks += chunks
            print(f"Ingested {filename}: {chunks} chunks")
    print(f"Total: {total_chunks} chunks")


if __name__ == "__main__":
    asyncio.run(main())
