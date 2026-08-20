from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from PIL import Image

from app.schemas.core import ScientificSkillId
from app.workflow.scientific_inputs import _content_parameters


def _image_dataset_bytes() -> bytes:
    images: list[dict[str, str]] = []
    content: dict[str, bytes] = {}
    for index in range(10):
        path = f"images/sample-{index:02d}.png"
        images.append({"path": path, "label": "galaxy" if index < 5 else "star"})
        image = BytesIO()
        Image.new("RGB", (8, 6), color=(index * 10, 20, 30)).save(
            image, format="PNG"
        )
        content[path] = image.getvalue()
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "labels.json",
            json.dumps({"schema_version": "1.0.0", "images": images}).encode(),
        )
        for path, value in content.items():
            archive.writestr(path, value)
    return output.getvalue()


def test_csv_research_input_becomes_bounded_typed_rows() -> None:
    parameters = _content_parameters(
        ScientificSkillId.clustering_analysis,
        "row_id,x,y,label\r\na,1,2.5,star\r\nb,,3,galaxy\r\n".encode(),
        input_type="csv",
    )

    assert parameters == {
        "rows": [
            {"row_id": "a", "x": 1, "y": 2.5, "label": "star"},
            {"row_id": "b", "x": None, "y": 3, "label": "galaxy"},
        ]
    }


def test_csv_research_input_rejects_ambiguous_or_overwide_rows() -> None:
    with pytest.raises(ValueError, match="unique non-empty"):
        _content_parameters(
            ScientificSkillId.data_profile,
            b"x,x\n1,2\n",
            input_type="csv",
        )
    with pytest.raises(ValueError, match="more cells"):
        _content_parameters(
            ScientificSkillId.data_profile,
            b"x,y\n1,2,3\n",
            input_type="csv",
        )


def test_json_rows_and_astronomical_series_use_their_declared_shapes() -> None:
    rows = _content_parameters(
        ScientificSkillId.anomaly_detection,
        json.dumps({"rows": [{"row_id": "a", "flux": 1.2}]}).encode(),
        input_type="json",
    )
    spectrum = _content_parameters(
        ScientificSkillId.spectrum_analysis,
        json.dumps(
            {
                "object_name": "HD 189733",
                "wavelength": [500.0, 501.0],
                "flux": [1.0, 0.9],
            }
        ).encode(),
        input_type="json",
    )

    assert rows == {"rows": [{"row_id": "a", "flux": 1.2}]}
    assert spectrum["object_name"] == "HD 189733"
    assert "rows" not in spectrum


def test_row_skill_rejects_an_undeclared_input_format() -> None:
    with pytest.raises(ValueError, match="CSV, XLSX, Parquet or JSON"):
        _content_parameters(
            ScientificSkillId.statistical_analysis,
            b"not a table",
            input_type="text",
        )


def test_image_classification_accepts_only_a_resolved_image_dataset() -> None:
    parameters = _content_parameters(
        ScientificSkillId.image_classification,
        _image_dataset_bytes(),
        input_type="image_dataset",
    )

    assert parameters["image_shape"] == [32, 32, 3]
    assert parameters["image_count"] == 10
    with pytest.raises(ValueError, match="requires an image_dataset"):
        _content_parameters(
            ScientificSkillId.image_classification,
            json.dumps({"images": []}).encode(),
            input_type="json",
        )
