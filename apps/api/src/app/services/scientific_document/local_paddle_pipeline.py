"""Narrow local-bundle visual backend: the official in-process PaddleOCR-VL
pipeline wrapped as the existing ``VisualPageParserPort``.

Governed scope (Scientific Document Parsing Contract): this adapter adds no
second parser framework — it constructs the single adopted official pipeline
(``paddleocr.PaddleOCRVL``, pipeline_version v1.6) exclusively against a
content-addressed bundle that has fully verified against the committed asset
manifest, projects every page into the existing ``VisualPageResult`` shape,
and never lets any raw Paddle object escape this module.
"""

from __future__ import annotations

from pathlib import Path

from services.scientific_document.model_asset_contract import (
    load_asset_manifest,
    verify_model_bundle,
)

from .hybrid_parser import (
    VisualPageBlock,
    VisualPageResult,
    VisualParseError,
    _non_negative_int,
    _positive_int,
    _visual_bbox,
)

_PIPELINE_VERSION = "1.6"


def pinned_visual_model_revision() -> str:
    """The committed HF snapshot revision for the VLM component."""
    manifest = load_asset_manifest()
    for component in manifest["components"]:
        if component["role"] == "vlm_recognition":
            return str(component["revision"])
    raise RuntimeError("asset manifest lacks vlm_recognition component")


class LocalPaddleOcrVlPipeline:
    """Official ``PaddleOCRVL`` bound to a verified immutable model bundle."""

    def __init__(self, *, bundle_root: Path) -> None:
        self._bundle_root = Path(bundle_root).resolve()
        directories = {
            component["role"]: (self._bundle_root / component["role"]).resolve()
            for component in load_asset_manifest()["components"]
        }
        # Fail closed before any vendor import: every committed file must be
        # present with the exact pinned size/hash.
        self._bundle_digest = verify_model_bundle(
            load_asset_manifest(), directories
        )
        self._layout_dir = directories["layout_detection"]
        self._vlm_dir = directories["vlm_recognition"]
        self._engine = None

    @property
    def bundle_digest(self) -> str:
        return self._bundle_digest

    @property
    def engine_version(self) -> str:
        return _PIPELINE_VERSION

    @property
    def model_id(self) -> str:
        return "PaddleOCR-VL-1.6-0.9B"

    @property
    def model_revision(self) -> str:
        return pinned_visual_model_revision()

    def _pipeline(self):
        if self._engine is None:
            try:
                from paddleocr import PaddleOCRVL
            except ImportError as exc:  # pragma: no cover - guarded by caller
                raise VisualParseError(
                    "the approved paddleocr runtime is not installed"
                ) from exc
            self._engine = PaddleOCRVL(
                pipeline_version="v1.6",
                layout_detection_model_name="PP-DocLayoutV3",
                layout_detection_model_dir=str(self._layout_dir),
                vl_rec_model_name=self.model_id,
                vl_rec_model_dir=str(self._vlm_dir),
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_layout_detection=True,
                use_chart_recognition=False,
                use_seal_recognition=False,
                use_ocr_for_image_block=False,
            )
        return self._engine

    def parse_page(self, image_bytes: bytes) -> VisualPageResult:
        import cv2
        import numpy as np

        array = cv2.imdecode(
            np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if array is None:
            raise VisualParseError("visual backend could not decode the page image")
        try:
            results = list(self._pipeline().predict(array))
        except VisualParseError:
            raise
        except Exception as exc:  # noqa: BLE001 - vendor errors are normalized
            raise VisualParseError("local PaddleOCR-VL prediction failed") from exc
        if len(results) != 1:
            raise VisualParseError("local PaddleOCR-VL returned an invalid page count")
        raw = results[0]

        def field(item: object, name: str):
            if isinstance(item, dict) or hasattr(item, "get"):
                return item.get(name)
            return getattr(item, name, None)

        try:
            width = _positive_int(raw["width"], "width")
            height = _positive_int(raw["height"], "height")
            parsing_list = list(raw["parsing_res_list"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VisualParseError(
                "local PaddleOCR-VL returned an unusable page geometry"
            ) from exc
        try:
            blocks = tuple(
                VisualPageBlock(
                    label=str(field(item, "block_label") or "text").strip().lower(),
                    content=(str(field(item, "block_content")).strip() or None)
                    if field(item, "block_content") is not None
                    else None,
                    bbox=_visual_bbox(field(item, "block_bbox"), width, height),
                    order=_non_negative_int(field(item, "block_order"), index),
                )
                for index, item in enumerate(parsing_list)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise VisualParseError(
                "local PaddleOCR-VL returned an unusable page structure"
            ) from exc
        return VisualPageResult(width_pixels=width, height_pixels=height, blocks=blocks)
