# ADR 0001: Monorepo module boundaries

- Status: accepted
- Date: 2026-08-26

## Decision

Use one repository with deployable applications in `apps/`, reusable deep
modules in `packages/`, local service definitions in `infra/`, versioned public
contracts in `packages/contracts/`, and reproducible evaluations in `evals/`.

The domain package owns invariants and does not import frameworks. API and
worker applications are composition roots. Connector, retrieval, Agent runtime,
and evaluation packages expose small public interfaces; infrastructure details
remain internal to those modules.

## Consequences

Cross-module changes require an explicit contract or task-package ownership
update. Applications may depend on packages; packages must not depend on an
application. This keeps later DATA, RAG, Agent, Android, and operations work
independently testable without creating a second monolith.
