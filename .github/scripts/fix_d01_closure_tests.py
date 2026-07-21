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
TEST_PATH.write_text(text.replace(old, new, 1), encoding="utf-8")
