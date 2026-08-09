"""Stable integrity findings and priority handling for D-05."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.graph_artifact import (
    GraphIntegrityCounts,
    GraphIntegrityFinding,
    GraphIntegrityReport,
    GraphIntegrityStage,
    GraphIntegrityStatus,
    GraphRejectionReason,
    compute_graph_integrity_report_hash,
)


_PRIORITY = {
    GraphIntegrityStage.input_schema: 100,
    GraphIntegrityStage.artifact_version: 200,
    GraphIntegrityStage.ownership: 300,
    GraphIntegrityStage.taxonomy: 400,
    GraphIntegrityStage.identity: 500,
    GraphIntegrityStage.endpoint: 600,
    GraphIntegrityStage.evidence_snapshot: 700,
    GraphIntegrityStage.relation_trace: 800,
    GraphIntegrityStage.direction_type: 900,
    GraphIntegrityStage.capacity_progressive: 1000,
    GraphIntegrityStage.hash_commitment: 1100,
}


@dataclass(frozen=True, slots=True)
class GraphAdmissionFailure(ValueError):
    """One stable D-05 integrity failure before candidate sealing."""

    stage: GraphIntegrityStage
    reason: GraphRejectionReason
    path: str
    message: str

    def __str__(self) -> str:
        return self.message


def finding_from_failure(failure: GraphAdmissionFailure) -> GraphIntegrityFinding:
    return GraphIntegrityFinding(
        stage=failure.stage,
        reason=failure.reason,
        priority=_PRIORITY[failure.stage],
        path=failure.path,
        message=failure.message,
    )


def build_integrity_report(
    *,
    findings: tuple[GraphIntegrityFinding, ...],
    counts: GraphIntegrityCounts,
) -> GraphIntegrityReport:
    by_key: dict[tuple[int, str, str, str], GraphIntegrityFinding] = {}
    for finding in findings:
        key = (
            finding.priority,
            finding.stage.value,
            finding.path,
            finding.reason.value,
        )
        existing = by_key.get(key)
        if existing is None or finding.message < existing.message:
            by_key[key] = finding
    ordered = tuple(by_key[key] for key in sorted(by_key))
    status = (
        GraphIntegrityStatus.failed if ordered else GraphIntegrityStatus.passed
    )
    payload = {
        "policy_version": "1.0.0",
        "status": status,
        "findings": ordered,
        "first_failure_stage": ordered[0].stage if ordered else None,
        "first_rejection_reason": ordered[0].reason if ordered else None,
        "counts": counts,
    }
    return GraphIntegrityReport(
        **payload,
        content_hash=compute_graph_integrity_report_hash(payload),
    )


def failed_integrity_report(
    failure: GraphAdmissionFailure | tuple[GraphAdmissionFailure, ...],
    *,
    counts: GraphIntegrityCounts,
) -> GraphIntegrityReport:
    failures = (failure,) if isinstance(failure, GraphAdmissionFailure) else failure
    return build_integrity_report(
        findings=tuple(finding_from_failure(item) for item in failures),
        counts=counts,
    )


__all__ = [
    "GraphAdmissionFailure",
    "build_integrity_report",
    "failed_integrity_report",
    "finding_from_failure",
]
