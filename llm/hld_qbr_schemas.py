"""
llm/hld_qbr_schemas.py — Pydantic schemas for the HLD QBR template's
presentation plan.

Unlike the freeform DynamicPresentationPlan (template1/techm_v3), the HLD QBR
template is archetype-based: each field below maps to one specific, named
template slide (see core/builders/hld_qbr_builder.py). Any field left empty
means that slide is simply omitted from the generated deck — sections are
optional except cover/agenda/closing (always included).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class OrgPersonItem(BaseModel):
    """One person/role card for an org-structure slide."""
    name: str = ""
    role: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data):
        if isinstance(data, dict):
            name = data.get("name") or data.get("person") or data.get("full_name") or ""
            role = data.get("role") or data.get("title") or data.get("position") or ""
            return {"name": str(name).strip(), "role": str(role).strip()}
        return data


class PriorityItem(BaseModel):
    """One of up to 3 priority pillars."""
    heading: str = Field(default="Priority", description="Short pillar heading, e.g. 'Expand to New Markets'")
    body: str = Field(default="", description="One-sentence supporting detail")

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data):
        if isinstance(data, dict):
            heading = data.get("heading") or data.get("title") or data.get("name") or "Priority"
            body = data.get("body") or data.get("description") or data.get("detail") or ""
            return {"heading": str(heading).strip(), "body": str(body).strip()}
        return data


class ActionTrackerRow(BaseModel):
    project: str = ""
    owner: str = ""
    next_step: str = ""
    comment: str = ""
    status: str = "Not Started"


class KPIRow(BaseModel):
    """One KPI row: label + actual value + target value."""
    label: str = ""
    actual: str = ""
    target: str = ""


class GembaRow(BaseModel):
    area: str = ""
    observation: str = ""


class CIRow(BaseModel):
    """Continuous Improvement activity tracker row."""
    activity: str = ""
    category: str = ""
    status: str = "Not Started"
    value: str = ""
    comment: str = ""


class NonConformanceRow(BaseModel):
    period: str = ""
    nc_id: str = ""
    event: str = ""
    due_date: str = ""
    status: str = ""


class NextStepItem(BaseModel):
    step: str = ""
    date: str = ""


class VoiceOfCustomer(BaseModel):
    quote: str = ""
    attribution: str = ""


class ChartSeries(BaseModel):
    """One data series in a chart (e.g. 'Previous Month' or 'Current Month')."""
    name: str = ""
    values: List[float] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _clean_values(cls, data):
        if isinstance(data, dict):
            import re
            name = data.get("name") or data.get("series_name") or data.get("label") or ""
            raw_vals = data.get("values") or []
            cleaned = []
            for v in raw_vals:
                if isinstance(v, (int, float)):
                    cleaned.append(float(v))
                elif isinstance(v, str):
                    m = re.search(r"[-+]?\d*\.?\d+", v.replace(",", ""))
                    if m:
                        try:
                            cleaned.append(float(m.group(0)))
                        except ValueError:
                            cleaned.append(0.0)
                    else:
                        cleaned.append(0.0)
                else:
                    cleaned.append(0.0)
            return {"name": str(name).strip(), "values": cleaned}
        return data


class OperationalChart(BaseModel):
    """Clustered column chart slide with side observation bullets (template Slide 13 archetype)."""
    chart_title: str = Field(default="Operational Performance Snapshot", description="Slide and chart title")
    categories: List[str] = Field(default_factory=list, description="Up to 7 metric or category names")
    series: List[ChartSeries] = Field(default_factory=list, description="Up to 3 series, e.g. Previous Month, Current Month")
    insights_title: str = Field(default="KEY OBSERVATIONS", description="Title for the side observation card, e.g. 'KEY OBSERVATIONS' or 'OPERATIONAL INSIGHTS'")
    insights: List[str] = Field(default_factory=list, description="Up to 7 key bullet observations for the side panel")

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data):
        if isinstance(data, dict):
            chart_title = data.get("chart_title") or data.get("title") or "Operational Performance Snapshot"
            categories = data.get("categories") or data.get("metrics") or data.get("labels") or []
            series = data.get("series") or []
            insights_title = data.get("insights_title") or data.get("insights_heading") or "KEY OBSERVATIONS"
            insights = data.get("insights") or data.get("observations") or data.get("takeaways") or []
            return {
                "chart_title": str(chart_title).strip(),
                "categories": [str(c).strip() for c in categories if str(c).strip()],
                "series": series,
                "insights_title": str(insights_title).strip(),
                "insights": [str(ins).strip() for ins in insights if str(ins).strip()],
            }
        return data


class HLDQBRPresentationPlan(BaseModel):
    """Top-level plan consumed by core.builders.hld_qbr_builder.HLDQBRBuilder."""

    presentation_title: str = Field(..., description="Main report title, shown in the right-corner cover box")
    facility_name: str = Field(default="", description="Facility/program label shown on content slides")
    date: str = Field(default="", description="Cover date string, e.g. 'September 20th 2026'")

    agenda_topics: List[str] = Field(default_factory=list)

    org_structure: List[OrgPersonItem] = Field(default_factory=list, description="Up to 10 people")
    achievements: List[str] = Field(default_factory=list, description="Up to 6 prior-quarter milestones")
    priorities: List[PriorityItem] = Field(default_factory=list, description="Up to 3 pillars")

    action_tracker: List[ActionTrackerRow] = Field(default_factory=list, description="Up to 7 rows")

    kpi_safety_quality: List[KPIRow] = Field(default_factory=list, description="Up to 4 rows")
    kpi_operational: List[KPIRow] = Field(default_factory=list, description="Up to 7 rows")
    operational_chart: Optional[OperationalChart] = Field(default=None, description="Comparative monthly/quarterly chart with side observations")

    voice_of_customer: Optional[VoiceOfCustomer] = None

    gemba_walk_intro: str = ""
    gemba_walk: List[GembaRow] = Field(default_factory=list, description="Up to 4 rows")

    ci_tracker: List[CIRow] = Field(default_factory=list, description="Up to 7 rows")

    quality_org_structure: List[OrgPersonItem] = Field(default_factory=list, description="Up to 5 people")

    nc_review_summary: List[str] = Field(
        default_factory=list,
        description="4 values: [total NC initiated, total CAPAs assigned, total CAPAs closed, percent complete]",
    )
    nc_review_narrative: str = ""
    nc_tracker: List[NonConformanceRow] = Field(default_factory=list, description="Up to 7 rows")

    next_steps: List[NextStepItem] = Field(default_factory=list, description="Up to 4 rows")

    content_traceability: Dict[str, List[str]] = Field(
        default_factory=dict,
        description=(
            "Maps each populated archetype field name (e.g. 'priorities', 'kpi_operational') "
            "to the Content Model item ids that support it. Only cite ids that genuinely "
            "support the field's text; omit a field entirely if it was not grounded in the "
            "supplied Content Model."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_wrapped(cls, data):
        if isinstance(data, dict) and "plan" in data and "presentation_title" not in data:
            return data["plan"]
        return data
