# Scientific document fixtures

This directory stores a small, curated set of openly licensed research papers used by real parser and browser integration tests. These files are product test assets: tests send the original document through the production ResearchInput, DocumentParse, PaperSummary, Evidence, Revision, and Share paths.

Each paper must have a neighboring metadata file recording its citation, stable public source, license, retrieval date, and the exact capability it exercises. Keep only documents that add a stable, non-duplicated acceptance signal; do not use this directory as a general paper archive.

The curated set currently contains two complementary CC BY 4.0 assets:

- The Cadieux page-14 fixture includes the original Table 5 PDF excerpt, a high-resolution research-document image, and a real PaddleOCR-VL 1.6 recorded response. Browser integration replays that response through the production HTTP visual client as `source_mode=fixture` and `data_level=recorded_response`; tracked benchmark evidence separately proves live local-bundle execution. Together they verify visual routing, transposed scientific-table recovery, data admission, literature reasoning, revision, locator closure, and Artifact publication without repeatedly running the CPU model.
- `kunimoto-2022-tess-faint-star-search.pdf` is a complete paper retained for native PDF and longer-document regression coverage.
