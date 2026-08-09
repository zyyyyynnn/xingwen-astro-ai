"""Build the Scientific Document Parsing Contract Golden Set manifest (reproducible, license-governed).

Produces ``golden_set.json`` describing 15-20 ``exoplanet_host_star`` entries.
Ten legal synthetic fixtures are committed and content-hashed. Six real papers
are represented as local-only records with genuine arXiv identifiers; their PDFs
are not committed or fetched by CI.

A local-only entry with ``content_hash=None`` is explicitly *not exact-byte
verified in this checkout*. Such an entry may keep metadata/abstract-level
anchors, but MUST NOT claim PDF page count or page/block/cell locator ground
truth until the exact local PDF is acquired and hashed.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.scientific_document_benchmark import (
    BenchmarkDataType,
    GoldenExpectedAnnotation,
    GoldenSetEntry,
    GoldenSetManifest,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
MANIFEST_PATH = Path(__file__).resolve().parent / "golden_set.json"

_FIXTURE_SPECS: list[tuple[str, str, tuple[str, ...], GoldenExpectedAnnotation]] = [
    (
        "born_digital",
        "Exoplanet Host-Star Integration Study",
        ("born-digital", "paragraph", "reading-order"),
        GoldenExpectedAnnotation(
            expected_page_count=1,
            critical_headings=("Exoplanet Host-Star Integration Study",),
            selected_paragraph_block_ids=("p1-w0001", "p1-w0002"),
            selected_reading_order=("p1-w0001", "p1-w0002"),
            selected_scientific_values=(
                "period=2.1 d",
                "radius=1.3 R_earth",
                "Teff=5200 K",
            ),
        ),
    ),
    (
        "two_column",
        "Two-Column Hot-Jupiter Survey",
        ("two-column", "reading-order"),
        GoldenExpectedAnnotation(
            expected_page_count=1,
            critical_headings=("Two-Column Hot-Jupiter Survey",),
            selected_scientific_values=(
                "Teff=5000-6200 K",
                "metallicity=-0.2..0.3 dex",
            ),
        ),
    ),
    (
        "simple_table",
        "Sample Planet Parameters",
        ("table", "simple-table"),
        GoldenExpectedAnnotation(
            expected_page_count=1,
            critical_headings=(
                "Sample Planet Parameters",
                "Table 1. Sample planet parameters",
            ),
            selected_tables=("tbl-simple",),
            selected_cells=("simple-r0c0", "simple-r1c1", "simple-r2c2"),
        ),
    ),
    (
        "complex_table",
        "Stellar Parameters With Merged Header",
        ("table", "complex-table", "spans"),
        GoldenExpectedAnnotation(
            expected_page_count=1,
            critical_headings=(
                "Stellar Parameters With Merged Header",
                "Table 2. Merged-header parameter table",
            ),
            selected_tables=("tbl-complex",),
        ),
    ),
    (
        "cross_page_table",
        "Cross-Page Table (split)",
        ("table", "cross-page", "partial"),
        GoldenExpectedAnnotation(
            expected_page_count=2,
            critical_headings=(
                "Cross-Page Table (Part 1)",
                "Cross-Page Table (page 2 of 2)",
            ),
            selected_tables=("tbl-cross",),
        ),
    ),
    (
        "formula",
        "Orbital Mechanics Relations",
        ("formula",),
        GoldenExpectedAnnotation(
            expected_page_count=1,
            critical_headings=("Orbital Mechanics Relations",),
            selected_formulas=("fml-kepler",),
            selected_scientific_values=("P^2 = (4 pi^2 a^3)/(G M)",),
        ),
    ),
    (
        "figure_caption",
        "Radius-Period Distribution",
        ("figure", "caption"),
        GoldenExpectedAnnotation(
            expected_page_count=1,
            critical_headings=("Radius-Period Distribution",),
            selected_figure_caption_links=("fig-1",),
        ),
    ),
    (
        "mixed",
        "Mixed Text and Figure Layout",
        ("mixed", "figure", "caption"),
        GoldenExpectedAnnotation(
            expected_page_count=1,
            critical_headings=("Mixed Text and Figure Layout",),
            selected_figure_caption_links=("fig-2",),
        ),
    ),
    (
        "scanned_like",
        "Archived Observation Note",
        ("scanned-like", "low-quality"),
        GoldenExpectedAnnotation(expected_page_count=1),
    ),
    (
        "low_quality",
        "Preliminary Reduction",
        ("low-quality", "partial"),
        GoldenExpectedAnnotation(
            expected_page_count=1,
            critical_headings=("Preliminary Reduction",),
            selected_scientific_values=("Teff~5500 K",),
        ),
    ),
]

# Real local-only publications. Titles/selected values are metadata/abstract-level
# anchors from the cited arXiv records. No page count/locator annotation is
# claimed until exact local PDF bytes are acquired and content-hashed.
_RESTRICTED_SPECS: list[
    tuple[str, str, tuple[str, ...], str, str, GoldenExpectedAnnotation]
] = [
    (
        "real_trappist1",
        "Seven temperate terrestrial planets around the nearby ultracool dwarf star TRAPPIST-1",
        ("born-digital", "table", "formula", "multi-planet"),
        "arXiv:1703.01424",
        "arXiv record 1703.01424; Nature 542, 456-460 (2017); PDF not redistributed, local-only/not-exact-byte-verified",
        GoldenExpectedAnnotation(
            critical_headings=(
                "Seven temperate terrestrial planets around the nearby ultracool dwarf star TRAPPIST-1",
            ),
            selected_scientific_values=(
                "P=1.51 d",
                "P=2.42 d",
                "P=4.04 d",
                "P=6.06 d",
                "P=9.21 d",
                "P=12.35 d",
            ),
        ),
    ),
    (
        "real_kepler101",
        "Characterization of the Kepler-101 planetary system with HARPS-N",
        ("born-digital", "table", "radial-velocity"),
        "arXiv:1409.4592",
        "arXiv record 1409.4592; A&A 572, A2 (2014); PDF not redistributed, local-only/not-exact-byte-verified",
        GoldenExpectedAnnotation(
            critical_headings=(
                "Characterization of the Kepler-101 planetary system with HARPS-N",
            ),
            selected_scientific_values=(
                "P_b=3.49 d",
                "R_b=5.77 R_earth",
                "P_c=6.03 d",
                "R_c=1.25 R_earth",
            ),
        ),
    ),
    (
        "real_koi142",
        "KOI-142, the King of Transit Variations, is a Pair of Planets near the 2:1 Resonance",
        ("born-digital", "timing", "near-resonance"),
        "arXiv:1304.4283",
        "arXiv record 1304.4283; ApJ 777, 3 (2013); PDF not redistributed, local-only/not-exact-byte-verified",
        GoldenExpectedAnnotation(
            critical_headings=(
                "KOI-142, the King of Transit Variations, is a Pair of Planets near the 2:1 Resonance",
            ),
            selected_scientific_values=("P_c/P_b=2.03", "M_c=0.7 M_Jup"),
        ),
    ),
    (
        "real_kepler10c",
        "Kepler-10c, a 2.2-Earth radius transiting planet in a multiple system",
        ("born-digital", "validation"),
        "arXiv:1105.4647",
        "arXiv record 1105.4647; ApJS 197, 5 (2011); PDF not redistributed, local-only/not-exact-byte-verified",
        GoldenExpectedAnnotation(
            critical_headings=(
                "Kepler-10c, a 2.2-Earth radius transiting planet in a multiple system",
            ),
            selected_scientific_values=("R_p=2.227 R_earth",),
        ),
    ),
    (
        "real_k2_33b",
        "A short-period planet orbiting a pre-main-sequence star in Upper Scorpius",
        ("born-digital", "young-star"),
        "arXiv:1604.06165",
        "arXiv record 1604.06165; AJ 152, 61 (2016); PDF not redistributed, local-only/not-exact-byte-verified",
        GoldenExpectedAnnotation(
            critical_headings=(
                "A short-period planet orbiting a pre-main-sequence star in Upper Scorpius",
            ),
            selected_scientific_values=(
                "P_orb=5.425 d",
                "R_p=5.04 R_earth",
                "age~11 Myr",
            ),
        ),
    ),
    (
        "real_kepler_phasecurves",
        "Kepler phase curves and secondary eclipses -- temperatures and albedos of confirmed Kepler giant planets",
        ("born-digital", "phase-curve", "albedo"),
        "arXiv:1404.4348",
        "arXiv record 1404.4348; PASP (2015); PDF not redistributed, local-only/not-exact-byte-verified",
        GoldenExpectedAnnotation(
            critical_headings=(
                "A comprehensive study of Kepler phase curves and secondary eclipses -- temperatures and albedos of confirmed Kepler giant planets",
            ),
            selected_scientific_values=("albedo<0.1 (most)", "R_p>4 R_earth"),
        ),
    ),
]


def _content_hash_of_pdf(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest() -> GoldenSetManifest:
    entries: list[GoldenSetEntry] = []
    for key, title, tags, expected in _FIXTURE_SPECS:
        pdf = FIXTURES_DIR / f"golden_{key}.pdf"
        entries.append(
            GoldenSetEntry(
                entry_id=f"gs-{key}",
                case_key="exoplanet_host_star",
                title=title,
                data_type=BenchmarkDataType.fixture,
                source="synthetic-fixture",
                license_note="CC0 synthetic; generated by repo tooling, no third-party copyright",
                content_hash=_content_hash_of_pdf(pdf) if pdf.is_file() else None,
                availability="committed-fixture",
                local_only=False,
                coverage_tags=tags,
                expected=expected,
            )
        )

    for key, title, tags, identifier, license_note, expected in _RESTRICTED_SPECS:
        entries.append(
            GoldenSetEntry(
                entry_id=f"gs-{key}",
                case_key="exoplanet_host_star",
                title=title,
                data_type=BenchmarkDataType.golden,
                source="restricted-publication",
                doi_or_identifier=identifier,
                license_note=license_note,
                content_hash=None,
                availability="local-only",
                local_only=True,
                coverage_tags=tags,
                expected=expected,
            )
        )

    manifest = GoldenSetManifest(
        manifest_id="scientific_document-golden-set",
        version="1.1.0",
        case_key="exoplanet_host_star",
        generated_at=datetime.now(timezone.utc).replace(microsecond=0),
        sample_count=len(entries),
        entries=tuple(entries),
    )
    GoldenSetManifest.model_validate(manifest.model_dump(mode="json"))
    return manifest


def main() -> int:
    manifest = build_manifest()
    MANIFEST_PATH.write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {MANIFEST_PATH} with {manifest.sample_count} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
