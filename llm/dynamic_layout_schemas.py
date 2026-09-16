"""
llm/dynamic_layout_schemas.py — Pydantic schemas for dynamic visual layouts and content enrichment.

Enables the LLM to design arbitrary slide layouts inside the TechM_RefPPT-V3
content canvas (12.5" x 5.9" safe zone) without being constrained to static archetypes.
Equipped with robust model validators to seamlessly normalize LLM variations.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class KPIMetricItem(BaseModel):
    """A high-impact KPI / metric callout."""
    value: str = Field(default="0", description="The prominent metric number, e.g. '42%', '$15M', '99.99%'")
    label: str = Field(default="Metric", description="Short metric label, e.g. 'Cost Reduction', 'Uptime SLA'")
    delta: Optional[str] = Field(None, description="Optional trend, comparison or context, e.g. '+15% YoY'")

    @model_validator(mode="before")
    @classmethod
    def _normalize_kpi(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("value") or data.get("metric") or data.get("stat") or data.get("number") or "KPI"
            lbl = data.get("label") or data.get("title") or data.get("name") or data.get("metric_name") or "Metric"
            dlt = data.get("delta") or data.get("context") or data.get("trend") or data.get("change")
            return {
                "value": str(val).strip(),
                "label": str(lbl).strip(),
                "delta": str(dlt).strip() if dlt else None,
            }
        return data


class CardItem(BaseModel):
    """A styled content card / container."""
    title: str = Field(default="Key Takeaway", description="Card heading or pillar title")
    tag: Optional[str] = Field(None, description="Optional badge / category tag, e.g. 'Phase 1', 'Critical'")
    bullets: List[str] = Field(default_factory=list, description="Action-oriented bullet points (max 12 words each)")
    footer: Optional[str] = Field(None, description="Optional bottom highlight or metric")

    @model_validator(mode="before")
    @classmethod
    def _normalize_card(cls, data: Any) -> Any:
        if isinstance(data, dict):
            title_val = data.get("title") or data.get("heading") or data.get("name") or "Key Focus"
            tag_val = data.get("tag") or data.get("category") or data.get("badge")
            bullets_raw = data.get("bullets") or data.get("points") or data.get("items") or data.get("content") or []
            if isinstance(bullets_raw, str):
                bullets_list = [b.strip() for b in bullets_raw.split("\n") if b.strip()]
            elif isinstance(bullets_raw, list):
                bullets_list = [str(b).strip() for b in bullets_raw if str(b).strip()]
            else:
                bullets_list = []
            footer_val = data.get("footer") or data.get("note")
            return {
                "title": str(title_val).strip(),
                "tag": str(tag_val).strip() if tag_val else None,
                "bullets": bullets_list,
                "footer": str(footer_val).strip() if footer_val else None,
            }
        return data


class ProcessStepItem(BaseModel):
    """A sequential process step or workflow phase."""
    step_number: str = Field(default="1", description="Step identifier, e.g. '01', 'Phase 1', 'Step A'")
    title: str = Field(default="Process Step", description="Step title")
    description: str = Field(default="", description="Actionable description or deliverables")
    tag: Optional[str] = Field(None, description="Optional status or team tag")

    @model_validator(mode="before")
    @classmethod
    def _normalize_step(cls, data: Any) -> Any:
        if isinstance(data, dict):
            num = data.get("step_number") or data.get("number") or data.get("step") or data.get("id") or "1"
            title_val = data.get("title") or data.get("name") or data.get("heading") or f"Step {num}"
            desc_val = (
                data.get("description")
                or data.get("desc")
                or data.get("details")
                or data.get("text")
                or data.get("deliverables")
                or ""
            )
            tag_val = data.get("tag") or data.get("phase") or data.get("status")
            return {
                "step_number": str(num).strip(),
                "title": str(title_val).strip(),
                "description": str(desc_val).strip(),
                "tag": str(tag_val).strip() if tag_val else None,
            }
        return data


class TableDataGrid(BaseModel):
    """A structured 2D table grid."""
    headers: List[str] = Field(default_factory=list, description="Column header titles")
    rows: List[List[str]] = Field(default_factory=list, description="Row data items corresponding to headers")

    @model_validator(mode="before")
    @classmethod
    def _normalize_table(cls, data: Any) -> Any:
        if isinstance(data, dict):
            headers_raw = data.get("headers") or data.get("columns") or []
            rows_raw = data.get("rows") or data.get("data") or []
            headers = [str(h).strip() for h in headers_raw]
            rows = []
            for r in rows_raw:
                if isinstance(r, list):
                    rows.append([str(c).strip() for c in r])
                elif isinstance(r, dict):
                    rows.append([str(r.get(h, "")).strip() for h in headers])
                else:
                    rows.append([str(r).strip()])
            return {
                "headers": headers or ["Category", "Details"],
                "rows": rows or [["Item 1", "Details 1"]],
            }
        return data


class TimelineItem(BaseModel):
    """A chronological milestone or release point."""
    date: str = Field(default="Milestone", description="Date or timeframe, e.g. 'Q1 2026', 'Month 3'")
    event: str = Field(default="Key Milestone", description="Milestone title")
    description: str = Field(default="", description="Key achievements or deliverables")

    @model_validator(mode="before")
    @classmethod
    def _normalize_timeline(cls, data: Any) -> Any:
        if isinstance(data, dict):
            date_val = data.get("date") or data.get("time") or data.get("period") or data.get("phase") or "Milestone"
            event_val = (
                data.get("event")
                or data.get("milestone")
                or data.get("title")
                or data.get("name")
                or "Milestone"
            )
            desc_val = (
                data.get("description")
                or data.get("desc")
                or data.get("details")
                or data.get("text")
                or data.get("deliverables")
                or ""
            )
            # If milestone contained a longer string and description was missing:
            if not desc_val and len(str(event_val)) > 40 and (" — " in str(event_val) or " - " in str(event_val)):
                sep = " — " if " — " in str(event_val) else " - "
                parts = str(event_val).split(sep, 1)
                event_val = parts[0]
                desc_val = parts[1]
            return {
                "date": str(date_val).strip(),
                "event": str(event_val).strip(),
                "description": str(desc_val).strip(),
            }
        return data


class ComparisonColumn(BaseModel):
    """A column in a side-by-side comparison."""
    heading: str = Field(default="Option", description="Column heading, e.g. 'Current State', 'Target Architecture'")
    tag: Optional[str] = Field(None, description="Optional status badge, e.g. 'Before', 'Legacy', 'Cloud-Native'")
    bullets: List[str] = Field(default_factory=list, description="Key characteristics or bullet points")

    @model_validator(mode="before")
    @classmethod
    def _normalize_comparison(cls, data: Any) -> Any:
        if isinstance(data, dict):
            h_val = data.get("heading") or data.get("title") or data.get("name") or "Option"
            tag_val = data.get("tag") or data.get("badge") or data.get("status")
            bullets_raw = data.get("bullets") or data.get("points") or data.get("items") or []
            if isinstance(bullets_raw, str):
                bullets_list = [b.strip() for b in bullets_raw.split("\n") if b.strip()]
            elif isinstance(bullets_raw, list):
                bullets_list = [str(b).strip() for b in bullets_raw if str(b).strip()]
            else:
                bullets_list = []
            return {
                "heading": str(h_val).strip(),
                "tag": str(tag_val).strip() if tag_val else None,
                "bullets": bullets_list,
            }
        return data


class HeroBlock(BaseModel):
    """A prominent hero banner or executive callout."""
    headline: str = Field(default="Executive Brief", description="Bold core message or thesis statement")
    subtext: str = Field(default="", description="Supporting narrative or strategic justification")
    key_takeaway: Optional[str] = Field(None, description="Actionable takeaway")

    @model_validator(mode="before")
    @classmethod
    def _normalize_hero(cls, data: Any) -> Any:
        if isinstance(data, dict):
            head = data.get("headline") or data.get("title") or data.get("heading") or "Executive Brief"
            sub = data.get("subtext") or data.get("description") or data.get("text") or ""
            takeaway = data.get("key_takeaway") or data.get("takeaway") or data.get("call_to_action")
            return {
                "headline": str(head).strip(),
                "subtext": str(sub).strip(),
                "key_takeaway": str(takeaway).strip() if takeaway else None,
            }
        return data


class DynamicLayoutComposition(BaseModel):
    """
    Flexible layout composition container.
    The LLM populates the fields corresponding to its chosen pattern.
    """
    pattern: str = Field(
        default="MULTI_COLUMN_CARDS",
        description=(
            "Chosen layout pattern: 'MULTI_COLUMN_CARDS', 'METRIC_RIBBON_AND_CARDS', "
            "'PROCESS_PIPELINE', 'COMPARISON_SPLIT', 'DATA_MATRIX_TABLE', "
            "'TIMELINE_ROADMAP', 'HERO_AND_SIDEBAR', 'KEY_HIGHLIGHTS'"
        ),
    )
    metrics: Optional[List[KPIMetricItem]] = Field(None, description="Used in metric ribbons or KPI slides (2-4 items)")
    cards: Optional[List[CardItem]] = Field(None, description="Used in multi-column cards or grids (2-4 items)")
    steps: Optional[List[ProcessStepItem]] = Field(None, description="Used in process pipelines (3-5 items)")
    table: Optional[TableDataGrid] = Field(None, description="Used in structured data matrices")
    timeline: Optional[List[TimelineItem]] = Field(None, description="Used in roadmap / milestone views (3-5 items)")
    comparison: Optional[List[ComparisonColumn]] = Field(None, description="Used in side-by-side comparisons (2-3 columns)")
    hero: Optional[HeroBlock] = Field(None, description="Used in hero banners or executive summaries")

    @model_validator(mode="before")
    @classmethod
    def _normalize_comp(cls, data: Any) -> Any:
        if isinstance(data, dict):
            pattern = str(data.get("pattern") or "").upper().strip()
            # Auto-detect pattern if empty or generic
            if not pattern or pattern in ("CUSTOM", "NONE"):
                if data.get("metrics") and data.get("cards"):
                    pattern = "METRIC_RIBBON_AND_CARDS"
                elif data.get("timeline"):
                    pattern = "TIMELINE_ROADMAP"
                elif data.get("steps"):
                    pattern = "PROCESS_PIPELINE"
                elif data.get("comparison"):
                    pattern = "COMPARISON_SPLIT"
                elif data.get("table"):
                    pattern = "DATA_MATRIX_TABLE"
                elif data.get("hero"):
                    pattern = "HERO_AND_SIDEBAR"
                else:
                    pattern = "MULTI_COLUMN_CARDS"
            data["pattern"] = pattern
            return data
        return data


class DynamicSlideDefinition(BaseModel):
    """Slide specification for the dynamic canvas."""
    slide_number: int = Field(default=2, description="Sequential slide number starting at 2 (1 is Title cover)")
    title: str = Field(default="Slide Title", description="Slide title to place in header placeholder")
    subtitle: Optional[str] = Field(None, description="Context-specific subtitle in slide header bar (e.g. 'Legacy Architecture | Cloud Capabilities')")
    executive_takeaway: Optional[str] = Field(None, description="1-sentence punchy takeaway displayed below title")
    layout_pattern: str = Field(default="MULTI_COLUMN_CARDS", description="Selected pattern name")
    composition: DynamicLayoutComposition = Field(default_factory=DynamicLayoutComposition, description="The detailed layout composition components")
    speaker_notes: Optional[str] = Field("", description="Speaker notes for presenting this slide")

    @model_validator(mode="before")
    @classmethod
    def _normalize_slide(cls, data: Any) -> Any:
        if isinstance(data, dict):
            slide_num = data.get("slide_number") or data.get("slide") or data.get("number") or 2
            title_val = data.get("title") or data.get("heading") or "Slide Title"
            subtitle_val = data.get("subtitle") or data.get("sub_title") or data.get("context")
            takeaway_val = data.get("executive_takeaway") or data.get("takeaway") or data.get("summary") or data.get("purpose")
            notes_val = data.get("speaker_notes") or data.get("notes") or ""

            # Check composition
            comp = data.get("composition")
            if isinstance(comp, BaseModel):
                comp = comp.model_dump()
            elif not comp or not isinstance(comp, dict):
                comp = {}
                for k in ["metrics", "cards", "steps", "table", "timeline", "comparison", "hero", "pattern"]:
                    if k in data:
                        comp[k] = data[k]
            pattern_val = data.get("layout_pattern") or (comp.get("pattern") if isinstance(comp, dict) else None) or "MULTI_COLUMN_CARDS"
            if isinstance(comp, dict):
                comp["pattern"] = pattern_val

            return {
                "slide_number": int(slide_num),
                "title": str(title_val).strip(),
                "subtitle": str(subtitle_val).strip() if subtitle_val else None,
                "executive_takeaway": str(takeaway_val).strip() if takeaway_val else None,
                "layout_pattern": str(pattern_val).strip(),
                "composition": comp,
                "speaker_notes": str(notes_val).strip() if notes_val else "",
            }
        return data


class DynamicPresentationPlan(BaseModel):
    """Complete presentation plan tailored for TechM_RefPPT-V3."""
    title: str = Field(default="Presentation Title", description="Presentation title for Slide 1 Cover")
    subtitle: Optional[str] = Field(None, description="Subtitle for Slide 1 Cover")
    date: Optional[str] = Field("16SEP2026", description="Date string for Slide 1 Date placeholder")
    audience: Optional[str] = Field("", description="Target audience")
    slides: List[DynamicSlideDefinition] = Field(default_factory=list, description="List of content slides (duplicates of Slide 2)")

    @model_validator(mode="before")
    @classmethod
    def _normalize_plan(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "presentation" in data and isinstance(data["presentation"], dict):
                data = data["presentation"]
            t_val = data.get("title") or "UPS Presentation"
            sub_val = data.get("subtitle")
            d_val = data.get("date") or "16SEP2026"
            aud_val = data.get("audience") or ""
            slides_val = data.get("slides") or []
            return {
                "title": str(t_val).strip(),
                "subtitle": str(sub_val).strip() if sub_val else None,
                "date": str(d_val).strip(),
                "audience": str(aud_val).strip(),
                "slides": slides_val,
            }
        return data
