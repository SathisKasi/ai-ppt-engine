"""
templates/extract_hld_qbr_phase2_render.py — Phase 2 of the HLD QBR asset-tree
build: renders what Phase 1 (extract_hld_qbr_assets.py) could not produce from
the raw zip/XML alone.

PowerPoint's SVG export filter isn't installed on this machine (Slide.Export
with "SVG" fails with "no installed converter supports this file type"), and
there's no LibreOffice either. Instead: use PowerPoint COM only for the one
format it always supports natively — PDF (Presentation.ExportAsFixedFormat) —
then do everything per-slide/per-icon with PyMuPDF (already a project
dependency), which can emit true vector SVG per page and crop precise
high-DPI PNGs via clip rects, no extra converter needed.

Produces:
  layouts/slide_NN.svg          full-slide vector SVG (from the PDF page),
                                 de-sampled afterwards (guidance-sticker text
                                 blanked using the same GUIDANCE_REGEX as the
                                 real builder)
  brand-assets/icons/set_NN_*/  individual icon PNGs cropped out of the icon-
                                 library slides (54-56) — those icons are
                                 vector freeform/group shapes, not embedded
                                 media, so a high-DPI clipped render (via
                                 Phase 1 metadata bounding boxes) is used
                                 instead of a direct per-shape COM export.

Requires: pywin32, a local PowerPoint install, PyMuPDF. Run Phase 1 first
(this script reads templates/hld_qbr_assets/metadata/*.json for icon crop
boxes).

Re-run: python templates/extract_hld_qbr_phase2_render.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

import fitz  # PyMuPDF
import win32com.client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402

ASSETS_DIR = PROJECT_ROOT / "templates" / "hld_qbr_assets"
METADATA_DIR = ASSETS_DIR / "metadata"
LAYOUTS_DIR = ASSETS_DIR / "layouts"
ICONS_DIR = ASSETS_DIR / "brand-assets" / "icons"
PDF_PATH = ASSETS_DIR / "_render_tmp.pdf"

GUIDANCE_REGEX = re.compile(
    r"required content|required slide|\bexample\b|optional \||format option|"
    r"additional slides available|must be updated|formulas in notes",
    re.IGNORECASE,
)

ICON_RENDER_DPI = 360
POINTS_PER_INCH = 72

# (slide_index, folder_name, icon_number_start) for the 3 icon-library slides.
ICON_SLIDES = [
    (54, "set_1_healthcare_coldchain", 1),
    (55, "set_2_supply_chain_logistics", 61),
    (56, "set_3_quality_compliance", 121),
]

NON_ICON_SHAPE_NAMES = {"title", "slide number placeholder"}


def export_pdf() -> None:
    app = win32com.client.gencache.EnsureDispatch("PowerPoint.Application")
    try:
        pres = app.Presentations.Open(
            str(config.HLD_QBR_TEMPLATE_FILE), ReadOnly=True, Untitled=False, WithWindow=False
        )
    except Exception:
        app.Visible = True
        pres = app.Presentations.Open(
            str(config.HLD_QBR_TEMPLATE_FILE), ReadOnly=True, Untitled=False, WithWindow=True
        )
    try:
        pres.ExportAsFixedFormat(
            str(PDF_PATH),
            2,  # ppFixedFormatTypePDF
            1,  # ppFixedFormatIntentScreen
            0,  # msoFalse: FrameSlides
            1,  # ppPrintHandoutVerticalFirst (unused for OutputType below)
            1,  # ppPrintOutputSlides
            0,  # msoFalse: PrintHiddenSlides
            None,  # PrintRange
            1,  # ppPrintAll
        )
    finally:
        pres.Close()
        app.Quit()
    print(f"[pdf] exported presentation -> {PDF_PATH}")


def render_layout_svgs(doc: "fitz.Document") -> None:
    LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(doc):
        # text_as_path=False keeps real <text> elements (needed for de-sampling
        # below, and keeps the SVG smaller/searchable) instead of vector outlines.
        svg_text = page.get_svg_image(text_as_path=False)
        (LAYOUTS_DIR / f"slide_{i:02d}.svg").write_text(svg_text, encoding="utf-8")
    print(f"[layouts] exported {doc.page_count} slide SVGs -> {LAYOUTS_DIR}")


def _is_icon_shape(shape: Dict[str, Any]) -> bool:
    name = (shape.get("name") or "").lower()
    if any(skip in name for skip in NON_ICON_SHAPE_NAMES):
        return False
    return shape.get("shape_type", "").startswith("GROUP") or shape.get("shape_type", "").startswith("FREEFORM")


def crop_icons(doc: "fitz.Document") -> None:
    total = 0
    zoom = ICON_RENDER_DPI / 72  # fitz matrix is relative to the default 72 dpi
    for slide_index, folder_name, start_number in ICON_SLIDES:
        metadata_path = METADATA_DIR / f"slide_{slide_index:02d}.json"
        record = json.loads(metadata_path.read_text(encoding="utf-8"))
        icon_shapes = [s for s in record["shapes"] if _is_icon_shape(s)]
        icon_shapes.sort(key=lambda s: (round(s["position_in"]["top"], 1), s["position_in"]["left"]))

        out_dir = ICONS_DIR / folder_name
        out_dir.mkdir(parents=True, exist_ok=True)
        page = doc[slide_index]
        matrix = fitz.Matrix(zoom, zoom)

        for offset, shape in enumerate(icon_shapes):
            pos = shape["position_in"]
            pad_in = 0.03
            rect = fitz.Rect(
                (pos["left"] - pad_in) * POINTS_PER_INCH,
                (pos["top"] - pad_in) * POINTS_PER_INCH,
                (pos["left"] + pos["width"] + pad_in) * POINTS_PER_INCH,
                (pos["top"] + pos["height"] + pad_in) * POINTS_PER_INCH,
            )
            pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=True)
            icon_number = start_number + offset
            pix.save(out_dir / f"icon_{icon_number:03d}.png")
        total += len(icon_shapes)
        print(f"[icons] cropped {len(icon_shapes)} icons -> {out_dir}")
    print(f"[icons] total icons cropped: {total}")


def _strip_guidance_text(svg_path: Path) -> bool:
    import xml.etree.ElementTree as ET

    tree = ET.parse(svg_path)
    root = tree.getroot()
    changed = False
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag not in ("text", "tspan"):
            continue
        full_text = "".join(elem.itertext())
        if full_text and GUIDANCE_REGEX.search(full_text):
            elem.text = ""
            for child in list(elem):
                elem.remove(child)
            changed = True
    if changed:
        tree.write(svg_path, encoding="utf-8", xml_declaration=True)
    return changed


def de_sample_layout_svgs() -> None:
    svg_files = sorted(LAYOUTS_DIR.glob("slide_*.svg"))
    changed_count = 0
    for svg_path in svg_files:
        try:
            if _strip_guidance_text(svg_path):
                changed_count += 1
        except Exception as exc:
            print(f"[layouts] WARNING: failed to de-sample {svg_path.name}: {exc}")
    print(f"[layouts] de-sampled {changed_count}/{len(svg_files)} SVGs (guidance text blanked)")


def _dir_stats(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"file_count": 0, "total_bytes": 0}
    files = [f for f in path.rglob("*") if f.is_file()]
    return {"file_count": len(files), "total_bytes": sum(f.stat().st_size for f in files)}


def refresh_manifest() -> None:
    manifest_path = ASSETS_DIR / "inventory" / "asset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["folders"]["layouts"] = _dir_stats(LAYOUTS_DIR)
    manifest["folders"]["brand-assets/icons"] = _dir_stats(ICONS_DIR)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[inventory] refreshed asset_manifest.json -> {manifest_path}")


def main() -> None:
    export_pdf()
    doc = fitz.open(str(PDF_PATH))
    try:
        render_layout_svgs(doc)
        crop_icons(doc)
    finally:
        doc.close()
        PDF_PATH.unlink(missing_ok=True)

    de_sample_layout_svgs()
    refresh_manifest()
    print("\nPhase 2 done.")


if __name__ == "__main__":
    main()

