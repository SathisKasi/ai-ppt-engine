"""
core/hld_qbr_catalog.py — Loads templates/hld_qbr_assets/inventory/
layout_capability_catalog.json (see templates/build_hld_qbr_layout_catalog.py)
and provides compact, prompt-ready views of it.

This catalog is the single source of truth for "what can this template
actually hold" — no topic names or sample text, only structure
(slots/maxChars/tables/charts/repeat-groups). The outline-assignment prompt
gets a compact summary; the content-fill prompt gets the full entry for just
the slides actually picked.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

CATALOG_PATH = getattr(config, "HLD_QBR_CATALOG_FILE", None)
if CATALOG_PATH is None or not CATALOG_PATH.exists():
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    CATALOG_PATH = _PROJECT_ROOT / "templates" / "hld_qbr_assets" / "inventory" / "layout_capability_catalog.json"

_cache: Optional[List[Dict[str, Any]]] = None


def load_catalog() -> List[Dict[str, Any]]:
    global _cache
    if _cache is None:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        _cache = data["slides"]
    return _cache


def get_entry(slide_id: str) -> Optional[Dict[str, Any]]:
    return next((s for s in load_catalog() if s["slide_id"] == slide_id), None)


def always_include_slide_ids() -> List[str]:
    return [s["slide_id"] for s in load_catalog() if s.get("always_include")]


# Cover/Agenda/Closing are pure structural chrome (branding/title/date; agenda's
# content is derived from the final chosen slide list, not document content) —
# these 3 specific ids are a structural fact about this template (every QBR
# deck needs a cover and closing slide), not a hardcoded document topic, so
# they're excluded from the pickable/content-matching catalog entirely.
STRUCTURAL_ONLY_SLIDE_IDS = {"slide_00", "slide_01", "slide_03", "slide_30"}


def content_bearing_mandatory_slide_ids() -> List[str]:
    """Mandatory slides that still need real document content (e.g. the
    executive summary) — forced into the final deck like any always-include
    slide, but still a normal pick/content-fill candidate upstream."""
    return [sid for sid in always_include_slide_ids() if sid not in STRUCTURAL_ONLY_SLIDE_IDS]



def compact_catalog_for_outline(exclude_slide_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Slim view for the outline-assignment call: no renderer-only shape
    ids — just enough structure to match content by SHAPE, not name.
    Excludes STRUCTURAL_ONLY_SLIDE_IDS (cover/agenda/closing).
    If exclude_slide_ids is provided, excludes non-repeatable slides that are in that list."""
    compact = []
    excluded_set = set(exclude_slide_ids or [])
    for entry in load_catalog():
        sid = entry["slide_id"]
        if sid in STRUCTURAL_ONLY_SLIDE_IDS:
            continue
        is_repeatable = entry.get("has_table") or entry.get("has_chart")
        if sid in excluded_set and not is_repeatable:
            continue

        # Summarize simple body text slots (exclude slide titles so outline matches real body capacity)
        text_slots = [
            s for s in entry["slots"]
            if not s.get("table_schema") and not s.get("chart_schema")
            and s.get("kind") not in ("placeholder_title", "empty_title_box")
        ]
        has_table = bool(entry.get("has_table"))
        has_chart = bool(entry.get("has_chart"))
        has_repeats = bool(entry.get("repeat_groups"))

        # Skip slides that have zero body capacity
        if not text_slots and not has_table and not has_chart and not has_repeats:
            continue

        item: Dict[str, Any] = {"slide_id": sid}
        if entry.get("always_include"):
            item["always_include"] = True
        if text_slots:
            item["text_slots"] = len(text_slots)

        # Table capability if present
        table_slot = next((s for s in entry["slots"] if s.get("table_schema")), None)
        if table_slot:
            ts = table_slot["table_schema"]
            item["table"] = {"cols": ts.get("cols"), "rows": ts.get("rows")}

        # Chart capability if present
        chart_slot = next((s for s in entry["slots"] if s.get("chart_schema")), None)
        if chart_slot:
            cs = chart_slot["chart_schema"]
            item["chart"] = {
                "type": cs.get("chart_type"),
                "categories": cs.get("category_count"),
                "series": cs.get("series_count"),
            }

        # Table/chart slides may be picked more than once (one per distinct
        # tabular/numeric dataset in the source) — every other slide_id is
        # still single-use. Flag explicitly so the outline prompt doesn't
        # have to infer this from the presence of "table"/"chart" alone.
        if entry.get("has_table") or entry.get("has_chart"):
            item["repeatable"] = True

        # Repeat groups (cards, badges, multi-column items)
        if entry.get("repeat_groups"):
            item["repeats"] = [
                {"max_items": rg["item_count"], "item_slots": len(rg["item_slots"])}
                for rg in entry["repeat_groups"]
            ]

        compact.append(item)
    return compact


def full_entries_for(slide_ids: List[str]) -> List[Dict[str, Any]]:
    by_id = {s["slide_id"]: s for s in load_catalog()}
    return [by_id[sid] for sid in slide_ids if sid in by_id]
