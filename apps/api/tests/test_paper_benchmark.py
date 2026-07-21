from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.paper_benchmark import (
    BenchmarkAdmissionStatus,
    BenchmarkEvaluationInput,
    BenchmarkMetricId,
    BenchmarkPackage,
    BenchmarkPackagePayload,
    BenchmarkReviewStatus,
    compute_benchmark_content_hash,
    compute_benchmark_scientific_payload_hash,
    evaluate_benchmark,
    load_benchmark_package,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_PATH = (
    REPOSITORY_ROOT
    / "services"
    / "paper_pipeline"
    / "benchmarks"
    / "exoplanet_host_star"
    / "paper-reasoning-benchmark.v1.json"
)


def _read_payload() -> dict[str, Any]:
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


def _review_record(
    payload: dict[str, Any],
    *,
    review_id: str,
    purpose: str = "pr_technical_review",
    verdict: str = "pass",
    sequence: int = 1,
    supersedes: str | None = None,
    reviewer_type: str = "web_gpt",
    reviewed_head_sha: str = "7a6abc1926f6f5891ad6f209eae8e91f11f7a5b6",
    reviewed_benchmark_version: str | None = None,
    reviewed_content_hash: str | None = None,
    scope: list[dict[str, Any]] | None = None,
    evidence_review_id: int | None = None,
) -> dict[str, Any]:
    return {
        "review_id": review_id,
        "review_sequence": sequence,
        "supersedes_review_id": supersedes,
        "reviewed_at": "2026-07-21T12:00:00+08:00",
        "reviewer_type": reviewer_type,
        "reviewer_identity": (
            "openai:web-gpt" if reviewer_type == "web_gpt" else "openai:codex"
        ),
        "reviewer_role": "pull_request_reviewer",
        "review_purpose": purpose,
        "verdict": verdict,
        "reviewed_head_sha": reviewed_head_sha,
        "reviewed_benchmark_version": (
            reviewed_benchmark_version or payload["benchmark_version"]
        ),
        "reviewed_content_hash": reviewed_content_hash
        or payload.get("scientific_payload_hash")
        or payload["content_hash"],
        "review_evidence_url": (
            "https://github.com/zyyyyynnn/xingwen-astro-ai/"
            f"pull/96#pullrequestreview-{evidence_review_id or sequence}"
        ),
        "scope": scope
        or [
            {
                "target_type": "benchmark_package",
                "target_ids": [payload["benchmark_id"]],
            }
        ],
        "blocking_findings": (
            ["Synthetic blocking finding."] if verdict == "blocked" else []
        ),
        "non_blocking_findings": (
            ["No blocking findings."] if verdict == "pass" else []
        ),
        "notes": "Synthetic review contract fixture.",
        "evidence_actor_identity": "github:zyyyyynnn",
        "review_evidence_state": "COMMENTED",
    }


def _full_review_scope(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "target_type": "benchmark_package",
            "target_ids": [payload["benchmark_id"]],
        },
        {
            "target_type": "source_policy",
            "target_ids": [item["source_id"] for item in payload["source_policies"]],
        },
        {
            "target_type": "seed_paper",
            "target_ids": [item["paper_id"] for item in payload["seed_papers"]],
        },
        {
            "target_type": "paper_summary",
            "target_ids": [item["summary_id"] for item in payload["paper_summaries"]],
        },
        {
            "target_type": "evidence",
            "target_ids": [item["evidence_id"] for item in payload["evidence"]],
        },
        {
            "target_type": "claim",
            "target_ids": [item["claim_id"] for item in payload["claims"]],
        },
        {
            "target_type": "relation",
            "target_ids": [item["relation_id"] for item in payload["relations"]],
        },
        {
            "target_type": "reasoning_trace",
            "target_ids": [item["trace_id"] for item in payload["reasoning_traces"]],
        },
        {
            "target_type": "graph_edge",
            "target_ids": [item["edge_id"] for item in payload["graph"]["edges"]],
        },
    ]


def _approved_payload(review_purpose: str) -> dict[str, Any]:
    from app.schemas.paper_benchmark import compute_benchmark_scientific_payload_hash

    payload = _read_payload()
    payload.pop("content_hash")
    payload["review_status"] = "approved"
    for collection in (
        payload["paper_summaries"],
        payload["evidence"],
        payload["claims"],
        payload["relations"],
        payload["reasoning_traces"],
    ):
        for item in collection:
            item["review_status"] = "approved"
    payload["scientific_payload_hash"] = compute_benchmark_scientific_payload_hash(
        payload
    )
    source = {**payload, "content_hash": payload["scientific_payload_hash"]}
    payload["review_records"] = [
        _review_record(
            source,
            review_id="review.scientific_pass",
            purpose=review_purpose,
            reviewed_content_hash=payload["scientific_payload_hash"],
            scope=_full_review_scope(payload),
        )
    ]
    return payload


def _review_fixture(
    *,
    package_status: BenchmarkReviewStatus,
    approved_relation_count: int,
) -> BenchmarkPackage:
    if package_status is BenchmarkReviewStatus.approved:
        assert approved_relation_count == len(_read_payload()["relations"])
        payload = _approved_payload("benchmark_scientific_review")
        payload["content_hash"] = compute_benchmark_content_hash(payload)
        return BenchmarkPackage.model_validate(payload)

    payload = _read_payload()
    payload["review_status"] = package_status.value
    for index, relation in enumerate(payload["relations"]):
        relation["review_status"] = (
            BenchmarkReviewStatus.approved.value
            if index < approved_relation_count
            else BenchmarkReviewStatus.pending_scientific_review.value
        )
        if relation["review_status"] != BenchmarkReviewStatus.approved.value:
            continue
        claim_ids = {relation["source_claim_id"], relation["target_claim_id"]}
        claims = [
            claim for claim in payload["claims"] if claim["claim_id"] in claim_ids
        ]
        for claim in claims:
            claim["review_status"] = BenchmarkReviewStatus.approved.value
        related_evidence_ids = {
            *relation["evidence_ids"],
            *(evidence_id for claim in claims for evidence_id in claim["evidence_ids"]),
        }
        if relation["reasoning_trace_id"] is not None:
            trace = next(
                trace
                for trace in payload["reasoning_traces"]
                if trace["trace_id"] == relation["reasoning_trace_id"]
            )
            trace["review_status"] = BenchmarkReviewStatus.approved.value
            related_evidence_ids.update(
                evidence_id
                for step in trace["steps"]
                for evidence_id in step["evidence_ids"]
            )
        for evidence in payload["evidence"]:
            if evidence["evidence_id"] in related_evidence_ids:
                evidence["review_status"] = BenchmarkReviewStatus.approved.value

    payload["scientific_payload_hash"] = compute_benchmark_scientific_payload_hash(
        payload
    )
    payload["content_hash"] = compute_benchmark_content_hash(payload)
    return BenchmarkPackage.model_validate(payload)


def _evaluation_input(**overrides: int) -> BenchmarkEvaluationInput:
    values = {
        "schema_items_valid": 0,
        "schema_items_total": 0,
        "evidence_requirements_satisfied": 0,
        "evidence_requirements_total": 0,
        "evidence_less_relations_blocked": 0,
        "evidence_less_relations_total": 0,
    }
    values.update(overrides)
    return BenchmarkEvaluationInput(**values)


def test_benchmark_package_is_machine_readable_and_versioned() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    assert package.benchmark_id == "exoplanet_host_star.paper_reasoning"
    assert package.schema_version == "1.2.0"
    assert package.benchmark_version == "1.2.0"
    assert package.case_id == "exoplanet_host_star"
    assert len(package.seed_papers) == 6
    assert len(package.claims) >= 5
    assert len(package.relations) >= 3
    assert package.review_status is BenchmarkReviewStatus.pending_scientific_review
    assert package.scientific_payload_hash == (
        "sha256:b979a27c0467061f254dec2343a7c205d8e38d861a5530c4249f3cd6d9455f83"
    )


def test_content_hash_uses_the_c01_canonical_rules() -> None:
    payload = _read_payload()
    package = BenchmarkPackage.model_validate(payload)

    assert compute_benchmark_content_hash(payload) == package.content_hash
    assert compute_benchmark_content_hash(package) == package.content_hash
    assert (
        compute_benchmark_content_hash(package.model_dump(mode="json"))
        == package.content_hash
    )


def test_hash_is_stable_after_json_round_trip() -> None:
    payload = _read_payload()
    round_tripped = json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=False))

    assert compute_benchmark_content_hash(round_tripped) == payload["content_hash"]


def test_hash_sorts_object_keys_but_preserves_array_order() -> None:
    payload = _read_payload()
    reordered_keys = {key: payload[key] for key in reversed(tuple(payload))}
    assert compute_benchmark_content_hash(reordered_keys) == payload["content_hash"]

    reordered_array = deepcopy(payload)
    reordered_array["seed_papers"].reverse()
    assert compute_benchmark_content_hash(reordered_array) != payload["content_hash"]


@pytest.mark.parametrize(
    "field",
    ["created_at", "review_records", "change_records"],
)
def test_audit_and_review_metadata_are_hash_bound(field: str) -> None:
    payload = _read_payload()
    if field == "created_at":
        payload[field] = "2026-07-20"
    elif field == "review_records":
        payload[field].append(
            _review_record(
                payload,
                review_id="review.hash_bound_metadata",
                verdict="blocked",
                reviewer_type="automation",
            )
        )
    else:
        payload[field][0]["summary"] += " changed"

    assert compute_benchmark_content_hash(payload) != _read_payload()["content_hash"]


def test_wrong_content_hash_is_rejected() -> None:
    payload = _read_payload()
    payload["content_hash"] = f"sha256:{'0' * 64}"

    with pytest.raises(ValidationError, match="content_hash does not match"):
        BenchmarkPackage.model_validate(payload)


@pytest.mark.parametrize("field", ["schema_version", "benchmark_version"])
def test_invalid_semantic_version_is_rejected(field: str) -> None:
    payload = _read_payload()
    payload[field] = "v1"

    with pytest.raises(ValidationError, match=field):
        BenchmarkPackage.model_validate(payload)


def test_seed_papers_have_verified_identifiers_and_data_boundaries() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    for paper in package.seed_papers:
        assert paper.doi or paper.arxiv_id or paper.official_url
        assert paper.verification_sources
        assert all(source.verified_at for source in paper.verification_sources)
        assert all(author.casefold().rstrip(".") != "et al" for author in paper.authors)
        assert paper.metadata_public is True
        assert paper.abstract_public is True
        assert paper.license_or_usage_boundary
        assert paper.rate_limit_or_runtime_risk
        assert set(paper.intended_uses) <= {"benchmark", "manual_review", "fixture"}


def test_verification_sources_use_revalidated_stable_records() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    for paper in package.seed_papers:
        for source in paper.verification_sources:
            assert source.verified_at.isoformat() == "2026-07-21"
            if source.source_id == "crossref":
                assert str(source.url).startswith("https://api.crossref.org/works/")

    clark = next(
        paper
        for paper in package.seed_papers
        if paper.paper_id == "paper.clark_2021_galah_tess"
    )
    assert {source.source_id for source in clark.verification_sources} == {
        "arxiv",
        "crossref",
    }


def test_crossref_policy_separates_documented_claims_and_observed_headers() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    crossref = next(
        source for source in package.source_policies if source.source_id == "crossref"
    )

    assert crossref.crossref_rate_limits is not None
    snapshot = crossref.crossref_rate_limits
    assert len(snapshot.documented_policy) >= 2
    assert all(policy.known_conflict_note for policy in snapshot.documented_policy)
    assert snapshot.runtime_uses_response_headers is True
    assert snapshot.handles_429_with_backoff is True
    assert snapshot.missing_headers_strategy == "conservative"
    assert {
        (
            observed.request_class,
            observed.x_api_pool,
            observed.x_rate_limit_limit,
            observed.x_rate_limit_interval,
            observed.x_concurrency_limit,
            observed.response_status,
        )
        for observed in snapshot.observed_runtime_limits
    } == {
        ("single_record", "public", 5, "1s", 1, 200),
        ("list_or_search", "public", 5, "1s", 1, 200),
    }


def test_crossref_observed_headers_can_be_explicitly_unavailable() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    crossref = next(
        source
        for source in payload["source_policies"]
        if source["source_id"] == "crossref"
    )
    observed = crossref["crossref_rate_limits"]["observed_runtime_limits"][0]
    observed["x_api_pool"] = "unavailable"
    observed["x_rate_limit_limit"] = "unavailable"
    observed["x_rate_limit_interval"] = "unavailable"
    observed["x_concurrency_limit"] = "unavailable"

    BenchmarkPackagePayload.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("documented_policy", 0, "limits", 0, "requests_per_interval"), 0),
        (("observed_runtime_limits", 0, "response_status"), 99),
        (("observed_runtime_limits", 0, "request_class"), "unknown"),
    ],
)
def test_crossref_limit_snapshot_enforces_boundaries(
    path: tuple[Any, ...], value: Any
) -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    crossref = next(
        source
        for source in payload["source_policies"]
        if source["source_id"] == "crossref"
    )
    target: Any = crossref["crossref_rate_limits"]
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        BenchmarkPackagePayload.model_validate(payload)


def test_automation_review_cannot_approve_package() -> None:
    payload = _approved_payload("benchmark_scientific_review")
    payload["review_records"] = [
        _review_record(
            {**payload, "content_hash": payload["scientific_payload_hash"]},
            review_id="review.automation_blocked",
            purpose="benchmark_scientific_review",
            verdict="blocked",
            reviewer_type="automation",
            reviewed_content_hash=payload["scientific_payload_hash"],
            scope=_full_review_scope(payload),
        )
    ]

    with pytest.raises(ValidationError, match="scientific Review PASS"):
        BenchmarkPackagePayload.model_validate(payload)


def test_web_gpt_review_requires_explicit_purpose_and_content_binding() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    payload["review_records"] = [
        _review_record(_read_payload(), review_id="review.web_gpt_technical_pass")
    ]

    BenchmarkPackagePayload.model_validate(payload)


def test_automation_cannot_issue_formal_pass() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    payload["review_records"] = [
        _review_record(
            _read_payload(),
            review_id="review.automation_pass",
            reviewer_type="automation",
        )
    ]

    with pytest.raises(ValidationError, match="automation cannot issue"):
        BenchmarkPackagePayload.model_validate(payload)


def test_later_blocked_review_is_the_effective_verdict() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    source = _read_payload()
    payload["review_records"] = [
        _review_record(source, review_id="review.pass"),
        _review_record(
            source,
            review_id="review.blocked",
            verdict="blocked",
            sequence=2,
            supersedes="review.pass",
        ),
    ]

    from app.schemas.paper_benchmark import BenchmarkPrReviewGate

    with pytest.raises(ValidationError, match="unresolved BLOCKED"):
        BenchmarkPrReviewGate.model_validate(
            {
                "current_head_sha": "7a6abc1926f6f5891ad6f209eae8e91f11f7a5b6",
                "current_benchmark_version": source["benchmark_version"],
                "current_scientific_payload_hash": source["scientific_payload_hash"],
                "review_records": payload["review_records"],
            }
        )


def test_later_pass_resolves_blocked_review() -> None:
    source = _read_payload()
    records = [
        _review_record(source, review_id="review.blocked", verdict="blocked"),
        _review_record(
            source,
            review_id="review.pass",
            sequence=2,
            supersedes="review.blocked",
        ),
    ]

    from app.schemas.paper_benchmark import BenchmarkPrReviewGate

    gate = BenchmarkPrReviewGate.model_validate(
        {
            "current_head_sha": "7a6abc1926f6f5891ad6f209eae8e91f11f7a5b6",
            "current_benchmark_version": source["benchmark_version"],
            "current_scientific_payload_hash": source["scientific_payload_hash"],
            "review_records": records,
        }
    )

    assert gate.review_records[-1].verdict.value == "pass"


@pytest.mark.parametrize(
    ("records", "expected_message"),
    [
        (
            lambda source: [
                _review_record(
                    source,
                    review_id="review.child",
                    sequence=2,
                    supersedes="review.missing",
                )
            ],
            "unknown supersedes_review_id",
        ),
        (
            lambda source: [
                _review_record(source, review_id="review.root"),
                _review_record(
                    source,
                    review_id="review.child_a",
                    sequence=2,
                    supersedes="review.root",
                ),
                _review_record(
                    source,
                    review_id="review.child_b",
                    sequence=2,
                    supersedes="review.root",
                    evidence_review_id=3,
                ),
            ],
            "more than one direct successor",
        ),
        (
            lambda source: [
                _review_record(
                    source,
                    review_id="review.a",
                    sequence=2,
                    supersedes="review.b",
                ),
                _review_record(
                    source,
                    review_id="review.b",
                    sequence=3,
                    supersedes="review.a",
                ),
            ],
            "supersedes cycle",
        ),
        (
            lambda source: [
                _review_record(source, review_id="review.root"),
                _review_record(
                    source,
                    review_id="review.child",
                    purpose="benchmark_scientific_review",
                    sequence=2,
                    supersedes="review.root",
                ),
            ],
            "review purpose",
        ),
        (
            lambda source: [
                _review_record(source, review_id="review.root"),
                _review_record(
                    source,
                    review_id="review.child",
                    sequence=2,
                    supersedes="review.root",
                    scope=[
                        {
                            "target_type": "source_policy",
                            "target_ids": ["crossref"],
                        }
                    ],
                ),
            ],
            "review scope",
        ),
    ],
)
def test_invalid_review_evolution_is_rejected(
    records: Any, expected_message: str
) -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    payload["review_records"] = records(_read_payload())

    with pytest.raises(ValidationError, match=expected_message):
        BenchmarkPackagePayload.model_validate(payload)


def test_new_review_cannot_reuse_superseded_evidence_url() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    source = _read_payload()
    root = _review_record(source, review_id="review.root", verdict="blocked")
    child = _review_record(
        source,
        review_id="review.child",
        sequence=2,
        supersedes="review.root",
    )
    child["review_evidence_url"] = root["review_evidence_url"]
    payload["review_records"] = [root, child]

    with pytest.raises(ValidationError, match="review evidence URL"):
        BenchmarkPackagePayload.model_validate(payload)


@pytest.mark.parametrize(
    ("override", "expected_message"),
    [
        ({"reviewed_head_sha": "0" * 40}, "current HEAD"),
        ({"reviewed_benchmark_version": "9.9.9"}, "benchmark version"),
        ({"reviewed_content_hash": f"sha256:{'0' * 64}"}, "content hash"),
        ({"purpose": "benchmark_scientific_review"}, "technical Review PASS"),
    ],
)
def test_pr_gate_rejects_stale_or_wrong_purpose_review(
    override: dict[str, str], expected_message: str
) -> None:
    source = _read_payload()
    record = _review_record(
        source,
        review_id="review.stale",
        **override,
    )

    from app.schemas.paper_benchmark import BenchmarkPrReviewGate

    with pytest.raises(ValidationError, match=expected_message):
        BenchmarkPrReviewGate.model_validate(
            {
                "current_head_sha": "7a6abc1926f6f5891ad6f209eae8e91f11f7a5b6",
                "current_benchmark_version": source["benchmark_version"],
                "current_scientific_payload_hash": source["scientific_payload_hash"],
                "review_records": [record],
            }
        )


def test_scientific_hash_excludes_review_metadata_but_detects_payload_tampering() -> (
    None
):
    from app.schemas.paper_benchmark import compute_benchmark_scientific_payload_hash

    payload = _read_payload()
    expected = compute_benchmark_scientific_payload_hash(payload)

    changed_review = deepcopy(payload)
    changed_review["review_records"] = [
        _review_record(
            payload,
            review_id="review.metadata_only",
            verdict="blocked",
            reviewer_type="automation",
        )
    ]
    assert compute_benchmark_scientific_payload_hash(changed_review) == expected

    changed_science = deepcopy(payload)
    changed_science["seed_papers"][0]["title"] += " tampered"
    assert compute_benchmark_scientific_payload_hash(changed_science) != expected


def test_technical_review_cannot_approve_scientific_benchmark() -> None:
    payload = _approved_payload("pr_technical_review")

    with pytest.raises(ValidationError, match="scientific Review PASS"):
        BenchmarkPackagePayload.model_validate(payload)


def test_complete_scientific_review_can_approve_benchmark() -> None:
    payload = _approved_payload("benchmark_scientific_review")

    package = BenchmarkPackagePayload.model_validate(payload)

    assert package.review_status.value == "approved"


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        ("reviewed_benchmark_version", "9.9.9", "benchmark version"),
        ("reviewed_content_hash", f"sha256:{'0' * 64}", "scientific payload hash"),
    ],
)
def test_scientific_review_must_bind_current_version_and_hash(
    field: str, value: str, expected_message: str
) -> None:
    payload = _approved_payload("benchmark_scientific_review")
    payload["review_records"][0][field] = value

    with pytest.raises(ValidationError, match=expected_message):
        BenchmarkPackagePayload.model_validate(payload)


def test_scientific_review_scope_must_cover_every_object() -> None:
    payload = _approved_payload("benchmark_scientific_review")
    graph_scope = next(
        scope
        for scope in payload["review_records"][0]["scope"]
        if scope["target_type"] == "graph_edge"
    )
    graph_scope["target_ids"].pop()

    with pytest.raises(ValidationError, match="scientific review scope is incomplete"):
        BenchmarkPackagePayload.model_validate(payload)


def test_unresolved_scientific_block_prevents_approval() -> None:
    payload = _approved_payload("benchmark_scientific_review")
    passed = payload["review_records"][0]
    payload["review_records"].append(
        _review_record(
            {**payload, "content_hash": payload["scientific_payload_hash"]},
            review_id="review.scientific_blocked",
            purpose="benchmark_scientific_review",
            verdict="blocked",
            sequence=2,
            supersedes=passed["review_id"],
            reviewed_content_hash=payload["scientific_payload_hash"],
            scope=passed["scope"],
        )
    )

    with pytest.raises(ValidationError, match="unresolved BLOCKED scientific"):
        BenchmarkPackagePayload.model_validate(payload)


def test_unsupported_reviewer_type_is_rejected() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    record = _review_record(_read_payload(), review_id="review.unsupported")
    record["reviewer_type"] = "person"
    payload["review_records"] = [record]

    with pytest.raises(ValidationError):
        BenchmarkPackagePayload.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("review_purpose", "unsupported_review"),
        ("reviewed_head_sha", "not-a-40-character-commit-sha"),
        ("evidence_actor_identity", "openai:web-gpt"),
        ("review_evidence_state", "UNKNOWN"),
    ],
)
def test_review_rejects_invalid_enum_identity_and_head_fields(
    field: str, value: str
) -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    record = _review_record(_read_payload(), review_id="review.invalid_contract")
    record[field] = value
    payload["review_records"] = [record]

    with pytest.raises(ValidationError):
        BenchmarkPackagePayload.model_validate(payload)


def test_review_records_have_stable_identity_and_machine_readable_scope() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    assert package.review_records == ()


def test_review_evidence_must_belong_to_this_repository() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    record = _review_record(_read_payload(), review_id="review.wrong_repository")
    record["review_evidence_url"] = (
        "https://github.com/another/repository/pull/96#pullrequestreview-1"
    )
    payload["review_records"] = [record]

    with pytest.raises(ValidationError, match="this repository"):
        BenchmarkPackagePayload.model_validate(payload)


def test_claims_cover_required_types_and_bind_evidence() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    claim_types = {claim.claim_type.value for claim in package.claims}

    assert len(claim_types & {"finding", "method", "dataset", "limitation"}) >= 3
    assert all(claim.evidence_ids for claim in package.claims)


def test_claim_without_evidence_is_rejected() -> None:
    payload = _read_payload()
    payload["claims"][0]["evidence_ids"] = []

    with pytest.raises(ValidationError):
        BenchmarkPackage.model_validate(payload)


def test_paper_metadata_evidence_is_rejected_without_a_supported_locator() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    assert len(package.evidence) == 18
    assert {evidence.evidence_type for evidence in package.evidence} == {"paper_text"}

    payload = _read_payload()
    payload["evidence"][0]["evidence_type"] = "paper_metadata"

    with pytest.raises(ValidationError, match="paper_metadata"):
        BenchmarkPackage.model_validate(payload)


def test_relations_cover_types_and_all_admission_states() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    relation_types = {relation.relation_type.value for relation in package.relations}
    statuses = {relation.status for relation in package.relations}
    assert (
        len(
            relation_types
            & {"supports", "extends", "derived_from", "limits", "contradicts"}
        )
        >= 3
    )
    assert statuses == set(BenchmarkAdmissionStatus)


def test_directional_relations_use_source_relation_target_order() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    relations = {relation.relation_id: relation for relation in package.relations}
    traces = {trace.relation_id: trace for trace in package.reasoning_traces}
    nodes = {node.node_id: node for node in package.graph.nodes}

    extends = relations["relation.revised_tic_extends_initial_tic"]
    assert extends.source_claim_id == "claim.stassun_2019_gaia_revision"
    assert extends.target_claim_id == "claim.stassun_2018_tic_method"
    assert traces[extends.relation_id].premise_claim_ids == (
        extends.source_claim_id,
        extends.target_claim_id,
    )

    derived = relations["relation.clark_catalog_derived_from_tic"]
    assert derived.source_claim_id == "claim.clark_crossmatched_catalog"
    assert derived.target_claim_id == "claim.stassun_2019_gaia_revision"
    assert traces[derived.relation_id].premise_claim_ids == (
        derived.source_claim_id,
        derived.target_claim_id,
    )

    for edge in package.graph.edges:
        if edge.cross_document:
            relation = relations[edge.relation_id]
            assert nodes[edge.source].ref_id == relation.source_claim_id
            assert nodes[edge.target].ref_id == relation.target_claim_id


def test_trace_premises_cannot_reverse_directional_relation() -> None:
    payload = _read_payload()
    trace = payload["reasoning_traces"][0]
    trace["premise_claim_ids"].reverse()

    with pytest.raises(
        ValidationError, match="premises must follow relation direction"
    ):
        BenchmarkPackage.model_validate(payload)


def test_approved_relation_requires_approved_dependencies() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    relation = next(
        relation
        for relation in payload["relations"]
        if relation["status"] == "accepted"
    )
    relation["review_status"] = "approved"

    with pytest.raises(ValidationError, match="has unapproved source claim"):
        BenchmarkPackagePayload.model_validate(payload)


@pytest.mark.parametrize(
    ("dependency", "expected_message"),
    [
        ("target_claim", "has unapproved target claim"),
        ("reasoning_trace", "has unapproved reasoning trace"),
        ("evidence", "has unapproved evidence"),
    ],
)
def test_approved_relation_rejects_each_unapproved_dependency(
    dependency: str,
    expected_message: str,
) -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_scientific_review,
        approved_relation_count=1,
    )
    payload = package.model_dump(mode="json", exclude={"content_hash"})
    relation = next(
        relation
        for relation in payload["relations"]
        if relation["review_status"] == "approved"
    )

    if dependency == "target_claim":
        target_claim = next(
            claim
            for claim in payload["claims"]
            if claim["claim_id"] == relation["target_claim_id"]
        )
        target_claim["review_status"] = "pending_scientific_review"
    elif dependency == "reasoning_trace":
        trace = next(
            trace
            for trace in payload["reasoning_traces"]
            if trace["trace_id"] == relation["reasoning_trace_id"]
        )
        trace["review_status"] = "pending_scientific_review"
    else:
        related_evidence = next(
            evidence
            for evidence in payload["evidence"]
            if evidence["evidence_id"] in relation["evidence_ids"]
        )
        related_evidence["review_status"] = "pending_scientific_review"

    with pytest.raises(ValidationError, match=expected_message):
        BenchmarkPackagePayload.model_validate(payload)


def test_approved_relation_cannot_omit_reasoning_trace() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_scientific_review,
        approved_relation_count=4,
    )
    payload = package.model_dump(mode="json", exclude={"content_hash"})
    rejected = next(
        relation
        for relation in payload["relations"]
        if relation["status"] == "rejected"
    )
    rejected["reasoning_trace_id"] = None

    with pytest.raises(ValidationError, match="requires approved reasoning trace"):
        BenchmarkPackagePayload.model_validate(payload)


def test_accepted_relation_requires_trace_and_both_claims_evidence() -> None:
    payload = _read_payload()
    accepted = next(
        relation
        for relation in payload["relations"]
        if relation["status"] == "accepted"
    )
    source_claim = next(
        claim
        for claim in payload["claims"]
        if claim["claim_id"] == accepted["source_claim_id"]
    )
    accepted["evidence_ids"] = [source_claim["evidence_ids"][0]]

    with pytest.raises(ValidationError, match="lacks target evidence"):
        BenchmarkPackage.model_validate(payload)


def test_accepted_relation_without_trace_is_rejected() -> None:
    payload = _read_payload()
    accepted = next(
        relation
        for relation in payload["relations"]
        if relation["status"] == "accepted"
    )
    accepted["reasoning_trace_id"] = None

    with pytest.raises(ValidationError, match="accepted relation requires"):
        BenchmarkPackage.model_validate(payload)


def test_evidence_less_relation_is_rejected() -> None:
    payload = _read_payload()
    payload["relations"][0]["evidence_ids"] = []

    with pytest.raises(ValidationError):
        BenchmarkPackage.model_validate(payload)


def test_evidence_must_be_bound_by_its_declared_target() -> None:
    payload = _read_payload()
    payload["claims"][0]["evidence_ids"] = [payload["claims"][1]["evidence_ids"][0]]

    with pytest.raises(ValidationError, match="is not bound by its declared target"):
        BenchmarkPackage.model_validate(payload)


def test_candidate_relation_cannot_reference_a_dangling_trace() -> None:
    payload = _read_payload()
    candidate = next(
        relation
        for relation in payload["relations"]
        if relation["status"] == "candidate"
    )
    candidate["reasoning_trace_id"] = "trace.missing"

    with pytest.raises(ValidationError, match="unknown relation trace"):
        BenchmarkPackage.model_validate(payload)


def test_rejected_relation_requires_a_reason() -> None:
    payload = _read_payload()
    rejected = next(
        relation
        for relation in payload["relations"]
        if relation["status"] == "rejected"
    )
    rejected["rejection_reason"] = None

    with pytest.raises(ValidationError, match="rejected relation requires"):
        BenchmarkPackage.model_validate(payload)


def test_trace_must_point_back_to_the_pinning_relation() -> None:
    payload = _read_payload()
    payload["reasoning_traces"][0]["relation_id"] = payload["relations"][1][
        "relation_id"
    ]

    with pytest.raises(ValidationError, match="not pinned by its relation"):
        BenchmarkPackage.model_validate(payload)


def test_graph_rejects_dangling_edge_endpoint() -> None:
    payload = _read_payload()
    payload["graph"]["edges"][0]["target"] = "node.missing"

    with pytest.raises(ValidationError, match="unknown graph edge node"):
        BenchmarkPackage.model_validate(payload)


def test_cross_document_edge_rejects_non_accepted_relation() -> None:
    payload = _read_payload()
    cross_edge = next(
        edge for edge in payload["graph"]["edges"] if edge["cross_document"]
    )
    rejected = next(
        relation
        for relation in payload["relations"]
        if relation["status"] == "rejected"
    )
    cross_edge["relation_id"] = rejected["relation_id"]

    with pytest.raises(ValidationError, match="non-accepted relation"):
        BenchmarkPackage.model_validate(payload)


def test_cross_document_edge_must_match_relation_claim_endpoints() -> None:
    payload = _read_payload()
    cross_edges = [edge for edge in payload["graph"]["edges"] if edge["cross_document"]]
    cross_edges[0]["source"] = cross_edges[1]["source"]

    with pytest.raises(ValidationError, match="endpoints do not match relation claims"):
        BenchmarkPackage.model_validate(payload)


def test_graph_uses_only_frozen_taxonomy_types() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    allowed_nodes = set(package.graph_taxonomy.allowed_node_types)
    allowed_edges = set(package.graph_taxonomy.allowed_edge_types)

    assert all(node.node_type in allowed_nodes for node in package.graph.nodes)
    assert all(edge.edge_type in allowed_edges for edge in package.graph.edges)


def test_metrics_are_computed_from_approved_relation_fixture() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.approved,
        approved_relation_count=4,
    )
    expected_papers = tuple(
        dict.fromkeys(
            paper_id
            for scenario in package.search_scenarios
            for paper_id in scenario.expected_paper_ids
        )
    )
    results = evaluate_benchmark(
        package,
        BenchmarkEvaluationInput(
            retrieved_expected_paper_ids=expected_papers[:-1],
            schema_items_valid=9,
            schema_items_total=10,
            evidence_requirements_satisfied=8,
            evidence_requirements_total=10,
            scientifically_reviewed_relations_correct=3,
            scientifically_reviewed_relations_total=4,
            evidence_less_relations_blocked=5,
            evidence_less_relations_total=5,
        ),
    )
    by_id = {result.metric_id: result for result in results}

    assert by_id[BenchmarkMetricId.candidate_recall].numerator == 5
    assert by_id[BenchmarkMetricId.candidate_recall].denominator == 6
    assert by_id[BenchmarkMetricId.schema_pass_rate].value == 0.9
    assert by_id[BenchmarkMetricId.evidence_coverage].value == 0.8
    assert by_id[BenchmarkMetricId.relation_scientific_accuracy].value == 0.75
    assert by_id[BenchmarkMetricId.evidence_less_relation_block_rate].value == 1.0


def test_relation_scientific_accuracy_is_not_available_without_approved_relations() -> (
    None
):
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_scientific_review,
        approved_relation_count=0,
    )
    results = evaluate_benchmark(package, _evaluation_input())
    by_id = {result.metric_id: result for result in results}

    relation_accuracy = by_id[BenchmarkMetricId.relation_scientific_accuracy]
    assert relation_accuracy.numerator == 0
    assert relation_accuracy.denominator == 0
    assert relation_accuracy.value is None
    assert relation_accuracy.status == "not_available"


def test_relation_scientific_accuracy_rejects_nonzero_counts_without_approved_relations() -> (
    None
):
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_scientific_review,
        approved_relation_count=0,
    )

    with pytest.raises(ValueError, match="counts must be zero"):
        evaluate_benchmark(
            package,
            _evaluation_input(
                scientifically_reviewed_relations_correct=1,
                scientifically_reviewed_relations_total=1,
            ),
        )


def test_relation_scientific_accuracy_total_must_match_approved_relations() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.approved,
        approved_relation_count=4,
    )

    with pytest.raises(ValueError, match="total must equal"):
        evaluate_benchmark(
            package,
            _evaluation_input(
                scientifically_reviewed_relations_correct=3,
                scientifically_reviewed_relations_total=3,
            ),
        )


def test_relation_scientific_accuracy_rejects_correct_above_total() -> None:
    with pytest.raises(ValidationError, match="numerator must not exceed denominator"):
        _evaluation_input(
            scientifically_reviewed_relations_correct=4,
            scientifically_reviewed_relations_total=3,
        )


def test_pending_benchmark_does_not_report_relation_accuracy() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    results = evaluate_benchmark(package, _evaluation_input())
    by_id = {result.metric_id: result for result in results}

    assert package.review_status is BenchmarkReviewStatus.pending_scientific_review
    assert all(
        relation.review_status is BenchmarkReviewStatus.pending_scientific_review
        for relation in package.relations
    )
    assert (
        by_id[BenchmarkMetricId.relation_scientific_accuracy].status == "not_available"
    )


def test_pending_package_blocks_accuracy_even_with_approved_relations() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_scientific_review,
        approved_relation_count=4,
    )
    results = evaluate_benchmark(package, _evaluation_input())
    by_id = {result.metric_id: result for result in results}

    assert (
        by_id[BenchmarkMetricId.relation_scientific_accuracy].status == "not_available"
    )


def test_pending_package_rejects_nonzero_relation_accuracy_counts() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_scientific_review,
        approved_relation_count=4,
    )

    with pytest.raises(ValueError, match="counts must be zero"):
        evaluate_benchmark(
            package,
            _evaluation_input(
                scientifically_reviewed_relations_correct=3,
                scientifically_reviewed_relations_total=4,
            ),
        )


def test_metrics_report_not_available_for_empty_denominators() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    results = evaluate_benchmark(
        package,
        BenchmarkEvaluationInput(
            schema_items_valid=0,
            schema_items_total=0,
            evidence_requirements_satisfied=0,
            evidence_requirements_total=0,
            scientifically_reviewed_relations_correct=0,
            scientifically_reviewed_relations_total=0,
            evidence_less_relations_blocked=0,
            evidence_less_relations_total=0,
        ),
    )
    by_id = {result.metric_id: result for result in results}

    for metric_id in (
        BenchmarkMetricId.schema_pass_rate,
        BenchmarkMetricId.evidence_coverage,
        BenchmarkMetricId.relation_scientific_accuracy,
        BenchmarkMetricId.evidence_less_relation_block_rate,
    ):
        assert by_id[metric_id].value is None
        assert by_id[metric_id].status == "not_available"


def test_benchmark_models_export_machine_readable_json_schema() -> None:
    schema = BenchmarkPackage.model_json_schema()

    assert "content_hash" in schema["required"]
    assert "seed_papers" in schema["required"]
    assert "relations" in schema["required"]
    assert "graph" in schema["required"]
    assert BenchmarkPackagePayload.model_json_schema()["type"] == "object"
