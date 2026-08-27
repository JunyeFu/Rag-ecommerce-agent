# ADR 0004: Domain identity, money, quote time, and Agent evidence

- Status: accepted
- Date: 2026-08-26

## Decision

`Product` is a normalized concept, `ProductVariant` is the comparable SKU,
`Offer` is a merchant sales entry, and `OfferQuote` is an immutable observation.
Their identifiers are never interchangeable. Amounts use signed 64-bit minor
units with an explicit ISO currency; V2 initially permits CNY and never accepts
binary floating point at a domain boundary.

All persisted times are timezone-aware UTC. Authorized live quotes are fresh
for at most five minutes unless a later connector contract introduces a more
restrictive TTL. Discovery-only offers have no amount and never participate in
price ordering. Quote history is append-only.

Agent runs store model, prompt, policy, and contract versions plus an
idempotency key. Steps, tool invocations, and evidence references retain stable
links without storing hidden reasoning or raw credential-bearing payloads.

## Consequences

PostgreSQL tables use explicit foreign keys, uniqueness, check constraints, and
`ON DELETE` rules. Public JSON Schema mirrors domain vocabulary but is not a
serialization of internal tables. Platform order, payment, refund, shipment,
and address records remain intentionally absent.
