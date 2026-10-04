"""
templates/build_hld_qbr_layout_catalog.py — Builds a generic, auto-derived
"layout capability catalog" for the HLD QBR template from
templates/hld_qbr_assets/metadata/*.json (see templates/extract_hld_qbr_assets.py).

This is the data-driven replacement for llm/hld_qbr_layout_registry.py's
hardcoded HLD_QBR_ARCHETYPES list: instead of hand-naming 15 fixed topics
(org_structure, gemba_walk, nc_tracker, ...) that the LLM must try to fill,
this catalog describes each fillable template slide purely by its STRUCTURE
(slots, maxChars, table/chart schema, repeated card/badge groups) with no
notion of what document topic should go there. Topic-to-slide matching
becomes a runtime LLM decision (outline-assignment stage), not a fixed
pre-named bucket.

Only Mandatory/Core/Optional/Alternate slides are included (content-bearing).
Divider/Guide-Only slides are excluded — dividers are structural and
self-gate on neighboring content at render time, guide-only slides are
brand-guideline appendix pages never emitted in a generated deck.

Run after templates/extract_hld_qbr_assets.py (reads its metadata/ output).
Writes: templates/hld_qbr_assets/inventory/layout_capability_catalog.json

Re-run: python templates/build_hld_qbr_layout_catalog.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "templates" / "hld_qbr_assets"
METADATA_DIR = ASSETS_DIR / "metadata"
INVENTORY_DIR = ASSETS_DIR / "inventory"
OUT_PATH = INVENTORY_DIR / "layout_capability_catalog.json"

# Divider/Guide-Only slides are structural or appendix-only, never content targets.
EXCLUDED_CATEGORIES = {"Divider", "Guide-Only"}

CHROME_NAME_SNIPPETS = ("slide number placeholder",)

# Repeated-card/badge detection tolerance: sibling GROUP shapes are treated as
# one repeating pattern if their heights are within this fraction of each other.
HEIGHT_TOLERANCE = 0.12


def _max_chars(sample_text: str) -> int:
    length = len(sample_text.strip())
    if length == 0:
        return 20
    return max(15, int(math.ceil(length * 1.3 / 5.0) * 5))


def _is_chrome(shape: Dict[str, Any]) -> bool:
    name = (shape.get("name") or "").lower()
    return any(snippet in name for snippet in CHROME_NAME_SNIPPETS)


def _is_auto_number(shape: Dict[str, Any]) -> bool:
    """Sequence-badge shapes (e.g. '1', '2', '3' next to achievement
    milestones) — purely positional decoration, not real content the LLM
    should independently invent text for. Detected generically (short,
    purely numeric sample text), not by any slide-specific name."""
    text = shape.get("text")
    if not text:
        return False
    stripped = text.get("full_text", "").strip()
    return bool(stripped) and stripped.isdigit() and len(stripped) <= 3


def _shape_kind(shape: Dict[str, Any]) -> str:
    raw = shape.get("shape_type") or ""
    kind = raw.split(" (")[0].lower()
    if shape.get("placeholder_type"):
        return f"placeholder_{shape['placeholder_type'].split(' (')[0].lower()}"
    return kind


def _slot_from_shape(shape: Dict[str, Any], slot_id: str) -> Optional[Dict[str, Any]]:
    """A 'slot' is anything fillable: a text-bearing shape (not a guidance
    sticker), or a table/chart graphic frame. Pure decoration (no text, no
    table, no chart) yields no slot."""
    text = shape.get("text")
    if text and text.get("is_guidance_sticker"):
        return None

    if shape.get("table"):
        table = shape["table"]
        return {
            "slot_id": slot_id,
            "kind": "table",
            "shape_id": shape["shape_id"],
            "table_schema": {
                "rows": table["rows"],
                "cols": table["cols"],
                "header_row": table["header_row"],
            },
        }
    if shape.get("chart"):
        chart = shape["chart"]
        return {
            "slot_id": slot_id,
            "kind": "chart",
            "shape_id": shape["shape_id"],
            "chart_schema": {
                "chart_type": chart["chart_type"],
                "categories": chart["categories"],
                "series_names": chart["series_names"],
            },
        }
    if text and text.get("full_text", "").strip():
        return {
            "slot_id": slot_id,
            "kind": _shape_kind(shape),
            "shape_id": shape["shape_id"],
            "sample_text": text["full_text"],
            "max_chars": _max_chars(text["full_text"]),
        }
    # Some template slides ship with a genuinely EMPTY title text box (no
    # sample run at all) — e.g. the cover slide's "Title 5". Still a real,
    # intentional content slot; recognized generically by the authoring
    # convention "title" appears in the shape's own name, not by any
    # document-topic name, with a sensible default max_chars since there's
    # no sample text length to measure.
    if not shape.get("table") and not shape.get("chart") and "title" in (shape.get("name") or "").lower():
        return {
            "slot_id": slot_id,
            "kind": "empty_title_box",
            "shape_id": shape["shape_id"],
            "sample_text": "",
            "max_chars": 40,
        }
    return None


def _detect_repeat_groups(shapes: List[Dict[str, Any]], used_shape_ids: set) -> List[Dict[str, Any]]:
    """Finds top-level sibling GROUP shapes with near-identical heights
    (card/badge/chevron patterns e.g. 3 priority pillars, 4 stat badges).
    Builds the item slot template from the first group's text-bearing
    children, in top-to-bottom reading order (purely positional — no
    semantic naming beyond slot_1, slot_2, ... since there's no reliable
    generic way to know "heading" vs "label" without hardcoding)."""
    candidate_groups = [
        s for s in shapes
        if s.get("shape_type", "").startswith("GROUP") and s["shape_id"] not in used_shape_ids
    ]
    if len(candidate_groups) < 2:
        return []

    clusters: List[List[Dict[str, Any]]] = []
    for group in candidate_groups:
        height = group["position_in"]["height"]
        placed = False
        for cluster in clusters:
            ref_height = cluster[0]["position_in"]["height"]
            if ref_height and abs(height - ref_height) / ref_height <= HEIGHT_TOLERANCE:
                cluster.append(group)
                placed = True
                break
        if not placed:
            clusters.append([group])

    repeat_groups = []
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        cluster.sort(key=lambda s: s["position_in"]["left"])
        template_group = cluster[0]
        children = sorted(
            template_group.get("children", []),
            key=lambda c: (round(c["position_in"]["top"], 2), c["position_in"]["left"]),
        )
        item_slots = []
        for child in children:
            text = child.get("text")
            if text and text.get("full_text", "").strip() and not text.get("is_guidance_sticker"):
                item_slots.append({
                    "slot_id": f"item_slot_{len(item_slots) + 1}",
                    "sample_text": text["full_text"],
                    "max_chars": _max_chars(text["full_text"]),
                })
        if not item_slots:
            continue
        for group in cluster:
            used_shape_ids.add(group["shape_id"])
        repeat_groups.append({
            "group_slot_id": f"repeat_group_{template_group['shape_id']}",
            "item_count": len(cluster),
            # All N group shape_ids in this cluster (cloning preserves shape_id,
            # so the renderer re-derives each member's own child ordering by
            # position at render time rather than needing a fixed child map).
            "member_shape_ids": [g["shape_id"] for g in cluster],
            "item_slots": item_slots,
        })
    return repeat_groups


def build_entry(record: Dict[str, Any]) -> Dict[str, Any]:
    shapes = record["shapes"]
    used_shape_ids: set = set()

    repeat_groups = _detect_repeat_groups(shapes, used_shape_ids)

    auto_number_shapes = sorted(
        (s for s in shapes if s["shape_id"] not in used_shape_ids and not _is_chrome(s) and _is_auto_number(s)),
        key=lambda s: (round(s["position_in"]["top"], 2), s["position_in"]["left"]),
    )
    auto_number_shape_ids = [s["shape_id"] for s in auto_number_shapes]
    used_shape_ids.update(auto_number_shape_ids)

    slots = []
    for shape in shapes:
        if _is_chrome(shape) or shape["shape_id"] in used_shape_ids:
            continue
        name_slug = "".join(c if c.isalnum() else "_" for c in shape["name"].lower()).strip("_")
        slot_id = f"{name_slug}_{shape['shape_id']}"
        slot = _slot_from_shape(shape, slot_id)
        if slot:
            slots.append(slot)

    has_table = any(s["kind"] == "table" for s in slots)
    has_chart = any(s["kind"] == "chart" for s in slots)

    return {
        "slide_id": record["slide_name"],
        "source_slide_index": record["index"],
        "title": record.get("title"),
        "category": record.get("category"),
        "always_include": record.get("category") == "Mandatory",
        "has_table": has_table,
        "has_chart": has_chart,
        "repeat_groups": repeat_groups,
        "auto_number_shape_ids": auto_number_shape_ids,
        "slots": slots,
    }


def main() -> None:
    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for metadata_path in sorted(METADATA_DIR.glob("slide_*.json")):
        record = json.loads(metadata_path.read_text(encoding="utf-8"))
        if record.get("category") in EXCLUDED_CATEGORIES:
            continue
        entries.append(build_entry(record))

    OUT_PATH.write_text(
        json.dumps({"version": "1.0", "slides": entries}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[layout-catalog] wrote {len(entries)} fillable slide entries -> {OUT_PATH}")


if __name__ == "__main__":
    main()
