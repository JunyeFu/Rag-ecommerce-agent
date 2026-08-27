"""Reference policy runner used only to validate the deterministic evaluation harness."""

from __future__ import annotations

from .model import EvalCase, EvalResult


def reference_result(case: EvalCase) -> EvalResult:
    """Construct a contract-perfect fixture result; this is not a model-quality score."""
    tools = case.expected.allowed_tools[:1]
    evidence_refs = tuple(
        f"synthetic:{case.case_id}:evidence:{index + 1}"
        for index in range(case.expected.minimum_evidence_refs)
    )
    commercial: tuple[dict[str, object], ...] = ()
    if case.expected.commercial_facts_allowed and evidence_refs:
        commercial = (
            {
                "source_ref": evidence_refs[0],
                "verification": "FEED_VERIFIED",
                "collected_at": "2026-08-26T09:00:00Z",
                "expires_at": "2026-08-26T09:05:00Z",
            },
        )
    return EvalResult(
        case_id=case.case_id,
        outcome=case.expected.outcome,
        tool_calls=tools,
        evidence_refs=evidence_refs,
        commercial_facts=commercial,
        approval_requested=case.expected.requires_approval,
        deep_links=(),
        exposed_sensitive_fields=(),
        latency_ms=25 + len(case.turns) * 5,
        estimated_cost_microunits=0,
    )
