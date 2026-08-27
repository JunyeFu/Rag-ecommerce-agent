# ADR 0003: Contract-first deterministic clients

- Status: accepted
- Date: 2026-08-26

## Decision

`packages/contracts/openapi.json` and JSON Schemas are the public contract
sources. `scripts/generate_contracts.py` is a repository-owned generator with a
locked format version. Generated Python, Kotlin, and TypeScript files are
committed and CI executes the generator in check mode.

The bootstrap intentionally uses no remote code generator, which makes clean
checkout verification independent of a mutable hosted tool. A future generator
replacement requires an ADR and a reviewed migration diff.
