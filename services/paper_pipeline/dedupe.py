"""Deterministic duplicate grouping with explicit uncertainty and conflicts."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_collection import (
    PaperCandidateConflict,
    PaperDuplicateGroup,
    PaperPotentialDuplicate,
)

from .canonicalize import CandidateDraft, author_surname
from .constants import DEDUPE_VERSION


@dataclass(frozen=True)
class CandidateDedupeInfo:
    duplicate_group_id: str
    canonical_paper_id: str
    evidence: tuple[str, ...]
    conflicts: tuple[PaperCandidateConflict, ...]


@dataclass(frozen=True)
class DedupeResult:
    groups: tuple[PaperDuplicateGroup, ...]
    potential_duplicates: tuple[PaperPotentialDuplicate, ...]
    candidate_info: dict[str, CandidateDedupeInfo]


def group_duplicates(candidates: tuple[CandidateDraft, ...]) -> DedupeResult:
    ordered = tuple(sorted(candidates, key=lambda candidate: candidate.candidate_id))
    parent = {candidate.candidate_id: candidate.candidate_id for candidate in ordered}
    pair_evidence: dict[tuple[str, str], str] = {}
    potential: list[PaperPotentialDuplicate] = []
    conflict_registry: dict[str, list[PaperCandidateConflict]] = {
        candidate.candidate_id: [] for candidate in ordered
    }

    def find(candidate_id: str) -> str:
        while parent[candidate_id] != candidate_id:
            parent[candidate_id] = parent[parent[candidate_id]]
            candidate_id = parent[candidate_id]
        return candidate_id

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        lower, higher = sorted((left_root, right_root))
        parent[higher] = lower

    for left, right in combinations(ordered, 2):
        pair = (left.candidate_id, right.candidate_id)
        basis: str | None = None
        if left.doi and left.doi == right.doi:
            basis = "doi_exact"
        elif left.arxiv_id and left.arxiv_id == right.arxiv_id:
            basis = "arxiv_exact"
        elif (
            left.normalized_title == right.normalized_title
            and left.year is not None
            and left.year == right.year
        ):
            left_authors = set(left.normalized_authors)
            right_authors = set(right.normalized_authors)
            same_first_author = bool(
                left.normalized_authors
                and right.normalized_authors
                and author_surname(left.normalized_authors[0])
                == author_surname(right.normalized_authors[0])
            )
            if same_first_author or left_authors.intersection(right_authors):
                basis = "title_year_author_match"
            else:
                reason = (
                    "title/year match has missing author evidence"
                    if not left_authors or not right_authors
                    else "title/year match has conflicting authors"
                )
                potential.append(
                    PaperPotentialDuplicate(
                        candidate_ids=pair,
                        basis="title_year",
                        reason=reason,
                    )
                )
                for candidate, related in ((left, right), (right, left)):
                    conflict_registry[candidate.candidate_id].append(
                        PaperCandidateConflict(
                            field="authors",
                            related_candidate_id=related.candidate_id,
                            classification="uncertain_match",
                            detail=reason,
                        )
                    )
        if basis:
            union(*pair)
            pair_evidence[pair] = basis

    members_by_root: dict[str, list[CandidateDraft]] = {}
    for candidate in ordered:
        members_by_root.setdefault(find(candidate.candidate_id), []).append(candidate)

    groups: list[PaperDuplicateGroup] = []
    candidate_info: dict[str, CandidateDedupeInfo] = {}
    for members in sorted(
        members_by_root.values(), key=lambda values: tuple(item.candidate_id for item in values)
    ):
        member_ids = tuple(sorted(candidate.candidate_id for candidate in members))
        group_hash = compute_canonical_payload_hash(
            {"rule_version": DEDUPE_VERSION, "candidate_ids": member_ids}
        )
        group_id = f"duplicate.{group_hash.removeprefix('sha256:')}"
        canonical_paper_id = _group_canonical_paper_id(tuple(members))
        match_basis = tuple(
            sorted(
                {
                    basis
                    for pair, basis in pair_evidence.items()
                    if pair[0] in member_ids and pair[1] in member_ids
                }
            )
        ) or ("singleton",)

        group_conflicts = _group_conflicts(tuple(members), conflict_registry)
        groups.append(
            PaperDuplicateGroup(
                duplicate_group_id=group_id,
                canonical_paper_id=canonical_paper_id,
                candidate_ids=member_ids,
                match_basis=match_basis,
                conflicts=group_conflicts,
            )
        )
        for candidate in members:
            evidence = tuple(
                sorted(
                    f"{basis}:{other}"
                    for pair, basis in pair_evidence.items()
                    if candidate.candidate_id in pair
                    for other in pair
                    if other != candidate.candidate_id
                )
            )
            candidate_info[candidate.candidate_id] = CandidateDedupeInfo(
                duplicate_group_id=group_id,
                canonical_paper_id=canonical_paper_id,
                evidence=evidence or ("singleton",),
                conflicts=tuple(
                    sorted(
                        conflict_registry[candidate.candidate_id],
                        key=lambda conflict: (
                            conflict.field,
                            conflict.related_candidate_id,
                            conflict.classification,
                        ),
                    )
                ),
            )

    return DedupeResult(
        groups=tuple(sorted(groups, key=lambda group: group.duplicate_group_id)),
        potential_duplicates=tuple(
            sorted(potential, key=lambda item: item.candidate_ids)
        ),
        candidate_info=candidate_info,
    )


def _group_canonical_paper_id(members: tuple[CandidateDraft, ...]) -> str:
    basis_priority = {"doi": 0, "arxiv_id": 1, "title_year_authors": 2, "source_record": 3}
    representative = min(
        members,
        key=lambda candidate: (
            basis_priority[candidate.canonical_identity_basis],
            candidate.canonical_paper_id,
        ),
    )
    return representative.canonical_paper_id


def _group_conflicts(
    members: tuple[CandidateDraft, ...],
    conflict_registry: dict[str, list[PaperCandidateConflict]],
) -> tuple[PaperCandidateConflict, ...]:
    fields = {
        "doi": lambda candidate: candidate.doi,
        "arxiv_id": lambda candidate: candidate.arxiv_id,
        "title": lambda candidate: candidate.normalized_title,
        "year": lambda candidate: candidate.year,
        "authors": lambda candidate: candidate.normalized_authors,
    }
    for field, getter in fields.items():
        for left, right in combinations(members, 2):
            left_value, right_value = getter(left), getter(right)
            if left_value in (None, (), "") or right_value in (None, (), ""):
                continue
            if left_value == right_value:
                continue
            detail = f"duplicate group retains conflicting {field} values"
            for candidate, related in ((left, right), (right, left)):
                conflict_registry[candidate.candidate_id].append(
                    PaperCandidateConflict(
                        field=field,
                        related_candidate_id=related.candidate_id,
                        classification="conflict",
                        detail=detail,
                    )
                )
    conflicts = {
        (
            conflict.field,
            conflict.related_candidate_id,
            conflict.classification,
            conflict.detail,
        ): conflict
        for member in members
        for conflict in conflict_registry[member.candidate_id]
        if conflict.related_candidate_id in {candidate.candidate_id for candidate in members}
    }
    return tuple(conflicts[key] for key in sorted(conflicts))
