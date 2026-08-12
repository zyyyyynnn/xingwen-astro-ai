"""Provision or verify the content-addressed visual document model bundle.

Provisioning is an explicit operator action: it may use the network to fetch
the exact approved upstream revision, materializes every enabled component
under an operator-chosen bundle root, and succeeds only after the complete
immutable bundle verifies against the asset manifest. The production runtime
never invokes this script and never downloads models implicitly.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from services.scientific_document.model_asset_contract import (
    load_asset_manifest,
    verify_model_bundle,
)


def _empty_directory(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise RuntimeError("provisioning target must be absent or empty")
    path.mkdir(parents=True, exist_ok=True)


def _component_directories(bundle_root: Path) -> dict[str, Path]:
    manifest = load_asset_manifest()
    return {
        component["role"]: (bundle_root / component["role"]).resolve()
        for component in manifest["components"]
    }


def provision(bundle_root: Path) -> str:
    """Provision exact official assets into an operator-selected bundle root."""
    manifest = load_asset_manifest()
    directories = _component_directories(bundle_root)
    components = {component["role"]: component for component in manifest["components"]}

    for target in directories.values():
        _empty_directory(target)

    vlm = components["vlm_recognition"]
    source = vlm["official_source"]
    from huggingface_hub import HfApi, snapshot_download

    info = HfApi().model_info(source["repo_id"], revision=vlm["revision"])
    if info.sha != vlm["revision"]:
        raise RuntimeError("Hugging Face resolved revision does not match asset contract")
    snapshot_download(
        repo_id=source["repo_id"],
        revision=vlm["revision"],
        local_dir=directories[vlm["role"]],
        cache_dir=bundle_root / ".provisioning-cache" / "huggingface",
    )
    shutil.rmtree(directories[vlm["role"]] / ".cache", ignore_errors=True)

    cache_home = bundle_root / ".provisioning-cache" / "paddlex"
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache_home)
    os.environ["PADDLE_PDX_MODEL_SOURCE"] = "bos"
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    from paddlex.inference.utils.official_models import official_models

    layout = components["layout_detection"]
    downloaded_layout = Path(official_models.get_model_path(layout["resolved_model_id"]))
    shutil.copytree(
        downloaded_layout,
        directories[layout["role"]],
        dirs_exist_ok=True,
    )
    digest = verify(bundle_root)
    shutil.rmtree(bundle_root / ".provisioning-cache", ignore_errors=True)
    return digest


def verify(bundle_root: Path) -> str:
    manifest = load_asset_manifest()
    return verify_model_bundle(manifest, _component_directories(bundle_root))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("provision", "verify"))
    parser.add_argument("--bundle-root", type=Path, required=True)
    args = parser.parse_args()
    digest = provision(args.bundle_root) if args.mode == "provision" else verify(args.bundle_root)
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
