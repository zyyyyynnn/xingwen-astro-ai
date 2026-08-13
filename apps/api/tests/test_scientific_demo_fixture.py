from __future__ import annotations

import json

from app.schemas.core import ArtifactVersionDetail
from app.schemas.scientific_artifact_api import ScientificArtifactRead
from services.scientific_skills.demo_fixture import (
    FIXTURE_OUTPUT_PATH,
    build_scientific_fixture_document,
)


def test_committed_scientific_demo_fixture_is_generated_from_current_contract() -> None:
    committed = json.loads(FIXTURE_OUTPUT_PATH.read_text(encoding="utf-8"))

    assert committed == build_scientific_fixture_document()
    assert committed["$generated"]["scenario_id"] == (
        "exoplanet_host_star.scientific_artifacts"
    )
    assert len(committed["entries"]) == 4

    for entry in committed["entries"]:
        version = ArtifactVersionDetail.model_validate(entry["version"])
        read = ScientificArtifactRead.model_validate(entry["read"])
        assert version.id == read.artifact_version_id
        assert version.content_hash == read.content_hash
        assert version.source_mode.value == "fixture"
        assert read.producer_execution.producer.name == (
            "scientific_artifact_assembler"
        )
        assert entry["content_blobs"] == []
