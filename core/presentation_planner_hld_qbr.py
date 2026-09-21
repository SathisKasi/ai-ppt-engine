"""
core/presentation_planner_hld_qbr.py — LLM Planner for the HLD QBR Template.

Calls the LLM once with the mined template guidelines + content analysis and
returns a validated HLDQBRPresentationPlan for core.builders.hld_qbr_builder.
"""
from __future__ import annotations

from typing import Optional

from pydantic import ValidationError

from llm.groq_client import GroqClient, JSONParseError
from llm.content_model_schemas import ContentModel
from llm.hld_qbr_schemas import HLDQBRPresentationPlan
from llm.prompts_hld_qbr import SYSTEM_ROLE_HLD_QBR_ARCHITECT, build_hld_qbr_planning_prompt
from llm.schemas import ContentAnalysis
from utils.logging_utils import get_logger
from utils.text_utils import truncate_text

logger = get_logger(__name__)

# Cover, Agenda, Executive Summary, and Closing are always rendered by the builder
# regardless of content — they are mandatory structural slides and must never be
# subtracted from the user's requested content-slide target.
MANDATORY_SLIDE_COUNT = 4
# Number of distinct optional content archetypes the schema supports (see
# llm/prompts_hld_qbr.py AVAILABLE CONTENT ARCHETYPES).
MAX_CONTENT_SLIDES = 12


class HLDQBRPlanningError(Exception):
    """Raised when HLD QBR presentation planning fails."""


def _format_compact_analysis(ca: ContentAnalysis) -> str:
    """Produces a concise, token-efficient text summary of content analysis."""
    parts = [f"Topic: {ca.main_topic}"]
    if ca.key_concepts:
        parts.append(f"Key Concepts: {'; '.join(ca.key_concepts[:6])}")
    if ca.statistics:
        parts.append(f"Statistics & Metrics: {'; '.join(ca.statistics[:6])}")
    if ca.sections:
        parts.append(f"Key Sections: {'; '.join(ca.sections[:8])}")
    if ca.processes:
        parts.append(f"Processes: {'; '.join(ca.processes[:3])}")
    highlights = getattr(ca, "executive_highlights", None)
    if highlights:
        parts.append(f"Highlights: {'; '.join(highlights[:4])}")
    if ca.summary:
        parts.append(f"Summary: {ca.summary[:300]}")
    return "\n".join(parts)


def plan_hld_qbr_presentation(
    client: GroqClient,
    content_analysis: ContentAnalysis,
    source_text: str = "",
    presentation_title: Optional[str] = None,
    facility_name: str = "",
    audience: Optional[str] = None,
    style: Optional[str] = None,
    language: Optional[str] = None,
    additional_instructions: Optional[str] = None,
    slide_count: Optional[int] = None,
    content_model: Optional[ContentModel] = None,
    max_source_chars: int = 6000,
) -> HLDQBRPresentationPlan:
    """Executes the HLD QBR Architect LLM call and returns a validated plan.

    ``slide_count`` is the user's requested number of CONTENT slides.
    Mandatory structural slides (Cover, Agenda, Executive Summary, Closing)
    are always included by the builder and are not subtracted from this count.
    """
    if not presentation_title or not presentation_title.strip():
        presentation_title = content_analysis.main_topic

    content_slide_target: Optional[int] = None
    if slide_count is not None:
        # slide_count is the target number of CONTENT slides
        content_slide_target = max(1, min(MAX_CONTENT_SLIDES, slide_count))

    # Adaptive source truncation to guarantee total requested tokens stay well under 8000
    effective_max_chars = max_source_chars
    if slide_count is not None and slide_count <= 5:
        effective_max_chars = min(max_source_chars, 4500)
    elif max_source_chars > 7000:
        effective_max_chars = 6000

    truncated_source = truncate_text(source_text, effective_max_chars)
    analysis_digest = _format_compact_analysis(content_analysis)

    prompt = build_hld_qbr_planning_prompt(
        content_analysis=analysis_digest,
        source_content=truncated_source,
        presentation_title=presentation_title,
        facility_name=facility_name or "",
        audience=audience or "Executive Leadership",
        style=style or "Executive Corporate",
        language=language or "English",
        additional_instructions=additional_instructions or "None",
        requested_slide_count=content_slide_target,
        content_model_json=content_model.compact_json() if content_model and content_model.content_items else None,
    )

    messages = [
        {"role": "system", "content": SYSTEM_ROLE_HLD_QBR_ARCHITECT},
        {"role": "user", "content": prompt},
    ]

    logger.info("Running HLD QBR Planning for '%s'", presentation_title)

    # Calculate adaptive max_tokens (e.g. 5-slide deck needs only ~400 tokens; 1536 is plenty)
    if content_slide_target is not None:
        calc_max_tokens = min(2048, max(1200, 800 + content_slide_target * 150))
    else:
        calc_max_tokens = 1536

    try:
        raw_data = client.chat_complete_json(messages=messages, temperature=0.3, max_tokens=calc_max_tokens)
    except JSONParseError as e:
        raise HLDQBRPlanningError(f"LLM returned invalid JSON during HLD QBR planning: {e}") from e
    except Exception as e:
        raise HLDQBRPlanningError(f"HLD QBR planning LLM call failed: {e}") from e

    plan_dict = raw_data.get("plan", raw_data) if isinstance(raw_data, dict) else raw_data

    try:
        plan = HLDQBRPresentationPlan.model_validate(plan_dict)
    except ValidationError as e:
        # Field-level repair: drop ONLY the offending field(s) so every other
        # correctly-populated section the LLM produced survives, instead of
        # discarding the entire plan for one bad field (e.g. voice_of_customer
        # returned as [] instead of a dict/null).
        logger.warning("HLDQBRPresentationPlan direct validation failed: %s — attempting field-level repair", e)
        if not isinstance(plan_dict, dict):
            raise HLDQBRPlanningError(f"Failed to construct valid HLDQBRPresentationPlan: {e}") from e
        repaired_dict = dict(plan_dict)
        last_err: ValidationError = e
        for _ in range(10):
            try:
                plan = HLDQBRPresentationPlan.model_validate(repaired_dict)
                break
            except ValidationError as retry_err:
                last_err = retry_err
                bad_fields = {err["loc"][0] for err in retry_err.errors() if err["loc"]}
                if not bad_fields or not bad_fields & repaired_dict.keys():
                    raise HLDQBRPlanningError(
                        f"Failed to construct valid HLDQBRPresentationPlan: {retry_err}"
                    ) from retry_err
                for field in bad_fields:
                    logger.warning("Dropping invalid field '%s' during HLD QBR repair (falls back to schema default)", field)
                    repaired_dict.pop(field, None)
        else:
            raise HLDQBRPlanningError(
                f"Failed to construct valid HLDQBRPresentationPlan after repeated repair attempts: {last_err}"
            ) from last_err

    populated_content_slides = _count_populated_content_slides(plan)
    logger.info(
        "HLD QBR Plan validated: %d agenda topics, %d org rows, %d action rows. "
        "Content slides populated: %d/%s (requested total incl. mandatory: %s).",
        len(plan.agenda_topics), len(plan.org_structure), len(plan.action_tracker),
        populated_content_slides,
        content_slide_target if content_slide_target is not None else "auto",
        slide_count if slide_count is not None else "auto",
    )
    return plan


def _count_populated_content_slides(plan: HLDQBRPresentationPlan) -> int:
    """Mirrors core.builders.hld_qbr_builder's per-section inclusion checks —
    used only for logging/telemetry, never to gate or trigger replanning."""
    return sum(
        bool(populated)
        for populated in (
            plan.org_structure,
            plan.achievements,
            plan.priorities,
            plan.action_tracker,
            plan.kpi_safety_quality or plan.kpi_operational,
            plan.voice_of_customer and plan.voice_of_customer.quote,
            plan.gemba_walk,
            plan.ci_tracker,
            plan.quality_org_structure,
            plan.nc_review_narrative or plan.nc_review_summary,
            plan.nc_tracker,
            plan.next_steps,
        )
    )
