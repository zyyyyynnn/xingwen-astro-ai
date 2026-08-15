"""Semantic tests for the visual model asset contract and adoption profiles.

These tests pin the long-lived contract invariants of
``services/scientific_document/model_asset_contract.py`` and the visual
runtime-profile admission rules of ``adoption_contract.py``: complete
component graph, tamper/path/symlink rejection, path-independent identity and
independent CPU/GPU admission.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[3]
ADOPTION = ROOT / "services" / "scientific_document" / "upstream_adoption.json"
ASSETS = ADOPTION.parent / "visual_model_assets.json"

EXPECTED_BUNDLE_DIGEST = (
    "sha256:148cac3e8bd8464618ac9e6fc95c4b2a53ee10f4d7fd7505a53ab709ffd73484"
)
EXPECTED_CPU_CONFIGURATION_HASH = (
    "sha256:479f5c5e286b0564c5e9f0f7b8850e379ea280c504fde8dfb1861e82f6ecf6ae"
)


def _visual_entry() -> dict:
    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    return next(
        entry
        for entry in data["entries"]
        if entry["capability"] == "visual_ocr_layout_table_formula"
    )


def _visual_configuration_params(visual: dict) -> dict:
    return {
        "pipeline_version": visual["pipeline_version"],
        "runtime_backend": visual["runtime_backend"],
        "component_execution_policy": visual["component_execution_policy"],
        "component_directory_bindings": visual["component_directory_bindings"],
        "directory_binding_policy": visual["runtime_directory_binding"],
        "network_policy": visual["runtime_network_policy"],
        "implicit_download_policy": visual["runtime_download_policy"],
        "paddleocr_package": visual["package"],
        "paddleocr_extra": visual["package_extra"],
        "paddleocr_version": visual["package_version"],
        "paddlex_package": visual["paddlex_package"],
        "paddlex_extras": list(visual["paddlex_extras"]),
        "paddlex_version": visual["paddlex_version"],
    }


def test_visual_asset_manifest_binds_complete_component_graph() -> None:
    from services.scientific_document.model_asset_contract import load_asset_manifest

    assets = load_asset_manifest(ASSETS)
    components = {component["role"]: component for component in assets["components"]}
    assert set(components) == {"layout_detection", "vlm_recognition"}
    assert assets["bundle_digest"] == EXPECTED_BUNDLE_DIGEST


def test_runtime_configuration_hash_is_path_independent() -> None:
    from services.scientific_document.model_asset_contract import load_asset_manifest
    from services.scientific_document.runtime_provenance import (
        compute_runtime_configuration_hash,
    )

    assets = load_asset_manifest(ASSETS)
    visual = _visual_entry()
    cpu = next(
        profile for profile in visual["runtime_profiles"] if profile["profile_id"] == "cpu"
    )
    digest = compute_runtime_configuration_hash(
        assets,
        **_visual_configuration_params(visual),
        distribution=cpu["distribution"],
        version=cpu["version"],
        device=cpu["device"],
    )
    assert digest == EXPECTED_CPU_CONFIGURATION_HASH
    # Identity must not depend on machine paths or usernames.
    serialized = json.dumps(assets, sort_keys=True)
    assert "\\" not in serialized
    assert "/home/" not in serialized
    assert "/Users/" not in serialized


def test_configuration_hash_changes_when_adoption_policy_changes() -> None:
    from services.scientific_document.model_asset_contract import load_asset_manifest
    from services.scientific_document.runtime_provenance import (
        compute_runtime_configuration_hash,
    )

    assets = load_asset_manifest(ASSETS)
    visual = _visual_entry()
    cpu = next(
        profile for profile in visual["runtime_profiles"] if profile["profile_id"] == "cpu"
    )
    cpu_runtime = {
        "distribution": cpu["distribution"],
        "version": cpu["version"],
        "device": cpu["device"],
    }
    params = _visual_configuration_params(visual)
    baseline = compute_runtime_configuration_hash(assets, **params, **cpu_runtime)
    assert baseline == cpu["configuration_hash"]

    mutations = {
        "pipeline_version": "v1.7",
        "runtime_backend": "server",
        "directory_binding_policy": "cache",
        "network_policy": "enabled",
        "implicit_download_policy": "enabled",
        "paddleocr_version": "3.6.1",
        "paddlex_version": "3.6.1",
        "paddlex_extras": ["ocr"],
        "component_directory_bindings": {
            **params["component_directory_bindings"],
            "vlm_recognition": "another_model_dir",
        },
    }
    for key, changed in mutations.items():
        mutated = compute_runtime_configuration_hash(
            assets, **{**params, key: changed}, **cpu_runtime
        )
        assert mutated != baseline, key

    flipped_policy = dict(params["component_execution_policy"])
    flipped_policy["use_chart_recognition"] = True
    flipped = compute_runtime_configuration_hash(
        assets, **{**params, "component_execution_policy": flipped_policy}, **cpu_runtime
    )
    assert flipped != baseline


def test_bundle_and_configuration_hash_change_when_asset_bytes_change() -> None:
    from services.scientific_document.model_asset_contract import (
        compute_bundle_digest,
        compute_component_asset_digest,
        load_asset_manifest,
        validate_asset_manifest,
    )
    from services.scientific_document.runtime_provenance import (
        compute_runtime_configuration_hash,
    )

    committed = load_asset_manifest(ASSETS)
    visual = _visual_entry()
    params = _visual_configuration_params(visual)
    cpu = next(
        profile for profile in visual["runtime_profiles"] if profile["profile_id"] == "cpu"
    )
    cpu_runtime = {
        "distribution": cpu["distribution"],
        "version": cpu["version"],
        "device": cpu["device"],
    }

    # Asset bytes change -> bundle digest and configuration hash both change.
    data = json.loads(ASSETS.read_text(encoding="utf-8"))
    layout = next(
        component
        for component in data["components"]
        if component["role"] == "layout_detection"
    )
    layout["files"][0]["sha256"] = "sha256:" + "0" * 64
    layout["asset_digest"] = compute_component_asset_digest(layout["files"])
    data["bundle_digest"] = compute_bundle_digest(data)
    tampered = validate_asset_manifest(data)
    assert tampered["bundle_digest"] != committed["bundle_digest"]
    changed = compute_runtime_configuration_hash(tampered, **params, **cpu_runtime)
    assert changed != cpu["configuration_hash"]

    # Binding semantics change -> bundle digest unchanged, config hash changes.
    rebound = compute_runtime_configuration_hash(
        committed,
        **{
            **params,
            "component_directory_bindings": {
                **params["component_directory_bindings"],
                "vlm_recognition": "another_model_dir",
            },
        },
        **cpu_runtime,
    )
    assert compute_bundle_digest(committed) == committed["bundle_digest"]
    assert rebound != cpu["configuration_hash"]


def test_bundle_digest_ignores_manifest_format_metadata() -> None:
    from services.scientific_document.model_asset_contract import (
        compute_bundle_digest,
        load_asset_manifest,
    )

    assets = load_asset_manifest(ASSETS)
    baseline = compute_bundle_digest(assets)
    mutated = json.loads(json.dumps(assets))
    mutated["manifest_id"] = "renamed-manifest"
    mutated["schema_version"] = "9.9.9"
    assert compute_bundle_digest(mutated) == baseline


def test_model_asset_digest_is_order_insensitive_and_tamper_evident() -> None:
    from services.scientific_document.model_asset_contract import (
        compute_component_asset_digest,
    )

    files = [
        {"path": "b.bin", "size": 2, "sha256": "sha256:" + "b" * 64},
        {"path": "a.bin", "size": 1, "sha256": "sha256:" + "a" * 64},
    ]
    assert compute_component_asset_digest(files) == compute_component_asset_digest(
        list(reversed(files))
    )
    tampered = [dict(item) for item in files]
    tampered[0]["size"] = 3
    assert compute_component_asset_digest(files) != compute_component_asset_digest(tampered)


def test_visual_manifest_rejects_incomplete_graph_and_short_revision() -> None:
    from services.scientific_document.model_asset_contract import (
        ModelAssetContractError,
        load_asset_manifest,
        validate_asset_manifest,
    )

    assets = load_asset_manifest(ASSETS)
    incomplete = json.loads(json.dumps(assets))
    incomplete["components"] = [
        component
        for component in incomplete["components"]
        if component["role"] != "layout_detection"
    ]
    with pytest.raises(ModelAssetContractError) as excinfo:
        validate_asset_manifest(incomplete)
    assert excinfo.value.code == "model_asset_component_graph_incomplete"

    short_revision = json.loads(json.dumps(assets))
    vlm = next(
        component
        for component in short_revision["components"]
        if component["role"] == "vlm_recognition"
    )
    vlm["revision"] = vlm["revision"][:12]
    with pytest.raises(ModelAssetContractError) as excinfo:
        validate_asset_manifest(short_revision)
    assert excinfo.value.code == "model_asset_revision_invalid"


def test_visual_manifest_rejects_duplicate_role_and_path_traversal() -> None:
    from services.scientific_document.model_asset_contract import (
        ModelAssetContractError,
        load_asset_manifest,
        validate_asset_manifest,
    )

    assets = load_asset_manifest(ASSETS)
    duplicate = json.loads(json.dumps(assets))
    duplicate["components"].append(json.loads(json.dumps(duplicate["components"][0])))
    with pytest.raises(ModelAssetContractError) as excinfo:
        validate_asset_manifest(duplicate)
    assert excinfo.value.code == "model_asset_duplicate_role"

    traversal = json.loads(json.dumps(assets))
    traversal["components"][0]["files"][0]["path"] = "../escape.bin"
    with pytest.raises(ModelAssetContractError) as excinfo:
        validate_asset_manifest(traversal)
    assert excinfo.value.code == "model_asset_path_invalid"


def _component(data: dict, role: str) -> dict:
    return next(
        component for component in data["components"] if component["role"] == role
    )


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda data: _component(data, "vlm_recognition")["official_source"].pop("repo_id"),
            "model_asset_source_invalid",
        ),
        (
            lambda data: _component(data, "vlm_recognition")["official_source"].__setitem__(
                "repo_id", "another/repo"
            ),
            "model_asset_source_identity_mismatch",
        ),
        (
            lambda data: _component(data, "vlm_recognition")["official_source"].__setitem__(
                "unexpected_field", "x"
            ),
            "model_asset_source_invalid",
        ),
        (
            lambda data: _component(data, "layout_detection")["official_source"].pop(
                "model_name"
            ),
            "model_asset_source_invalid",
        ),
        (
            lambda data: _component(data, "layout_detection")["official_source"].__setitem__(
                "model_name", "SomeOtherModel"
            ),
            "model_asset_source_identity_mismatch",
        ),
        (
            lambda data: _component(data, "layout_detection")["official_source"].__setitem__(
                "reviewed_at", "2026-01-01"
            ),
            "model_asset_source_invalid",
        ),
    ],
    ids=[
        "vlm-missing-repo-id",
        "vlm-repo-id-mismatch",
        "vlm-unexpected-field",
        "layout-missing-model-name",
        "layout-model-name-mismatch",
        "layout-arbitrary-metadata",
    ],
)
def test_visual_manifest_rejects_inconsistent_official_source(
    mutate: object, expected_code: str
) -> None:
    from services.scientific_document.model_asset_contract import (
        ModelAssetContractError,
        load_asset_manifest,
        validate_asset_manifest,
    )

    data = json.loads(json.dumps(load_asset_manifest(ASSETS)))
    mutate(data)
    with pytest.raises(ModelAssetContractError) as excinfo:
        validate_asset_manifest(data)
    assert excinfo.value.code == expected_code


def test_component_directory_rejects_missing_extra_and_tampered_files(tmp_path: Path) -> None:
    from services.scientific_document.model_asset_contract import (
        ModelAssetContractError,
        verify_component_directory,
    )

    payload = b"verified"
    component = {
        "files": [
            {
                "path": "model.bin",
                "size": len(payload),
                "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            }
        ]
    }
    root = tmp_path.resolve()
    with pytest.raises(ModelAssetContractError) as excinfo:
        verify_component_directory(component, root)
    assert excinfo.value.code == "model_asset_file_missing"
    (root / "model.bin").write_bytes(payload)
    verify_component_directory(component, root)
    (root / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ModelAssetContractError) as excinfo:
        verify_component_directory(component, root)
    assert excinfo.value.code == "model_asset_file_unexpected"
    (root / "extra.json").unlink()
    (root / "model.bin").write_bytes(b"tampered")
    with pytest.raises(ModelAssetContractError) as excinfo:
        verify_component_directory(component, root)
    assert excinfo.value.code == "model_asset_hash_mismatch"


def test_model_bundle_requires_exact_component_directories(tmp_path: Path) -> None:
    from services.scientific_document.model_asset_contract import (
        ModelAssetContractError,
        load_asset_manifest,
        verify_model_bundle,
    )

    assets = load_asset_manifest(ASSETS)
    with pytest.raises(ModelAssetContractError) as excinfo:
        verify_model_bundle(assets, {"layout_detection": tmp_path.resolve()})
    assert excinfo.value.code == "model_asset_directory_binding_missing"


@pytest.mark.parametrize(
    "mutate",
    [
        None,
        lambda bindings: {
            key: value for key, value in bindings.items() if key != "layout_detection"
        },
        lambda bindings: {**bindings, "other_component": "other_model_dir"},
        lambda bindings: {**bindings, "vlm_recognition": bindings["layout_detection"]},
    ],
    ids=["committed", "missing-binding", "unknown-binding", "duplicate-vendor-parameter"],
)
def test_visual_adoption_bindings_cover_exact_asset_roles(
    mutate: object, tmp_path: Path
) -> None:
    import shutil

    from services.scientific_document.adoption_contract import load_adoption_manifest

    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    visual = next(
        entry
        for entry in data["entries"]
        if entry["capability"] == "visual_ocr_layout_table_formula"
    )
    if mutate is not None:
        visual["component_directory_bindings"] = mutate(
            dict(visual["component_directory_bindings"])
        )
    manifest_copy = tmp_path / "upstream_adoption.json"
    manifest_copy.write_text(json.dumps(data), encoding="utf-8")
    shutil.copyfile(ASSETS, tmp_path / "visual_model_assets.json")
    shutil.copyfile(ADOPTION.parent / "golden_set.json", tmp_path / "golden_set.json")
    if mutate is None:
        load_adoption_manifest(manifest_copy)
    else:
        with pytest.raises(ValueError):
            load_adoption_manifest(manifest_copy)


def test_adoption_manifest_declares_exact_import_roots() -> None:
    from services.scientific_document.adoption_contract import (
        collect_approved_packages,
        load_adoption_manifest,
    )

    manifest = load_adoption_manifest(ADOPTION)
    roots = collect_approved_packages(manifest)
    assert roots == {"docling_parse", "paddleocr", "paddlex", "paddle"}


def test_gpu_profile_cannot_reuse_cpu_live_evidence() -> None:
    from services.scientific_document.adoption_contract import UpstreamAdoptionManifest

    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    visual = next(
        entry
        for entry in data["entries"]
        if entry["capability"] == "visual_ocr_layout_table_formula"
    )
    gpu = next(profile for profile in visual["runtime_profiles"] if profile["profile_id"] == "gpu")
    gpu.update(
        status="approved",
        probe_evidence="live",
        initialization_completed=True,
        predict_executed=True,
    )
    with pytest.raises(ValidationError):
        UpstreamAdoptionManifest.model_validate(data)


def test_visual_runtime_profile_ids_must_be_unique() -> None:
    from services.scientific_document.adoption_contract import UpstreamAdoptionManifest

    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    visual = next(
        entry
        for entry in data["entries"]
        if entry["capability"] == "visual_ocr_layout_table_formula"
    )
    cpu = next(
        profile for profile in visual["runtime_profiles"] if profile["profile_id"] == "cpu"
    )
    visual["runtime_profiles"].append(json.loads(json.dumps(cpu)))
    with pytest.raises(ValidationError):
        UpstreamAdoptionManifest.model_validate(data)


def test_cpu_live_probe_fixture_is_bound_to_golden_set(tmp_path: Path) -> None:
    import shutil

    from services.scientific_document.adoption_contract import load_adoption_manifest

    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    visual = next(
        entry
        for entry in data["entries"]
        if entry["capability"] == "visual_ocr_layout_table_formula"
    )
    cpu = next(
        profile for profile in visual["runtime_profiles"] if profile["profile_id"] == "cpu"
    )
    golden = json.loads((ADOPTION.parent / "golden_set.json").read_text(encoding="utf-8"))
    golden_entry = next(
        entry for entry in golden["entries"] if entry["entry_id"] == cpu["fixture_id"]
    )
    assert cpu["fixture_sha256"] == golden_entry["content_hash"]

    cpu["fixture_sha256"] = "sha256:" + "1" * 64
    manifest_copy = tmp_path / "upstream_adoption.json"
    manifest_copy.write_text(json.dumps(data), encoding="utf-8")
    shutil.copyfile(ASSETS, tmp_path / "visual_model_assets.json")
    shutil.copyfile(ADOPTION.parent / "golden_set.json", tmp_path / "golden_set.json")
    with pytest.raises(ValueError):
        load_adoption_manifest(manifest_copy)


@pytest.mark.parametrize(
    "manifest_path",
    [ASSETS, ADOPTION],
    ids=["asset-manifest", "adoption-manifest"],
)
def test_manifests_reject_unknown_schema_version(manifest_path: Path) -> None:
    from services.scientific_document.adoption_contract import UpstreamAdoptionManifest
    from services.scientific_document.model_asset_contract import (
        ModelAssetContractError,
        validate_asset_manifest,
    )

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["schema_version"] = "9.9.9"
    if manifest_path == ASSETS:
        with pytest.raises(ModelAssetContractError):
            validate_asset_manifest(data)
    else:
        with pytest.raises(ValidationError):
            UpstreamAdoptionManifest.model_validate(data)
