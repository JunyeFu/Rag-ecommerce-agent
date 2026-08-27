# ADR 0002: Fact source and rebuildable projections

- Status: accepted
- Date: 2026-08-26

## Decision

PostgreSQL is the sole business fact source. Qdrant is a rebuildable retrieval
projection. Redis is limited to rate limits, short-lived cache, and background
coordination. Object storage contains lifecycle-managed media references.

Database-to-index propagation will use a transactional outbox. No request path
may claim success after writing only a projection, and no LLM output becomes a
price, inventory, merchant, logistics, or policy fact.

## Consequences

Projection loss is recovered by replay from PostgreSQL. DATA-01 and DOMAIN-01
must define stable identities before index or Agent work begins.
