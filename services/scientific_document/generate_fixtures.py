"""Generate the Scientific Document Parsing Contract Golden Set fixture PDFs (legal, synthetic, commit-safe).

Every file here is a SYNTHETIC exoplanet_host_star-style document generated
from scratch — none is a copyrighted paper. These fixtures cover the Scientific Document Parsing Contract
Golden Set dimensions and are committed so CI can run the native parser and
golden annotations without network access or restricted content.

Coverage dimensions defined by the Scientific Document Parsing Contract:
- born-digital, two-column, reading order, plain paragraph
- simple table, complex table (spans), cross-page table (split => partial)
- formula, figure+caption, mixed text+image, scanned page, low-quality page

The ``scanned`` fixture is generated as a real raster image (PIL) embedded into
the PDF with NO text layer, so the native born-digital parser legitimately finds
no extractable text. This is the honest way to test "native-only must not fake
accepted on scanned input".
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - fixture tooling dependency
    Image = ImageDraw = ImageFont = None


def _new_page(pdf: FPDF, title: str) -> None:
    pdf.add_page()
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 15)
    pdf.multi_cell(0, 9, title)
    pdf.ln(2)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 11)


def _paragraph(pdf: FPDF, text: str) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, text)
    pdf.ln(1)


def build_born_digital(path: Path) -> None:
    pdf = FPDF()
    _new_page(pdf, "Exoplanet Host-Star Integration Study")
    _paragraph(
        pdf,
        "We integrate hot-Jupiter candidates with host-star parameters to test "
        "orbital-period and radius correlations across the sample.",
    )
    _paragraph(
        pdf,
        "The TOI-1234 system shows a 2.1 day orbital period and a planet radius "
        "of 1.3 Earth radii around a 5200 K host star.",
    )
    _save(pdf, path)


def build_two_column(path: Path) -> None:
    pdf = FPDF()
    _new_page(pdf, "Two-Column Hot-Jupiter Survey")
    pdf.set_font("Helvetica", "", 10)
    left = (
        "Column A: We measured 42 exoplanet host stars. Most have effective "
        "temperatures between 5000 K and 6200 K. The metallicity spans -0.2 to 0.3 dex."
    )
    right = (
        "Column B: Radii cluster near 1.2 R_earth. Orbital periods range from "
        "1.4 to 12.6 days. No strong correlation with stellar mass was found."
    )
    pdf.multi_cell(90, 5, left, border=0)
    pdf.set_xy(105, pdf.get_y() - 30)
    pdf.multi_cell(90, 5, right, border=0)
    _save(pdf, path)


def build_simple_table(path: Path) -> None:
    pdf = FPDF()
    _new_page(pdf, "Sample Planet Parameters")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Table 1. Sample planet parameters", ln=1)
    pdf.set_font("Helvetica", "", 10)
    rows = [
        ("Object", "Period (d)", "Radius (R_e)", "Teff (K)"),
        ("TOI-1234 b", "2.1", "1.3", "5200"),
        ("TOI-5678 c", "4.8", "2.4", "5800"),
    ]
    for row in rows:
        for cell in row:
            pdf.cell(42, 7, cell, border=1)
        pdf.ln(7)
    _save(pdf, path)


def build_complex_table(path: Path) -> None:
    pdf = FPDF()
    _new_page(pdf, "Stellar Parameters With Merged Header")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Table 2. Merged-header parameter table", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(84, 7, "Host Star", border=1, align="C")
    pdf.cell(42, 7, "Planet", border=1, align="C")
    pdf.ln(7)
    for row in [("Name", "Teff (K)"), ("TOI-99", "5600"), ("TOI-100", "6100")]:
        for cell in row:
            pdf.cell(42, 7, cell, border=1)
        pdf.ln(7)
    _save(pdf, path)


def build_cross_page_table(path: Path) -> None:
    pdf = FPDF()
    _new_page(pdf, "Cross-Page Table (Part 1)")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Table 3. Long parameter table (page 1 of 2)", ln=1)
    pdf.set_font("Helvetica", "", 10)
    for i in range(1, 16):
        pdf.cell(42, 7, f"row-{i}", border=1)
        pdf.cell(42, 7, f"{(i * 1.3):.1f}", border=1)
        pdf.ln(7)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Table 3. Long parameter table (page 2 of 2)", ln=1)
    pdf.set_font("Helvetica", "", 10)
    for i in range(16, 28):
        pdf.cell(42, 7, f"row-{i}", border=1)
        pdf.cell(42, 7, f"{(i * 1.3):.1f}", border=1)
        pdf.ln(7)
    _save(pdf, path)


def build_formula(path: Path) -> None:
    pdf = FPDF()
    _new_page(pdf, "Orbital Mechanics Relations")
    _paragraph(
        pdf,
        "The orbital period follows Kepler's third law. For a circular orbit the "
        "equilibrium temperature is approximated by:",
    )
    pdf.set_font("Courier", "", 12)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 7, "P^2 = (4 pi^2 a^3) / (G (M_star + M_p))")
    pdf.set_font("Helvetica", "", 11)
    _paragraph(
        pdf,
        "where P is the period, a the semi-major axis, and M_star the host mass.",
    )
    _save(pdf, path)


def build_figure_caption(path: Path) -> None:
    pdf = FPDF()
    _new_page(pdf, "Radius-Period Distribution")
    pdf.rect(20, 40, 120, 70)
    pdf.set_xy(20, 115)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "I", 10)
    pdf.multi_cell(
        0,
        5,
        "Figure 1. Radius versus orbital period for 42 host-star systems. "
        "Symbols mark confirmed planets.",
    )
    _save(pdf, path)


def build_mixed(path: Path) -> None:
    pdf = FPDF()
    _new_page(pdf, "Mixed Text and Figure Layout")
    _paragraph(
        pdf,
        "The sample combines transit and radial-velocity detections. Figure 2 "
        "summarizes the mass-radius relation.",
    )
    pdf.rect(20, 50, 100, 50)
    pdf.set_xy(20, 105)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "I", 10)
    pdf.multi_cell(0, 5, "Figure 2. Mass-radius diagram with theoretical tracks.")
    _save(pdf, path)


def build_scanned_like(path: Path) -> None:
    """Genuine scanned fixture: a raster image embedded with NO text layer.

    The page text is drawn into a PIL image and embedded; the PDF therefore has
    no extractable text layer, so native born-digital parsing legitimately yields
    no blocks. This tests that native-only does not fabricate acceptance.
    """
    if Image is None:  # pragma: no cover - fixture tooling dependency
        raise RuntimeError("pillow is required to build the scanned fixture")
    width, height = 595, 842  # A4 @ ~72 dpi
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
    except Exception:  # pragma: no cover - font fallback
        font = ImageFont.load_default()
    lines = [
        "Archived Observation Note",
        "",
        "Archived observation log: host star brightness varied by 0.02 mag",
        "over the monitored window; period estimated near 3.5 days.",
        "Photometric scatter consistent with instrumental noise.",
        "No calibrated photometry in this scan.",
    ]
    y = 60
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += 28
    tmp = path.with_suffix(".png")
    img.save(tmp)
    pdf = FPDF()
    pdf.add_page()
    pdf.image(str(tmp), x=0, y=0, w=210)  # A4 width in mm
    _save(pdf, path)
    tmp.unlink(missing_ok=True)


def build_low_quality(path: Path) -> None:
    pdf = FPDF()
    _new_page(pdf, "Preliminary Reduction")
    pdf.set_font("Helvetica", "", 8)
    _paragraph(
        pdf,
        "Low-quality reduction: some entries unreadable; we report only verified "
        "values. Host temperature approximately 5500 K.",
    )
    _save(pdf, path)


def build_scientific_table_image(path: Path) -> None:
    """Build a document-like raster table for the governed visual path."""
    if Image is None:  # pragma: no cover - fixture tooling dependency
        raise RuntimeError("pillow is required to build the visual table fixture")
    image = Image.new("RGB", (1800, 1200), "white")
    draw = ImageDraw.Draw(image)

    def font(name: str, size: int):
        dejavu_name = {
            "arial.ttf": "DejaVuSans.ttf",
            "arialbd.ttf": "DejaVuSans-Bold.ttf",
        }[name]
        candidates = (name, dejavu_name)
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        return ImageFont.load_default()

    body = font("arial.ttf", 46)
    bold = font("arialbd.ttf", 50)
    title = font("arialbd.ttf", 64)
    draw.text((100, 70), "Scientific Host-Star Measurements", fill="black", font=title)
    draw.text(
        (100, 165),
        "Table 1. Adjudicated stellar parameters",
        fill="black",
        font=body,
    )
    x_positions = (100, 600, 1150, 1700)
    y_positions = (270, 430, 590, 750)
    for x_position in x_positions:
        draw.line(
            (x_position, y_positions[0], x_position, y_positions[-1]),
            fill="black",
            width=6,
        )
    for y_position in y_positions:
        draw.line(
            (x_positions[0], y_position, x_positions[-1], y_position),
            fill="black",
            width=6,
        )
    for column, text in enumerate(("star.tic_id", "Teff [K]", "star.radius [R_sun]")):
        draw.text(
            (x_positions[column] + 24, y_positions[0] + 45),
            text,
            fill="black",
            font=bold,
        )
    for row_index, row in enumerate(
        (("TIC 101", "5200", "0.80"), ("TIC 102", "6100", "1.10")),
        start=1,
    ):
        for column, text in enumerate(row):
            draw.text(
                (x_positions[column] + 24, y_positions[row_index] + 45),
                text,
                fill="black",
                font=body,
            )
    draw.text(
        (100, 870),
        "Values are reported for the observed exoplanet host stars.",
        fill="black",
        font=body,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False)


def _save(pdf: FPDF, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


BUILDERS = {
    "born_digital": build_born_digital,
    "two_column": build_two_column,
    "simple_table": build_simple_table,
    "complex_table": build_complex_table,
    "cross_page_table": build_cross_page_table,
    "formula": build_formula,
    "figure_caption": build_figure_caption,
    "mixed": build_mixed,
    "scanned_like": build_scanned_like,
    "low_quality": build_low_quality,
}


def build_all(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for key, builder in BUILDERS.items():
        path = out_dir / f"golden_{key}.pdf"
        builder(path)
        paths.append(path)
    visual_table = out_dir / "scientific_host_star_table.png"
    build_scientific_table_image(visual_table)
    paths.append(visual_table)
    return paths


if __name__ == "__main__":
    import sys

    target = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("services/scientific_document/fixtures")
    )
    built = build_all(target)
    for p in built:
        print(p)
