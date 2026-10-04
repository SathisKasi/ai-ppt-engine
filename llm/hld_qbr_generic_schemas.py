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


class ChartSeriesValues(BaseModel):
    name: str
    values: List[float] = Field(default_factory=list)


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
