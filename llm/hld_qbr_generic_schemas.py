"""
llm/hld_qbr_generic_schemas.py — Generic, data-driven presentation plan for
the HLD QBR template.

Unlike llm/hld_qbr_schemas.py (one named Pydantic field per pre-enumerated
archetype), this plan is keyed entirely by slide_id/slot_id values that come
from templates/hld_qbr_assets/inventory/layout_capability_catalog.json — a
structural catalog with NO notion of document topic names. The LLM maps
content extracted by core/content_model_extractor.py (open-ended, no
predefined categories) onto whichever catalog slide structurally fits it;
this plan is just the typed container for that mapping, consumed by
core/builders/hld_qbr_generic_builder.py's generic renderer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

_UNICODE_REPLACEMENTS = [
    ("\u2011", "-"), ("\u2012", "-"), ("\u2013", "-"), ("\u2014", " - "),
    ("\u2015", "-"), ("\u00a0", " "), ("\u2018", "'"), ("\u2019", "'"),
    ("\u201c", '"'), ("\u201d", '"'), ("\u2026", "..."), ("\u2022", "*"),
    ("\u25cf", "*"), ("\u202f", " "), ("\ufeff", ""),
]


def _sanitize_str(text: str) -> str:
    for char, replacement in _UNICODE_REPLACEMENTS:
        text = text.replace(char, replacement)
    return text


def _sanitize_value(obj: Any) -> Any:
    if isinstance(obj, str):
        return _sanitize_str(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_value(item) for item in obj]
    return obj


import re


class ChartSeriesValues(BaseModel):
    name: str = "Series"
    values: List[float] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _sanitize_series(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        name = data.get("name") or data.get("series_name") or data.get("label") or data.get("title") or "Series"
        raw_vals = data.get("values") or []
        cleaned_vals = []
        for v in raw_vals:
            if v is None:
                cleaned_vals.append(0.0)
            elif isinstance(v, (int, float)):
                cleaned_vals.append(float(v))
            elif isinstance(v, str):
                cleaned_str = re.sub(r"[^0-9.-]", "", v.strip())
                try:
                    cleaned_vals.append(float(cleaned_str))
                except ValueError:
                    cleaned_vals.append(0.0)
            else:
                cleaned_vals.append(0.0)
        return {"name": str(name), "values": cleaned_vals}


class SlideAssignment(BaseModel):
    """One catalog slide, filled in. Only the fields relevant to that
    slide's actual capability (per layout_capability_catalog.json) are
    populated — a text-only slide never has table_rows, etc."""

    slide_id: str = Field(..., description="Catalog slide_id, e.g. 'slide_05'")
    source_slide_index: int
    title: Optional[str] = Field(default=None, description="Value for this slide's title slot, if it has one")
    slot_values: Dict[str, str] = Field(default_factory=dict, description="slot_id -> text, for simple text slots")
    repeat_items: List[Dict[str, str]] = Field(
        default_factory=list,
        description="One dict per repeated card/badge instance, each mapping item_slot_id -> text",
    )
    table_headers: Optional[List[str]] = None
    table_rows: Optional[List[List[str]]] = None
    chart_categories: Optional[List[str]] = None
    chart_series: Optional[List[ChartSeriesValues]] = None
    content_item_ids: List[str] = Field(
        default_factory=list, description="ContentModel item ids this slide's content was grounded in (traceability)"
    )

    @model_validator(mode="before")
    @classmethod
    def _sanitize_assignment(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # 1. Sanitize slot_values: coerce values to str, ignore None
        raw_slots = data.get("slot_values")
        if isinstance(raw_slots, dict):
            cleaned_slots = {}
            for k, v in raw_slots.items():
                if v is not None and str(v).strip():
                    cleaned_slots[str(k)] = str(v).strip()
            data["slot_values"] = cleaned_slots
        elif raw_slots is None:
            data["slot_values"] = {}

        # 2. Sanitize repeat_items: coerce all dict values to string
        raw_items = data.get("repeat_items")
        if isinstance(raw_items, list):
            cleaned_items = []
            for item in raw_items:
                if isinstance(item, dict):
                    cleaned_items.append({str(k): str(v) if v is not None else "" for k, v in item.items()})
            data["repeat_items"] = cleaned_items

        # 3. Sanitize table_headers & table_rows
        raw_headers = data.get("table_headers")
        if isinstance(raw_headers, list):
            data["table_headers"] = [str(h) if h is not None else "" for h in raw_headers]
        raw_rows = data.get("table_rows")
        if isinstance(raw_rows, list):
            cleaned_rows = []
            for r in raw_rows:
                if isinstance(r, list):
                    cleaned_rows.append([str(c) if c is not None else "" for c in r])
            data["table_rows"] = cleaned_rows

        # 4. Sanitize chart_categories & chart_series
        raw_series = data.get("chart_series")
        raw_cats = data.get("chart_categories")
        if raw_series and isinstance(raw_series, list):
            # Check if there is at least one series with real numeric content
            has_numeric = False
            for s in raw_series:
                if isinstance(s, dict):
                    vals = s.get("values") or []
                    for v in vals:
                        if isinstance(v, (int, float)):
                            has_numeric = True
                            break
                        elif isinstance(v, str) and re.search(r"\d", v):
                            has_numeric = True
                            break
                if has_numeric:
                    break
            if not has_numeric or not raw_cats:
                # LLM output descriptive text or empty chart data -> safely omit chart
                data["chart_series"] = None
                data["chart_categories"] = None
        else:
            data["chart_series"] = None

        return data


class GenericHLDQBRPlan(BaseModel):
    presentation_title: str = ""
    facility_name: str = ""
    date: str = ""
    slides: List[SlideAssignment] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _sanitize_all_strings(cls, data: Any) -> Any:
        return _sanitize_value(data) if isinstance(data, dict) else data

    def slide_by_id(self, slide_id: str) -> Optional[SlideAssignment]:
        return next((s for s in self.slides if s.slide_id == slide_id), None)
