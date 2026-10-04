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
STRUCTURAL_ONLY_SLIDE_IDS = {"slide_00", "slide_01", "slide_30"}


def content_bearing_mandatory_slide_ids() -> List[str]:
    """Mandatory slides that still need real document content (e.g. the
    executive summary) — forced into the final deck like any always-include
    slide, but still a normal pick/content-fill candidate upstream."""
    return [sid for sid in always_include_slide_ids() if sid not in STRUCTURAL_ONLY_SLIDE_IDS]



def compact_catalog_for_outline() -> List[Dict[str, Any]]:
    """Slim view for the outline-assignment call: no renderer-only shape
    ids — just enough structure to match content by SHAPE, not name.
    Excludes STRUCTURAL_ONLY_SLIDE_IDS (cover/agenda/closing) — nothing to
    decide there, they're force-included by the orchestrator regardless."""
    compact = []
    for entry in load_catalog():
        if entry["slide_id"] in STRUCTURAL_ONLY_SLIDE_IDS:
            continue
        slots_summary = []
        for s in entry["slots"]:
            item = {"slot_id": s["slot_id"], "kind": s["kind"]}
            if s.get("max_chars") is not None:
                item["max_chars"] = s["max_chars"]
            if s.get("table_schema"):
                item["table_schema"] = s["table_schema"]
            if s.get("chart_schema"):
                item["chart_schema"] = {
                    "chart_type": s["chart_schema"]["chart_type"],
                    "category_count": s["chart_schema"]["category_count"],
                    "series_count": s["chart_schema"]["series_count"],
                }
            slots_summary.append(item)
        repeat_summary = [
            {
                "group_slot_id": rg["group_slot_id"],
                "max_items": rg["item_count"],
                "item_slot_count": len(rg["item_slots"]),
                "item_max_chars": [it["max_chars"] for it in rg["item_slots"]],
            }
            for rg in entry["repeat_groups"]
        ]
        compact.append({
            "slide_id": entry["slide_id"],
            "always_include": entry["always_include"],
            "has_table": entry["has_table"],
            "has_chart": entry["has_chart"],
            "repeat_groups": repeat_summary,
            "slots": slots_summary,
        })
    return compact


def full_entries_for(slide_ids: List[str]) -> List[Dict[str, Any]]:
    by_id = {s["slide_id"]: s for s in load_catalog()}
    return [by_id[sid] for sid in slide_ids if sid in by_id]
