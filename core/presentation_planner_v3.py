"""
core/presentation_planner_v3.py — Specialized LLM Planner for TechM_RefPPT-V3 Dynamic Layouts.

Uses Groq LLM with V3_PRESENTATION_PLANNING_PROMPT and SYSTEM_ROLE_V3_ARCHITECT to enrich
content and compose arbitrary visual slide layouts (KPI ribbons, cards, pipelines, comparisons, tables).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from llm.dynamic_layout_schemas import (
    CardItem,
    DynamicLayoutComposition,
    DynamicPresentationPlan,
    DynamicSlideDefinition,
)
from llm.groq_client import GroqClient, JSONParseError
from llm.prompts_dynamic_v3 import SYSTEM_ROLE_V3_ARCHITECT, V3_PRESENTATION_PLANNING_PROMPT
from llm.schemas import ContentAnalysis
from utils.logging_utils import get_logger
from utils.text_utils import truncate_text

logger = get_logger(__name__)


class DynamicPlanningError(Exception):
    """Raised when V3 dynamic presentation planning fails."""


def plan_dynamic_presentation(
    client: GroqClient,
    content_analysis: ContentAnalysis,
    source_text: str = "",
    presentation_title: Optional[str] = None,
    audience: Optional[str] = None,
    style: Optional[str] = None,
    slide_count: int = 6,
    language: Optional[str] = None,
    additional_instructions: Optional[str] = None,
    max_source_chars: int = 12000,
) -> DynamicPresentationPlan:
    """
    Executes the Template-Aware Layout Architect & Content Enricher LLM call.

    Args:
        client: GroqClient instance.
        content_analysis: Structured ContentAnalysis from Stage 1.
        source_text: Raw source document text for grounding.
        presentation_title: Desired title or fallback to main topic.
        audience: Target audience.
        style: Presentation style.
        slide_count: Total slides requested by the user, INCLUDING the mandatory
            Cover and Thank You slides added automatically by the template cloner.
        language: Output language.
        additional_instructions: Custom instructions from user.
        max_source_chars: Character limit for source excerpt.

    Returns:
        Validated DynamicPresentationPlan Pydantic model.
    """
    if not presentation_title or not presentation_title.strip():
        presentation_title = content_analysis.main_topic

    # Cover + Thank You are always added by the builder — subtract them so the
    # final deck totals exactly `slide_count`, not `slide_count + 2`.
    content_slide_count = max(1, slide_count - 2)

    truncated_source = truncate_text(source_text, max_source_chars)
    analysis_json = content_analysis.model_dump_json(indent=2)

    prompt = V3_PRESENTATION_PLANNING_PROMPT.format(
        content_analysis=analysis_json,
        source_content=truncated_source,
        presentation_title=presentation_title,
        audience=audience or "Executive Leadership",
        style=style or "Corporate Strategic",
        slide_count=content_slide_count,
        language=language or "English",
        additional_instructions=additional_instructions or "None",
    )

    messages = [
        {"role": "system", "content": SYSTEM_ROLE_V3_ARCHITECT},
        {"role": "user", "content": prompt},
    ]

    logger.info(
        "Running V3 Dynamic Presentation Planning: %d total requested (%d content slides) for '%s'",
        slide_count,
        content_slide_count,
        presentation_title,
    )

    try:
        raw_data = client.chat_complete_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
        )
    except JSONParseError as e:
        raise DynamicPlanningError(
            f"LLM returned invalid JSON during V3 dynamic presentation planning: {e}"
        ) from e
    except Exception as e:
        raise DynamicPlanningError(
            f"V3 presentation planning LLM call failed: {e}"
        ) from e

    # Handle wrapped structures e.g. {"presentation": {...}}
    plan_dict = raw_data.get("presentation", raw_data)

    try:
        plan = DynamicPresentationPlan.model_validate(plan_dict)
        logger.info(
            "V3 Dynamic Presentation Plan validated successfully with %d content slides.",
            len(plan.slides),
        )
        return plan
    except Exception as e:
        logger.warning(
            "DynamicPresentationPlan direct validation encountered issues: %s — attempting slide-by-slide repair",
            e,
        )
        slides_raw = plan_dict.get("slides") if isinstance(plan_dict, dict) else []
        repaired_slides = []
        for idx, s in enumerate(slides_raw or [], start=2):
            if isinstance(s, dict):
                try:
                    repaired_slides.append(DynamicSlideDefinition.model_validate(s))
                except Exception as s_err:
                    logger.warning("Slide %d failed validation, using resilient fallback: %s", idx, s_err)
                    title_val = str(s.get("title") or f"Section {idx}")
                    repaired_slides.append(
                        DynamicSlideDefinition(
                            slide_number=idx,
                            title=title_val,
                            executive_takeaway=str(s.get("executive_takeaway") or s.get("purpose") or ""),
                            layout_pattern="MULTI_COLUMN_CARDS",
                            composition=DynamicLayoutComposition(
                                pattern="MULTI_COLUMN_CARDS",
                                cards=[
                                    CardItem(
                                        title=title_val,
                                        bullets=[str(b) for b in s.get("bullets", [])]
                                        or [str(s.get("summary") or "Strategic topic insights and deliverables.")],
                                    )
                                ],
                            ),
                            speaker_notes=str(s.get("speaker_notes") or ""),
                        )
                    )
        try:
            return DynamicPresentationPlan(
                title=str(plan_dict.get("title") or presentation_title),
                subtitle=plan_dict.get("subtitle") if isinstance(plan_dict, dict) else None,
                date=plan_dict.get("date", "15JAN2025") if isinstance(plan_dict, dict) else "15JAN2025",
                audience=plan_dict.get("audience", "") if isinstance(plan_dict, dict) else "",
                slides=repaired_slides,
            )
        except Exception as e2:
            raise DynamicPlanningError(f"Failed to construct valid DynamicPresentationPlan: {e2}") from e
