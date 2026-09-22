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
You are an Executive Presentation Architect for UPS Healthcare Logistics & Distribution QBRs.
Extract concrete operational facts, metrics, dollar values, percentages, facility names, and root-cause analyses from the source document to synthesize an authoritative, boardroom-ready Quarterly Business Review.

Core Rules:
1. DEEP FACTUAL GROUNDING: Every bullet, achievement, priority, and chart insight MUST cite real metrics, data points, or operational challenges from the source. No vague generalities or corporate fluff.
2. CHART INTEGRITY: Group metrics with identical units/scales (e.g. percentages together, unit counts together). For each chart, provide 2 concise analytical observations explaining trends, variances, and recommended CAPA.
3. TABULAR DATA: Preserve full multi-column datasets with clear headers and units.
4. STRICT JSON: Return ONLY a valid JSON object matching the requested schema. No conversational prose or markdown wrap.
"""

HLD_QBR_PRESENTATION_PLANNING_PROMPT = """\
Plan a boardroom-grade QBR presentation based strictly on the source document.

{guidelines}
{slide_count_guidance}

CONTENT ARCHETYPES:
- agenda_topics: 3-5 concise topic titles for Slide 2.
- executive_summary: 4-5 high-impact bullets formatted as 'UPPERCASE CATEGORY (2-4 words): Concrete analytical takeaway citing figures, percentages, and business impact' (e.g. 'ON-TIME SERVICE EXCELLENCE: OTIF improved from 91.8% to 97.2%, exceeding the 95% target.').
- priorities: up to 3 strategic pillars [{{"heading": "Max 3 words", "body": "2 sentences with operational friction, lever, and target."}}].
- achievements: up to 4 milestone strings with concrete figures/percentages from prior quarter.
- charts: [{{"chart_title": "Descriptive content-specific title", "categories": ["Cat1", ...], "series": [{{"name": "Series", "values": [12.3, ...]}}], "insights_title": "KEY OBSERVATIONS", "insights": ["2 concise analytical bullets with metrics & root-cause/CAPA"]}}]. (Never mix dissimilar scales like % and volume counts on the same axis).
- kpi_tables: [{{"table_title": "Descriptive content-specific title", "headers": ["Col 1 (Unit)", "Col 2"], "rows": [["Row1", "..."], ...]}}] for multi-column operational datasets.
- action_tracker: up to 4 operational rows [{{"project": "Initiative name", "owner": "Role title", "next_step": "Measurable action", "comment": "Rationale citing source data", "status": "Complete" | "In Progress" | "Delayed"}}].
- next_steps: up to 4 rows [{{"step": "Action", "date": "e.g. Q4 2026"}}].
- Optional if evidence exists: org_structure [{{"name", "role"}}], voice_of_customer {{"quote", "attribution"}}, gemba_walk [{{"area", "observation"}}], ci_tracker [{{"activity", "category", "status", "value", "comment"}}], nc_review_summary [total, assigned, closed, pct], nc_tracker [{{"period", "nc_id", "event", "due_date", "status"}}].

SLIDE HEADING RULES (CRITICAL):
Every slide heading below MUST be generated specifically for this presentation and content. Do NOT copy template names like 'PERFORMANCE MANAGEMENT UPDATES', 'CONTINUOUS IMPROVEMENT PROGRAM UPDATES', or 'TODAY'S DISCUSSION'.
- agenda_title: UPPERCASE heading for the agenda slide (e.g. 'TODAY\'S AGENDA', 'MEETING OVERVIEW & OBJECTIVES', 'QUARTERLY REVIEW AGENDA').
- executive_summary_title: UPPERCASE heading for the executive summary slide (e.g. 'EXECUTIVE SUMMARY: STRATEGIC & OPERATIONAL HIGHLIGHTS', 'EXECUTIVE OVERVIEW: KEY OUTCOMES & IMPACT').
- section_heading: A concise 4-7 word UPPERCASE heading for the performance/operations section divider slide. Must reflect the actual content domain (e.g. 'HEALTHCARE LOGISTICS PERFORMANCE REVIEW', 'QUARTERLY OPERATIONS INTELLIGENCE BRIEFING').
- achievements_title: UPPERCASE heading for the achievements slide (e.g. 'Q3 2026 OPERATIONAL MILESTONES', 'PRIOR QUARTER KEY ACHIEVEMENTS').
- priorities_title: UPPERCASE heading for the priorities slide (e.g. 'STRATEGIC PRIORITIES FOR 2026', 'OPERATIONAL EXCELLENCE FOCUS AREAS').
- action_tracker_title: UPPERCASE heading for the action tracker slide (e.g. 'OPEN ACTION ITEMS & ACCOUNTABILITY', 'ACTION REGISTER & OWNERS').
- ci_section_title: UPPERCASE heading for the continuous improvement section divider slide (e.g. 'CONTINUOUS IMPROVEMENT INITIATIVES & VALUE CREATION').
- quality_section_title: UPPERCASE heading for the quality management section divider slide (e.g. 'QUALITY MANAGEMENT & REGULATORY ASSURANCE').
- next_steps_title: UPPERCASE heading for the next steps slide (e.g. 'NEXT STEPS & TARGET TIMELINES', 'UPCOMING COMMITMENTS').


{content_model_section}
DOCUMENT ANALYSIS:
{content_analysis}

SOURCE CONTENT (ground all data strictly in this text):
{source_content}

METADATA:
- Title: {presentation_title} | Facility: {facility_name} | Audience: {audience} | Style: {style}

OUTPUT SPECIFICATION:
Return ONLY a single valid JSON object in this format (leave unused optional fields empty):
{{
  "presentation_title": "{presentation_title}",
  "facility_name": "{facility_name}",
  "date": "",
  "agenda_title": "AGENDA SLIDE HEADING (e.g. TODAY'S AGENDA)",
  "executive_summary_title": "EXECUTIVE SUMMARY HEADING",
  "section_heading": "CONTENT-SPECIFIC SECTION HEADING (uppercase, 4-7 words)",
  "achievements_title": "ACHIEVEMENTS SLIDE HEADING",
  "priorities_title": "PRIORITIES SLIDE HEADING",
  "action_tracker_title": "ACTION TRACKER SLIDE HEADING",
  "ci_section_title": "CONTINUOUS IMPROVEMENT SECTION HEADING",
  "quality_section_title": "QUALITY MANAGEMENT SECTION HEADING",
  "next_steps_title": "NEXT STEPS SLIDE HEADING",
  "agenda_topics": ["..."],
  "executive_summary": ["CATEGORY: Analytical bullet with metrics..."],
  "priorities": [{{"heading": "...", "body": "..."}}],
  "achievements": ["..."],
  "charts": [{{"chart_title": "...", "categories": [...], "series": [{{"name": "...", "values": [...]}}], "insights_title": "KEY OBSERVATIONS", "insights": [...]}}],
  "kpi_tables": [{{"table_title": "...", "headers": [...], "rows": [[...]]}}],
  "action_tracker": [{{"project": "...", "owner": "...", "next_step": "...", "comment": "...", "status": "In Progress"}}],
  "next_steps": [{{"step": "...", "date": "..."}}]
}}
"""


def _build_content_model_section(content_model_json: Optional[str]) -> str:
    """Optional Stage-1 traceable items: included only when available."""
    if not content_model_json:
        return ""
    return (
        "CONTENT MODEL (traceable fact items):\n"
        f"{content_model_json}\n\n"
    )


def _build_slide_count_guidance(requested_content_slide_count: Optional[int]) -> str:
    """Provides concise targeting for content slides (excluding mandatory Cover/Agenda/Executive Summary/Closing)."""
    if requested_content_slide_count is None:
        return "SLIDE TARGET: Populate all content archetypes supported by source evidence."
    return (
        f"SLIDE TARGET: Allocate EXACTLY {requested_content_slide_count} content slides across:\n"
        f"- 'charts' (1 slide per chart)\n"
        f"- 'kpi_tables' (1 slide per table)\n"
        f"- 'priorities' (1 slide if populated)\n"
        f"- 'achievements' (1 slide if populated)\n"
        f"- 'action_tracker' (1 slide if populated)\n"
        f"- 'next_steps' (1 slide if populated)\n"
        f"Total content slides: len(charts) + len(kpi_tables) + non-chart slides = {requested_content_slide_count}.\n"
        "(Cover, Agenda, Executive Summary, and Closing are added automatically).\n"
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

