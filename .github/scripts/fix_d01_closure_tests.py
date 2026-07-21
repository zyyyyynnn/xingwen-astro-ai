from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_PATH = ROOT / "apps" / "api" / "tests" / "test_paper_benchmark.py"

text = TEST_PATH.read_text(encoding="utf-8")

old = '''def test_web_gpt_review_requires_explicit_purpose_and_content_binding() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    payload["review_records"] = ['''
new = '''def test_web_gpt_review_requires_explicit_purpose_and_content_binding() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    payload["review_status"] = "pending_scientific_review"
    payload["review_records"] = ['''
if old not in text:
    raise RuntimeError("technical review fixture anchor not found")
text = text.replace(old, new, 1)

old = '''def test_approved_relation_requires_approved_dependencies() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    relation = next('''
new = '''def test_approved_relation_requires_approved_dependencies() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    payload["review_status"] = "pending_scientific_review"
    payload["review_records"] = []
    for collection_name in (
        "paper_summaries",
        "evidence",
        "claims",
        "relations",
        "reasoning_traces",
    ):
        for item in payload[collection_name]:
            item["review_status"] = "pending_scientific_review"
    relation = next('''
if old not in text:
    raise RuntimeError("approved dependency fixture anchor not found")
text = text.replace(old, new, 1)

old = '''    pending_objects = deepcopy(payload)
    for collection_name in ('''
new = '''    pending_objects = deepcopy(payload)
    pending_objects["review_status"] = "pending_scientific_review"
    pending_objects["review_records"] = []
    for collection_name in ('''
if old not in text:
    raise RuntimeError("scientific hash fixture anchor not found")
text = text.replace(old, new, 1)

TEST_PATH.write_text(text, encoding="utf-8")
