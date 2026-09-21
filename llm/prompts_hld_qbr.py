"""
llm/prompts_hld_qbr.py — Prompts for the HLD QBR Presentation Architect.

Instructs the LLM on the HLD QBR template's archetype catalog (see
HLD_QBR_TEMPLATE_PLAN.md §2) and injects the mined brand/guardrail knowledge
from hld_qbr_guidelines.py, so generated content stays on-brand without ever
needing the template's own "Formatting Help" appendix slides to be shown.
"""
from __future__ import annotations

from typing import Optional

from llm.hld_qbr_guidelines import build_llm_guidelines_prompt

SYSTEM_ROLE_HLD_QBR_ARCHITECT = """\
You are an expert QBR presentation architect for UPS Healthcare Logistics & Distribution.
Your role: Extract facts from the provided source document to populate named QBR slide archetypes.
Rules:
1. FACTUAL GROUNDING: Every metric, name, and claim must come directly from the source text. Never invent numbers or targets.
2. ADAPTIVE MAPPING: Map source content to the closest matching archetype (e.g. focus areas -> priorities; metrics -> kpi_operational; initiatives -> action_tracker; milestones -> achievements).
3. STRICT JSON: Output ONLY valid JSON matching the HLDQBRPresentationPlan schema with no conversational filler.
"""

HLD_QBR_PRESENTATION_PLANNING_PROMPT = """\
You are populating the HLD QBR Presentation Plan (UPS Healthcare Quarterly Business Review format).

{guidelines}

{slide_count_guidance}

AVAILABLE CONTENT ARCHETYPES:
- agenda_topics: 3-5 concise topic headings for the agenda slide.
- priorities: up to 3 pillars {{heading, body}} (heading MUST be concise: 2-3 words, max 20 chars; body is 1-2 sentences).
- achievements: up to 5 milestone strings (prior-quarter wins, launches, operational progress).
- operational_chart: clustered column chart comparing metrics across time periods or series: {{"chart_title": "Short title", "categories": ["Metric 1", ... up to 7], "series": [{{"name": "Previous Month", "values": [...]}}, {{"name": "Current Month", "values": [...]}}], "insights": ["Up to 5 bullet observations for the side panel"]}}. Use this when source contains monthly/quarterly comparative tables with observations.
- kpi_operational: up to 6 rows {{label, actual, target}} (quantifiable metrics; leave target \"\" if not stated).
- action_tracker: up to 5 rows {{project, owner, next_step, comment, status}}.
- next_steps: up to 4 rows {{step, date}} (action items, upcoming milestones; leave date \"\" if none).
- org_structure: up to 6 people as {{name, role}}.
- voice_of_customer: {{quote, attribution}} (only if explicit customer quote exists).
- gemba_walk: up to 4 rows {{area, observation}}.
- ci_tracker: up to 5 rows {{activity, category, status, value, comment}}.
- nc_review_summary: 4 values [total_nc, capas_assigned, capas_closed, percent_complete].
- nc_tracker: up to 5 rows {{period, nc_id, event, due_date, status}}.

{content_model_section}

DOCUMENT ANALYSIS:
{content_analysis}

SOURCE CONTENT (extract facts strictly from here):
{source_content}

PRESENTATION METADATA:
- Title: {presentation_title}
- Facility/Program: {facility_name}
- Audience: {audience} | Style: {style} | Language: {language}
- Additional Instructions: {additional_instructions}

OUTPUT FORMAT:
Return ONLY valid JSON matching HLDQBRPresentationPlan:
- presentation_title, facility_name, date, agenda_topics
- Populate ONLY the targeted content archetypes with real source evidence.
- Set all other archetype fields to empty ([] or \"\" or null).
"""


def _build_content_model_section(content_model_json: Optional[str]) -> str:
    """Optional Stage-1 traceable items: included only when available."""
    if not content_model_json:
        return ""
    return (
        "CONTENT MODEL (traceable fact items — cite ids in content_traceability where applicable):\n"
        f"{content_model_json}\n"
    )


def _build_slide_count_guidance(requested_content_slide_count: Optional[int]) -> str:
    """Provides concise targeting for content slides (excluding mandatory Cover/Agenda/Executive Summary/Closing)."""
    if requested_content_slide_count is None:
        return "SLIDE TARGET: Populate content archetypes that have strong evidence in the source; leave unsupported fields empty."
    return (
        f"SLIDE TARGET: Populate approximately {requested_content_slide_count} content archetype(s) with the strongest source evidence "
        "(e.g., priorities, achievements, operational_chart, kpi_operational, action_tracker, next_steps). Leave unsupported archetype fields empty. "
        "(Mandatory structural slides: Cover, Agenda, Executive Summary, and Closing are added automatically by the builder)."
    )


def build_hld_qbr_planning_prompt(
    *,
    requested_slide_count: Optional[int] = None,
    content_model_json: Optional[str] = None,
    **kwargs,
) -> str:
    return HLD_QBR_PRESENTATION_PLANNING_PROMPT.format(
        guidelines=build_llm_guidelines_prompt(),
        slide_count_guidance=_build_slide_count_guidance(requested_slide_count),
        content_model_section=_build_content_model_section(content_model_json),
        **kwargs,
    )

