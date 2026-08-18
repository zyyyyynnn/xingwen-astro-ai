"""Generate the Core standalone schema set.

This command is the single owner of the ``packages/schemas/generated/core``
standalone export. The model tuple below is the canonical Core contract list;
local generation and CI checking must both go through this command so the
owned directory can never drift from a hand-copied ``--include`` list. The
complete OpenAPI export stays with ``export_openapi.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_schemas import (  # noqa: E402
    check_contracts,
    discover_models,
    prune_owned_json_schemas,
    render_contracts,
    write_contracts,
)

CORE_MODELS: tuple[str, ...] = (
    "ResearchProject",
    "UpdateResearchProjectRequest",
    "ResearchCatalogOption",
    "ResearchPlanningCatalog",
    "ModelExecutionRecord",
    "PlannerClarificationRequired",
    "PlannerDraftReady",
    "PlannerPartial",
    "PlannerUnsupported",
    "PlannerRefused",
    "PlannerOutcome",
    "ResearchThreadEntry",
    "ResearchThreadSummary",
    "ResearchTurnRequest",
    "ResearchTurnResult",
    "ResearchContractDraft",
    "ResearchContract",
    "ResearchRun",
    "CreateUserFeedbackRequest",
    "UserFeedback",
    "CreateRevisionPlanRequest",
    "RevisionVersionDecision",
    "RevisionConflict",
    "RevisionPlan",
    "ConfirmRevisionPlanRequest",
    "RunEvent",
    "RunStepRead",
    "ResearchArtifact",
    "ArtifactVersion",
    "ResearchArtifactDetail",
    "ArtifactVersionDetail",
    "PaperSummaryArtifactContent",
    "PaperSummaryRead",
    "PaperSummaryPdfSourceRead",
    "PaperCollectionRead",
    "PaperCollectionCandidateRead",
    "PaperCandidateInputBinding",
    "DataArtifactReadBase",
    "DatasetArtifactRead",
    "FieldDictionaryArtifactRead",
    "SourceCollectionArtifactRead",
    "DataArtifactRowRead",
    "LiteratureClaimRead",
    "LiteratureRelationRead",
    "LiteratureReasoningTraceRead",
    "GraphArtifactRead",
    "GraphNodeRead",
    "GraphEdgeRead",
    "GraphEvidenceUseRead",
    "CreateArtifactExportRequest",
    "ArtifactExportRead",
    "EvidenceRead",
    "SourceSnapshotDetail",
    "SessionCreated",
    "WorkspaceSnapshot",
    "ShareSnapshot",
    "ShareSnapshotCreated",
    "PublicShareSnapshot",
    "ResearchInputRef",
    "ResearchInputDetail",
    "CreateResearchInputRequest",
    "CreateResearchInputMultipartRequest",
)

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "packages/schemas/generated/core"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="directory receiving manifest.json and json/*.schema.json",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when generated files are missing, stale, or orphaned",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = discover_models()
    unknown = sorted(set(CORE_MODELS) - models.keys())
    if unknown:
        print(f"unknown schema model(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    selected = {name: models[name] for name in sorted(CORE_MODELS)}
    rendered = render_contracts(selected)
    if args.check:
        return check_contracts(args.output, rendered)

    write_contracts(args.output, rendered)
    removed = prune_owned_json_schemas(args.output, rendered)
    print(f"exported {len(rendered) - 1} core schemas to {args.output}")
    if removed:
        print(f"pruned {removed} orphan schema file(s) from {args.output / 'json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
