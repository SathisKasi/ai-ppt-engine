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

# Cover, Agenda, and Closing are always rendered by the builder regardless of
# content — they must never be counted against (or subtracted from) the
# requested content-slide target, so the planner is never pushed to invent
# data just to "fill" a mandatory slot.
MANDATORY_SLIDE_COUNT = 3
# Number of distinct optional content archetypes the schema supports (see
# llm/prompts_hld_qbr.py AVAILABLE SLIDE ARCHETYPES).
MAX_CONTENT_SLIDES = 11


class HLDQBRPlanningError(Exception):
    """Raised when HLD QBR presentation planning fails."""


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
    max_source_chars: int = 12000,
) -> HLDQBRPresentationPlan:
    """Executes the HLD QBR Architect LLM call and returns a validated plan.

    ``slide_count`` is the UI-facing TOTAL (matching the other templates'
    convention), which includes the 3 always-rendered mandatory slides
    (Cover/Agenda/Closing). It is converted here into a content-only target
    (mandatory subtracted out, capped at the schema's 11 optional archetypes)
    before being passed to the LLM, so the requested count never causes the
    planner to fetch/invent data for template sections not present in the
    source.

    ``content_model`` is the optional Stage-1 output (see
    core/content_model_extractor.py) — typed, id-tagged facts used here only
    for traceability (content_traceability). The raw source_text remains the
    authoritative grounding text regardless of whether this is supplied.
    """
    if not presentation_title or not presentation_title.strip():
        presentation_title = content_analysis.main_topic

    truncated_source = truncate_text(source_text, max_source_chars)
    analysis_json = content_analysis.model_dump_json(indent=2)

    content_slide_target: Optional[int] = None
    if slide_count is not None:
        content_slide_target = max(0, min(MAX_CONTENT_SLIDES, slide_count - MANDATORY_SLIDE_COUNT))

    prompt = build_hld_qbr_planning_prompt(
        content_analysis=analysis_json,
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

    try:
        raw_data = client.chat_complete_json(messages=messages, temperature=0.3, max_tokens=4096)
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
