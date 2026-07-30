from pathlib import Path

path = Path("apps/api/tests/test_supplemental_source_pipeline.py")
text = path.read_text(encoding="utf-8")
old = '''        page_size=2,\n        max_pages=2,\n        record_limit=3,\n    )\n    first_page = ['''
new = '''        page_size=2,\n        max_pages=2,\n        record_limit=4,\n    )\n    first_page = ['''
if text.count(old) != 1:
    raise SystemExit("expected completion-test pagination block exactly once")
path.write_text(text.replace(old, new), encoding="utf-8")
