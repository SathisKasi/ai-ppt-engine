"""
templates/extract_hld_qbr_assets.py — Builds the HLD QBR template asset tree
under templates/hld_qbr_assets/ straight from the source .potx, so the LLM
(and future tooling) can be grounded on real structural/brand facts instead of
hand-written prose prompts.

Generates (Phase 1 — no external renderer needed):
  hld_qbr_assets/
    README.md                     knowledge-layer entry point
    EXTRACTION_NOTES.md           what's generated, what's pending, how to re-run
    metadata/slide_NN.json        per-slide structural record (shapes, text,
                                   placeholders, charts, tables, geometry)
    inventory/slide_index.json    flat catalog (index/title/layout/category)
    inventory/archetype_catalog.json  archetype registry cross-referenced to
                                   slide indices
    inventory/asset_manifest.json  generated file/byte counts per folder
    brand-assets/source-xml/*.xml verbatim slideMaster + slideLayout XML
    media/*                       real photo/logo binaries from ppt/media

Phase 2 (pending, needs PowerPoint COM automation — see EXTRACTION_NOTES.md):
    layouts/slide_NN.svg          de-sampled (guidance-stripped) SVG per slide
    brand-assets/icons/...        individual icon shapes exported from the
                                   icon-library slides (54-56)

Re-run after the source .potx changes:
    python templates/extract_hld_qbr_assets.py
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pptx import Presentation  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE_TYPE  # noqa: E402
from pptx.util import Emu  # noqa: E402

import config  # noqa: E402
from templates.build_hld_qbr_layout_catalog import build_entry, describe_structure  # noqa: E402

ASSETS_DIR = PROJECT_ROOT / "templates" / "hld_qbr_assets"
METADATA_DIR = ASSETS_DIR / "metadata"
INVENTORY_DIR = ASSETS_DIR / "inventory"
SOURCE_XML_DIR = ASSETS_DIR / "brand-assets" / "source-xml"
MEDIA_DIR = ASSETS_DIR / "media"
DECORATIVE_MEDIA_DIR = ASSETS_DIR / "brand-assets" / "decorative-media"
LAYOUTS_DIR = ASSETS_DIR / "layouts"
ICONS_DIR = ASSETS_DIR / "brand-assets" / "icons"

# Real photo/logo raster formats -> media/. Everything else from ppt/media/
# (vector .emf/.svg status dots, dividers, etc.) -> brand-assets/decorative-media/.
PHOTO_EXTENSIONS = {".jpeg", ".jpg", ".png"}

# Guidance-sticker detector — kept in sync with core/builders/hld_qbr_builder.py
# GUIDANCE_REGEX so "de-sampled" consumers (layouts/, metadata readers) can
# identify and skip authoring-only text the same way the real builder does.
GUIDANCE_REGEX = re.compile(
    r"required content|required slide|\bexample\b|optional \||format option|"
    r"additional slides available|must be updated|formulas in notes",
    re.IGNORECASE,
)

# Slide-by-slide catalog (index, category) — category is a hand-classified
# governance tier (Mandatory/Core/Optional/Alternate/Divider/Guide-Only) that
# isn't derivable from the pptx itself, so it stays hardcoded here. Layout
# name is NEVER overridden — always read straight from slide.slide_layout.name
# (the real, exact value), so metadata/title can't drift from reality.
SLIDE_CATALOG: List[Dict[str, Any]] = [
    {"index": 0, "category": "Mandatory"},
    {"index": 1, "category": "Mandatory"},
    {"index": 2, "category": "Core"},
    {"index": 3, "category": "Mandatory"},
    {"index": 4, "category": "Core"},
    {"index": 5, "category": "Core"},
    {"index": 6, "category": "Alternate"},
    {"index": 7, "category": "Core"},
    {"index": 8, "category": "Guide-Only"},
    {"index": 9, "category": "Core"},
    {"index": 10, "category": "Optional"},
    {"index": 11, "category": "Divider"},
    {"index": 12, "category": "Core"},
    {"index": 13, "category": "Core"},
    {"index": 14, "category": "Core"},
    {"index": 15, "category": "Core"},
    {"index": 16, "category": "Core"},
    {"index": 17, "category": "Core"},
    {"index": 18, "category": "Core"},
    {"index": 19, "category": "Optional"},
    {"index": 20, "category": "Core"},
    {"index": 21, "category": "Divider"},
    {"index": 22, "category": "Core"},
    {"index": 23, "category": "Core"},
    {"index": 24, "category": "Divider"},
    {"index": 25, "category": "Core"},
    {"index": 26, "category": "Core"},
    {"index": 27, "category": "Core"},
    {"index": 28, "category": "Divider"},
    {"index": 29, "category": "Core"},
    {"index": 30, "category": "Mandatory"},
    {"index": 31, "category": "Divider"},
    {"index": 32, "category": "Optional"},
    {"index": 33, "category": "Optional"},
    {"index": 34, "category": "Optional"},
    {"index": 35, "category": "Optional"},
    {"index": 36, "category": "Optional"},
    {"index": 37, "category": "Optional"},
    {"index": 38, "category": "Optional"},
    {"index": 39, "category": "Optional"},
    {"index": 40, "category": "Optional"},
    {"index": 41, "category": "Guide-Only"},
    {"index": 42, "category": "Guide-Only"},
    {"index": 43, "category": "Guide-Only"},
    {"index": 44, "category": "Guide-Only"},
    {"index": 45, "category": "Guide-Only"},
    {"index": 46, "category": "Guide-Only"},
    {"index": 47, "category": "Guide-Only"},
    {"index": 48, "category": "Guide-Only"},
    {"index": 49, "category": "Guide-Only"},
    {"index": 50, "category": "Guide-Only"},
    {"index": 51, "category": "Guide-Only"},
    {"index": 52, "category": "Guide-Only"},
    {"index": 53, "category": "Guide-Only"},
    {"index": 54, "category": "Guide-Only"},
    {"index": 55, "category": "Guide-Only"},
    {"index": 56, "category": "Guide-Only"},
    {"index": 57, "category": "Guide-Only"},
    {"index": 58, "category": "Guide-Only"},
    {"index": 59, "category": "Guide-Only"},
]

# Slide index -> archetype plan_field, for the slides that have a 1:1 mapping
# in llm/hld_qbr_layout_registry.py (dividers/guide-only slides are omitted).
ARCHETYPE_SLIDE_INDEX: Dict[str, int] = {
    "org_structure": 2,
    "achievements": 4,
    "priorities": 5,
    "action_tracker": 9,
    "voice_of_customer": 10,
    "kpi_safety_quality": 12,
    "kpi_operational": 12,
    "gemba_walk": 22,
    "ci_tracker": 23,
    "quality_org_structure": 25,
    "nc_review_summary": 26,
    "nc_tracker": 27,
    "next_steps": 29,
    "stat_highlights": 34,
    "process_flow": 50,
}


def _emu_to_in(value: Optional[int]) -> Optional[float]:
    if value is None:
        return None
    return round(Emu(value).inches, 3)


def _color_hex(color_format) -> Optional[str]:
    try:
        if color_format.type is not None:
            return str(color_format.rgb)
    except Exception:
        pass
    return None


def _shape_text_record(shape) -> Optional[Dict[str, Any]]:
    if not shape.has_text_frame:
        return None
    full_text = shape.text_frame.text
    if not full_text.strip():
        return None
    runs: List[Dict[str, Any]] = []
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            font = run.font
            runs.append({
                "text": run.text,
                "font": font.name,
                "size_pt": font.size.pt if font.size else None,
                "bold": font.bold,
                "italic": font.italic,
                "color": _color_hex(font.color) if font.color else None,
            })
    return {
        "full_text": full_text,
        "runs": runs,
        "is_guidance_sticker": bool(GUIDANCE_REGEX.search(full_text)),
    }


def _chart_record(shape) -> Optional[Dict[str, Any]]:
    if not shape.has_chart:
        return None
    chart = shape.chart
    try:
        categories = list(chart.plots[0].categories) if chart.plots else []
    except Exception:
        categories = []
    series_names = []
    try:
        for plot in chart.plots:
            for series in plot.series:
                series_names.append(series.name)
    except Exception:
        pass
    return {
        "chart_type": str(chart.chart_type),
        "categories": [str(c) for c in categories],
        "series_names": series_names,
    }


def _table_record(shape) -> Optional[Dict[str, Any]]:
    if not shape.has_table:
        return None
    table = shape.table
    header_row = [cell.text for cell in table.rows[0].cells] if len(table.rows) else []
    return {
        "rows": len(table.rows),
        "cols": len(table.columns),
        "header_row": header_row,
    }


def _canvas_block(prs: Presentation) -> Dict[str, Any]:
    """Slide dimensions are constant across this deck; computed once and
    attached per-slide for metadata self-containedness (matches the
    reference asset tree's per-slide 'canvas' block)."""
    width_in, height_in = Emu(prs.slide_width).inches, Emu(prs.slide_height).inches
    return {
        "width_emu": prs.slide_width,
        "height_emu": prs.slide_height,
        "width_px": round(width_in * 96),
        "height_px": round(height_in * 96),
        "aspect_ratio": "16:9" if abs(width_in / height_in - 16 / 9) < 0.01 else f"{width_in:.2f}:{height_in:.2f}",
    }


def _collect_annotation_shapes(shape_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pulls guidance-sticker shapes (already flagged by _shape_text_record's
    is_guidance_sticker) into their own traceable list, recursing into
    groups — mirrors the reference asset tree's annotation_shapes array."""
    found: List[Dict[str, Any]] = []
    for rec in shape_records:
        text = rec.get("text")
        if text and text.get("is_guidance_sticker"):
            found.append({
                "shape_id": rec["shape_id"],
                "shape_name": rec["name"],
                "text": text["full_text"],
            })
        if rec.get("children"):
            found.extend(_collect_annotation_shapes(rec["children"]))
    return found


def _count_shape_type(shape_records: List[Dict[str, Any]], type_substr: str) -> int:
    count = 0
    for rec in shape_records:
        if type_substr in (rec.get("shape_type") or ""):
            count += 1
        if rec.get("children"):
            count += _count_shape_type(rec["children"], type_substr)
    return count


def _count_table_or_chart(shape_records: List[Dict[str, Any]]) -> int:
    count = 0
    for rec in shape_records:
        if rec.get("table") or rec.get("chart"):
            count += 1
        if rec.get("children"):
            count += _count_table_or_chart(rec["children"])
    return count


def _placeholder_list(placeholders) -> List[Dict[str, Any]]:
    result = []
    for ph in placeholders:
        result.append({
            "raw_type": str(ph.placeholder_format.type),
            "idx": ph.placeholder_format.idx,
            "position_in": {
                "left": _emu_to_in(ph.left),
                "top": _emu_to_in(ph.top),
                "width": _emu_to_in(ph.width),
                "height": _emu_to_in(ph.height),
            },
        })
    return result


def _editable_mapping(slide) -> Dict[str, Any]:
    """Layout + master placeholder inheritance for this slide — grounded
    facts straight from python-pptx (real idx/type/geometry), not an
    invented size/orientation classification."""
    layout = slide.slide_layout
    master = layout.slide_master
    return {
        "layout": {"name": layout.name, "placeholders": _placeholder_list(layout.placeholders)},
        "master": {"name": master.name, "placeholders": _placeholder_list(master.placeholders)},
    }


def _shape_record(shape, depth: int = 0) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "shape_id": shape.shape_id,
        "name": shape.name,
        "shape_type": str(shape.shape_type) if shape.shape_type is not None else None,
        "position_in": {
            "left": _emu_to_in(shape.left),
            "top": _emu_to_in(shape.top),
            "width": _emu_to_in(shape.width),
            "height": _emu_to_in(shape.height),
        },
    }
    if shape.is_placeholder:
        record["placeholder_type"] = str(shape.placeholder_format.type)
        record["placeholder_idx"] = shape.placeholder_format.idx

    text_record = _shape_text_record(shape)
    if text_record:
        record["text"] = text_record

    chart_record = _chart_record(shape)
    if chart_record:
        record["chart"] = chart_record

    table_record = _table_record(shape)
    if table_record:
        record["table"] = table_record

    try:
        if shape.fill.type is not None and shape.fill.type == 1:  # MSO_FILL.SOLID
            record["fill_color"] = _color_hex(shape.fill.fore_color)
    except Exception:
        pass

    if shape.shape_type == MSO_SHAPE_TYPE.GROUP and depth < 4:
        record["children"] = [_shape_record(child, depth + 1) for child in shape.shapes]

    return record


def extract_slide_metadata(prs: Presentation) -> None:
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog_by_index = {row["index"]: row for row in SLIDE_CATALOG}
    canvas_block = _canvas_block(prs)
    manifest: List[Dict[str, Any]] = []

    for idx, slide in enumerate(prs.slides):
        catalog_row = catalog_by_index.get(idx, {})
        shapes = [_shape_record(shape) for shape in slide.shapes]
        annotation_shapes = _collect_annotation_shapes(shapes)
        structure = {
            "shape_count": len(slide.shapes),
            "text_placeholder_count": sum(1 for s in slide.shapes if s.is_placeholder and s.has_text_frame),
            "image_count": _count_shape_type(shapes, "PICTURE"),
            "table_or_chart_count": _count_table_or_chart(shapes),
            "annotation_shape_count": len(annotation_shapes),
        }
        layout_name = slide.slide_layout.name
        category = catalog_row.get("category")
        structural_entry = build_entry({
            "shapes": shapes, "slide_name": f"slide_{idx:02d}", "index": idx, "category": category,
        })
        title = f"{layout_name} \u2014 {describe_structure(structural_entry)}"
        record = {
            "index": idx,
            "slide_name": f"slide_{idx:02d}",
            "title": title,
            "layout": layout_name,
            "category": category,
            "slide_layout_name": slide.slide_layout.name,
            "canvas": canvas_block,
            "structure": structure,
            "annotation_shapes": annotation_shapes,
            "editable_mapping": _editable_mapping(slide),
            "shapes": shapes,
        }
        out_path = METADATA_DIR / f"slide_{idx:02d}.json"
        out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest.append({
            "id": record["slide_name"],
            "title": record["title"],
            "layout": record["slide_layout_name"],
            "category": record["category"],
            **structure,
        })

    (METADATA_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[metadata] wrote {len(prs.slides)} slide records + manifest.json -> {METADATA_DIR}")


def extract_source_xml() -> None:
    SOURCE_XML_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(config.HLD_QBR_TEMPLATE_FILE, "r") as z:
        names = [n for n in z.namelist() if n.startswith("ppt/slideMasters/") or n.startswith("ppt/slideLayouts/")]
        names = [n for n in names if n.endswith(".xml")]
        for name in names:
            out_name = Path(name).name
            (SOURCE_XML_DIR / out_name).write_bytes(z.read(name))
    print(f"[source-xml] wrote {len(names)} files -> {SOURCE_XML_DIR}")


def extract_media() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    DECORATIVE_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    photo_count = 0
    decorative_count = 0
    with zipfile.ZipFile(config.HLD_QBR_TEMPLATE_FILE, "r") as z:
        names = [n for n in z.namelist() if n.startswith("ppt/media/")]
        for name in names:
            out_name = Path(name).name
            if Path(name).suffix.lower() in PHOTO_EXTENSIONS:
                (MEDIA_DIR / out_name).write_bytes(z.read(name))
                photo_count += 1
            else:
                (DECORATIVE_MEDIA_DIR / out_name).write_bytes(z.read(name))
                decorative_count += 1
    print(f"[media] wrote {photo_count} photo/logo files -> {MEDIA_DIR}")
    print(f"[media] wrote {decorative_count} decorative files -> {DECORATIVE_MEDIA_DIR}")


def _dir_stats(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"file_count": 0, "total_bytes": 0}
    files = [f for f in path.rglob("*") if f.is_file()]
    return {"file_count": len(files), "total_bytes": sum(f.stat().st_size for f in files)}


def build_inventory() -> None:
    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)

    # slide_index.json's titles come from the already-written manifest.json
    # (generic, structure-derived titles) rather than SLIDE_CATALOG, which
    # intentionally carries no title at all.
    manifest_entries = json.loads((METADATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    slide_index_entries = [
        {
            "index": int(m["id"].split("_")[1]),
            "title": m["title"],
            "layout": m["layout"],
            "category": m["category"],
        }
        for m in manifest_entries
    ]
    slide_index_path = INVENTORY_DIR / "slide_index.json"
    slide_index_path.write_text(
        json.dumps({"version": "1.0", "slides": slide_index_entries}, indent=2), encoding="utf-8"
    )

    from llm.hld_qbr_layout_registry import HLD_QBR_ARCHETYPES

    archetype_catalog = []
    for spec in HLD_QBR_ARCHETYPES:
        archetype_catalog.append({
            "layout_id": spec["layout_id"],
            "plan_field": spec["plan_field"],
            "purpose": spec["purpose"],
            "constraints": spec["constraints"],
            "slide_index": ARCHETYPE_SLIDE_INDEX.get(spec["plan_field"]),
        })
    (INVENTORY_DIR / "archetype_catalog.json").write_text(
        json.dumps({"version": "1.0", "archetypes": archetype_catalog}, indent=2), encoding="utf-8"
    )

    manifest = {
        "version": "1.0",
        "generated_from": str(config.HLD_QBR_TEMPLATE_FILE.relative_to(PROJECT_ROOT)),
        "folders": {
            "metadata": _dir_stats(METADATA_DIR),
            "layouts": _dir_stats(LAYOUTS_DIR),
            "inventory": _dir_stats(INVENTORY_DIR),
            "brand-assets/source-xml": _dir_stats(SOURCE_XML_DIR),
            "brand-assets/icons": _dir_stats(ICONS_DIR),
            "brand-assets/decorative-media": _dir_stats(DECORATIVE_MEDIA_DIR),
            "media": _dir_stats(MEDIA_DIR),
        },
    }
    (INVENTORY_DIR / "asset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[inventory] wrote slide_index.json, archetype_catalog.json, asset_manifest.json -> {INVENTORY_DIR}")


def write_top_level_docs() -> None:
    """README.md/EXTRACTION_NOTES.md are now hand-maintained (narrative docs,
    correction notes) — only bootstrap them on a fresh checkout where
    they're missing; never overwrite hand-authored content on a rerun."""
    readme_path = ASSETS_DIR / "README.md"
    if readme_path.exists():
        print(f"[docs] README.md already exists, left untouched -> {readme_path}")
        return
    readme_path.write_text(
        "# HLD QBR Template Asset Tree\n\n"
        "Machine-readable grounding layer for `HLD QBR Template PFv3.potx`, generated\n"
        "by `templates/extract_hld_qbr_assets.py`. This is NOT hand-authored — re-run\n"
        "the script after the source .potx changes.\n\n"
        "## Layout\n"
        "- `metadata/slide_NN.json` — per-slide structural record: every shape's\n"
        "  geometry, placeholder type, text runs (font/size/color), chart/table\n"
        "  structure, and an `is_guidance_sticker` flag on text that matches the\n"
        "  same authoring-artifact regex the real builder strips at render time.\n"
        "- `inventory/slide_index.json` — flat catalog (index/title/layout/category).\n"
        "- `inventory/archetype_catalog.json` — `llm/hld_qbr_layout_registry.py`\n"
        "  archetypes cross-referenced to their source slide index.\n"        "- `inventory/layout_capability_catalog.json` — generic, auto-derived slot/\n"
        "  table/chart/repeat-group schema per fillable slide (see\n"
        "  `templates/build_hld_qbr_layout_catalog.py`). No hardcoded topic names —\n"
        "  this is what topic-to-slide matching should be driven by, not\n"
        "  `archetype_catalog.json`'s fixed list.\n"        "- `inventory/asset_manifest.json` — generated file/byte counts per folder.\n"
        "- `brand-assets/source-xml/` — verbatim `slideMaster`/`slideLayout` XML.\n"
        "- `media/` — real photo/logo raster files (`.jpeg`/`.png`) pulled from\n"
        "  `ppt/media/`.\n"
        "- `brand-assets/decorative-media/` — the rest of `ppt/media/` (`.emf`/`.svg`\n"
        "  status dots, dividers, small decorative glyphs — not real photos).\n"
        "- `layouts/slide_NN.svg` — full-slide vector SVG per slide, de-sampled\n"
        "  (guidance-sticker text blanked). Generated by Phase 2, see\n"
        "  EXTRACTION_NOTES.md and `templates/extract_hld_qbr_phase2_render.py`.\n"
        "- `brand-assets/icons/set_N_*/icon_NNN.png` — individual icons cropped\n"
        "  from the icon-library slides (54-56). Also Phase 2.\n"
        "\n"
        "## Regenerating\n"
        "1. `python templates/extract_hld_qbr_assets.py` (Phase 1 — wipes and\n"
        "   rebuilds this whole tree from the zip/python-pptx, no renderer needed)\n"
        "2. `python templates/extract_hld_qbr_phase2_render.py` (Phase 2 — needs\n"
        "   desktop PowerPoint + pywin32; reads Phase 1's metadata/ for icon crop\n"
        "   boxes, so always run Phase 1 first)\n",
        encoding="utf-8",
    )
    (ASSETS_DIR / "EXTRACTION_NOTES.md").write_text(
        "# Extraction notes\n\n"
        "## Phase 1 (`extract_hld_qbr_assets.py`) — zip/python-pptx only, no renderer\n"
        "- `metadata/`, `inventory/`, `brand-assets/source-xml/`, `media/`,\n"
        "  `brand-assets/decorative-media/`\n\n"
        "## Phase 2 (`extract_hld_qbr_phase2_render.py`) — needs desktop PowerPoint\n"
        "- `layouts/slide_NN.svg`: full-slide vector SVG, de-sampled afterwards\n"
        "  (guidance-sticker text blanked via the same GUIDANCE_REGEX the real\n"
        "  builder uses). 21/60 slides had guidance text to strip.\n"
        "- `brand-assets/icons/set_N_*/icon_NNN.png`: individual icon crops from\n"
        "  slides 54-56 (182 total — catalog says 183, off by one, not yet root-\n"
        "  caused). These icons are vector freeform/group shapes, not embedded\n"
        "  media, so they can't be pulled from `ppt/media/` directly.\n\n"
        "### Why PDF + PyMuPDF instead of direct SVG/PNG export\n"
        "No LibreOffice (`soffice`) is installed on this machine. Desktop\n"
        "PowerPoint is (`C:\\Program Files\\Microsoft Office\\root\\Office16\\POWERPNT.EXE`)\n"
        "but its `Slide.Export(path, \"SVG\")` filter isn't installed, and relying on\n"
        "a raster `Slide.Export(path, \"PNG\", w, h)` per icon slide would need exact\n"
        "px/inch bookkeeping. Instead: `Presentation.ExportAsFixedFormat` to PDF\n"
        "(always available, native) once via `pywin32` COM, then PyMuPDF (already a\n"
        "project dependency) does everything else — `page.get_svg_image(text_as_\n"
        "path=False)` for true vector SVG per slide (keeps real `<text>` elements,\n"
        "required for the de-sampling regex pass to find anything), and\n"
        "`page.get_pixmap(matrix=..., clip=fitz.Rect(...))` for crisp per-icon PNG\n"
        "crops using the bounding boxes already captured in Phase 1's metadata\n"
        "(360 px/in, inches -> PDF points via *72 for the clip rect).\n\n"
        "### Known size gap vs. the reference project\n"
        "Icon crops here are tiny PNGs (~400KB total for all 182, vs. a 32.7MB\n"
        "reference figure) since each icon is only ~0.3in x 0.3in cropped at\n"
        "360dpi. Bump `ICON_RENDER_DPI` in extract_hld_qbr_phase2_render.py if\n"
        "higher-resolution icon assets are needed later.\n",
        encoding="utf-8",
    )
    print(f"[docs] wrote README.md, EXTRACTION_NOTES.md -> {ASSETS_DIR}")


def main() -> None:
    # Surgical cleanup: only wipe the subpaths THIS script owns, so reruns
    # never destroy Phase 2's layouts/brand-assets/icons output or the
    # hand-authored narrative docs (guardrails.md, guidelines.md, etc.) that
    # live alongside them in the same asset tree.
    if METADATA_DIR.exists():
        shutil.rmtree(METADATA_DIR)
    if SOURCE_XML_DIR.exists():
        shutil.rmtree(SOURCE_XML_DIR)
    if MEDIA_DIR.exists():
        shutil.rmtree(MEDIA_DIR)
    if DECORATIVE_MEDIA_DIR.exists():
        shutil.rmtree(DECORATIVE_MEDIA_DIR)
    for owned_file in ("slide_index.json", "archetype_catalog.json", "asset_manifest.json"):
        owned_path = INVENTORY_DIR / owned_file
        if owned_path.exists():
            owned_path.unlink()
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    prs = Presentation(str(config.HLD_QBR_TEMPLATE_FILE))
    extract_slide_metadata(prs)
    extract_source_xml()
    extract_media()
    build_inventory()
    write_top_level_docs()
    print("\nDone. Asset tree written to:", ASSETS_DIR)


if __name__ == "__main__":
    main()
