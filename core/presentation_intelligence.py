"""Presentation intelligence derived from the existing content analysis."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ContentSource(BaseModel):
    """Normalized source metadata and traceability information."""

    source_id: str
    source_type: str
    filename: str = ""
    title: str = ""
    text: str = ""
    provenance: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    charts: List[Dict[str, Any]] = Field(default_factory=list)
    extraction_warnings: List[str] = Field(default_factory=list)


class PresentationBrief(BaseModel):
    """Decision record used by planning, governance, and audit layers."""

    audience: str
    presentation_type: str
    storyline: List[str] = Field(default_factory=list)
    executive_message: str = ""
    recommended_layouts: List[str] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)


def classify_presentation(
    content_analysis: Any,
    audience: str,
    template_id: str,
) -> PresentationBrief:
    """Classify the presentation and expose explainable planning signals."""
    detected = {str(item).upper() for item in getattr(content_analysis, "content_types_detected", [])}
    topic = getattr(content_analysis, "main_topic", "Business update") or "Business update"
    topic_lower = topic.lower()

    if template_id == "hld_qbr" or any(token in topic_lower for token in ("qbr", "quarterly", "business review")):
        presentation_type = "Quarterly business review"
    elif any(token in topic_lower for token in ("roadmap", "strategy", "strategic")) or "TIMELINE" in detected:
        presentation_type = "Strategy and roadmap"
    elif any(token in topic_lower for token in ("proposal", "business case", "solution")):
        presentation_type = "Solution proposal"
    elif any(token in topic_lower for token in ("status", "program", "project")):
        presentation_type = "Project status report"
    else:
        presentation_type = "Executive update" if audience == "Executive" else "Business presentation"

    storyline = ["Context and executive message"]
    storyline.extend(getattr(content_analysis, "agenda_topics", [])[:6])
    if not getattr(content_analysis, "agenda_topics", []):
        storyline.extend(getattr(content_analysis, "sections", [])[:6])
    storyline.append("Recommendations and next steps")

    highlights = getattr(content_analysis, "executive_highlights", [])
    executive_message = highlights[0] if highlights else getattr(content_analysis, "summary", "")

    layouts = ["EXECUTIVE_SUMMARY", "AGENDA"]
    if getattr(content_analysis, "statistics", []):
        layouts.append("STATS")
    if getattr(content_analysis, "processes", []):
        layouts.append("PROCESS")
    if getattr(content_analysis, "timelines", []):
        layouts.append("TIMELINE")
    layouts.extend(["BULLETS", "CONCLUSION"])

    return PresentationBrief(
        audience=audience or "General",
        presentation_type=presentation_type,
        storyline=storyline,
        executive_message=executive_message,
        recommended_layouts=list(dict.fromkeys(layouts)),
    )