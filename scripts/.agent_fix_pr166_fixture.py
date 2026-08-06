from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: fixture-seam anchor mismatch: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


service = "apps/api/src/app/services/literature_artifacts.py"
replace_once(
    service,
    "    def __init__(self, artifacts: ArtifactReadService) -> None:\n"
    "        self._artifacts = artifacts\n",
    "    def __init__(\n"
    "        self,\n"
    "        artifacts: ArtifactReadService,\n"
    "        *,\n"
    "        paper_summary_reader: object | None = None,\n"
    "    ) -> None:\n"
    "        self._artifacts = artifacts\n"
    "        self._paper_summaries = (\n"
    "            paper_summary_reader\n"
    "            or getattr(artifacts, \"paper_summary_reader\", None)\n"
    "            or PaperSummaryReadService(artifacts)\n"
    "        )\n",
)
replace_once(
    service,
    "            summary_read = PaperSummaryReadService(self._artifacts).get_summary(\n",
    "            summary_read = self._paper_summaries.get_summary(\n",
)

support = "apps/api/tests/literature_artifact_test_support.py"
replace_once(
    support,
    "from app.schemas.literature_relation import (\n",
    "from app.schemas.paper_summary_api import (\n"
    "    PaperSummaryPaperMetadata,\n"
    "    PaperSummaryRead,\n"
    ")\n"
    "from app.schemas.literature_relation import (\n",
)
replace_once(
    support,
    "        self.full_content_requests: list[bool] = []\n",
    "        self.full_content_requests: list[bool] = []\n"
    "        self.paper_summary_reader = FixturePaperSummaryReads(self)\n",
)
fixture_reader = '''

class FixturePaperSummaryReads:
    """Test-only Summary envelope validator for frozen D-01 benchmark inputs."""

    def __init__(self, artifacts: FixtureArtifactReads) -> None:
        self._artifacts = artifacts

    def get_summary(self, *, version_id: str, session_id: str) -> PaperSummaryRead:
        version = self._artifacts.get_version(
            version_id=version_id,
            session_id=session_id,
            full_content=True,
        )
        artifact = self._artifacts.get_artifact(
            artifact_id=version.artifact_id, session_id=session_id
        )
        summary = PaperSummaryArtifactContent.model_validate(version.content)
        producer = summary.producer
        runtime = version.producer_execution
        if (
            artifact.kind.value != "paper_summary"
            or artifact.project_id != version.project_id
            or version.schema_version != summary.schema_version
            or version.content_hash
            != compute_canonical_payload_hash(version.content)
            or version.input_hash != summary.input_hash
            or runtime.run_id != version.created_by_run_id
            or runtime.step_key != producer.step_key
            or runtime.producer.type != producer.producer_type
            or runtime.producer.name != producer.producer_name
            or runtime.producer.version != producer.producer_version
            or runtime.producer.model_name != producer.model_name
            or runtime.producer.prompt_name != producer.prompt_name
            or runtime.producer.prompt_version != producer.prompt_version
            or runtime.producer.prompt_hash != producer.prompt_hash
            or runtime.parameters_hash != producer.parameters_hash
            or runtime.producer.parameters_hash != producer.parameters_hash
            or runtime.input_hash != summary.input_hash
            or runtime.output_hash != version.content_hash
            or runtime.status != "completed"
            or version.producer != runtime.producer
        ):
            raise _not_found("PAPER_SUMMARY_INVALID")
        if producer.run_id is not None and producer.run_id != version.created_by_run_id:
            raise _not_found("PAPER_SUMMARY_INVALID")
        return PaperSummaryRead(
            artifact_version_id=version.id,
            artifact_id=version.artifact_id,
            project_id=version.project_id,
            version_number=version.version_number,
            supersedes_version_id=version.supersedes_version_id,
            source_mode=version.source_mode,
            content_hash=version.content_hash,
            input_hash=version.input_hash,
            created_at=version.created_at,
            paper=PaperSummaryPaperMetadata(
                paper_id=summary.paper_id,
                title=summary.paper_id,
            ),
            summary=summary,
            producer_execution=runtime,
            source_snapshots=version.source_snapshots,
            evidence=version.evidence,
        )
'''
replace_once(
    support,
    "\ndef build_literature_fixture() -> LiteratureFixture:\n",
    fixture_reader + "\n\ndef build_literature_fixture() -> LiteratureFixture:\n",
)

postgres = "apps/api/tests/test_literature_artifacts_postgres.py"
replace_once(
    postgres,
    "from literature_artifact_test_support import (\n    _claim_version,\n",
    "from literature_artifact_test_support import (\n"
    "    FixturePaperSummaryReads,\n"
    "    _claim_version,\n",
)
replace_once(
    postgres,
    "    app = create_app()\n"
    "    app.state.artifact_read_service = ArtifactReadService(factory)\n",
    "    app = create_app()\n"
    "    artifact_reads = ArtifactReadService(factory)\n"
    "    setattr(\n"
    "        artifact_reads,\n"
    "        \"paper_summary_reader\",\n"
    "        FixturePaperSummaryReads(artifact_reads),\n"
    "    )\n"
    "    app.state.artifact_read_service = artifact_reads\n",
)

print("PR #166 benchmark Summary test seam applied")
