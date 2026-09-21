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
You are an elite Quarterly Business Review (QBR) presentation architect for UPS Healthcare
Logistics and Distribution. You write boardroom-ready, factual, on-brand QBR content for a
fixed, archetype-based template — you are NOT designing free-form layouts, you are filling in
specific, named slide types with real content extracted from the source document.

Your responsibilities:
1. FACTUAL GROUNDING: Every number, name, and claim must come from the provided source content.
   Never invent metrics, people, dates, or quotes that are not present or clearly implied.
2. CONTENT ENRICHMENT, NOT LITERAL MATCHING: Source documents rarely use QBR terminology
  verbatim — your job is to INTELLIGENTLY MAP whatever real content exists onto the
  closest-fitting QBR archetype rather than requiring an exact match. Read narrative,
  tables, dates, names, metrics, quotes, risks, and commitments together; do not require
  a source heading to match a template field. Examples: business
   segments/service lines -> priorities; named investments, launches, or milestones ->
   achievements; quantifiable facts (capacity, dollar amounts, counts) -> kpi_operational
   (leave target blank if no target is stated); calls-to-action or contact details -> next_steps;
   named individuals/roles -> org_structure. Only leave a field EMPTY if the source truly has
  NOTHING that could reasonably populate it — never leave it empty merely because the source
  doesn't use the exact QBR term. Never pad with generic filler unrelated to the source.
  Do not copy source section labels such as "KPI", "Gemba", or "Non-Conformance" into
  unrelated fields merely to satisfy the schema; infer the underlying facts and preserve
  their original meaning.
3. BRAND & GUARDRAIL COMPLIANCE: Follow the template's own brand and content guardrails exactly.
4. JSON EXCELLENCE: Output ONLY valid JSON matching the required schema — no commentary.
"""

HLD_QBR_PRESENTATION_PLANNING_PROMPT = """\
You are populating the HLD QBR Template (UPS Healthcare Quarterly Business Review format).
The source may be a natural account review, memo, or operating update with no explicit QBR
headings. Infer the fields from evidence in the full document; the source does not need to
announce that it contains priorities, KPIs, continuous improvement, or non-conformances.

{guidelines}

AVAILABLE SLIDE ARCHETYPES (populate every one the source content can reasonably support —
enrich/adapt real source content into the closest-fitting archetype rather than requiring a
literal QBR-terminology match; leave empty only when truly nothing in the source applies):
- agenda_topics: 3-7 concise thematic headings for the agenda slide, synthesized from the
  source storyline rather than copied mechanically from source headings.
- org_structure: up to 10 people as {{name, role}} for the organizational structure slide.
- achievements: up to 6 short prior-quarter milestone strings, in chronological order — derive
  from any named investments, launches, or milestones described in the source.
- priorities: up to 3 {{heading, body}} pillars for the customer priorities slide — derive from
  the document's main business segments, focus areas, or strategic themes.
- action_tracker: up to 7 rows of {{project, owner, next_step, comment, status}}.
- kpi_safety_quality / kpi_operational: up to 4/7 rows of {{label, actual, target}} for the KPI
  dashboard's two tables — derive from any quantifiable facts (capacity, dollar amounts, counts,
  percentages) in the source; leave target blank ("") if no target/benchmark is stated.
- voice_of_customer: a single {{quote, attribution}} if the source has a direct customer quote.
- gemba_walk_intro + gemba_walk: up to 4 rows of {{area, observation}}.
- ci_tracker: up to 7 rows of {{activity, category, status, value, comment}}.
- quality_org_structure: up to 5 people as {{name, role}}.
- nc_review_summary: exactly 4 values [total_nc_initiated, total_capas_assigned,
  total_capas_closed, percent_complete] if the source has non-conformance/CAPA summary data.
- nc_review_narrative: free-text narrative describing open non-conformances.
- nc_tracker: up to 7 rows of {{period, nc_id, event, due_date, status}}.
- next_steps: up to 4 {{step, date}} rows — derive from any calls-to-action, contact details, or
  "reach out"/"get started" language in the source; leave date blank ("") if none is given.

{slide_count_guidance}

{content_model_section}

CONTENT ANALYSIS FROM SOURCE DOCUMENT:
{content_analysis}

ORIGINAL SOURCE CONTENT (use ONLY these facts):
{source_content}

PRESENTATION REQUIREMENTS:
- Presentation Title: {presentation_title}
- Facility/Program Name: {facility_name}
- Audience: {audience}
- Style: {style}
- Language: {language}
- Additional Instructions: {additional_instructions}

Return ONLY valid JSON matching the HLDQBRPresentationPlan schema: presentation_title,
facility_name, date, agenda_topics, org_structure, achievements, priorities, action_tracker,
kpi_safety_quality, kpi_operational, voice_of_customer, gemba_walk_intro, gemba_walk,
ci_tracker, quality_org_structure, nc_review_summary, nc_review_narrative, nc_tracker,
next_steps, content_traceability.

For every one of the above fields you populate, add an entry to content_traceability
mapping that exact field name to the list of Content Model item ids (e.g. ["C001", "C003"])
that genuinely support it. If a field was populated purely from the raw source content with
no matching Content Model item, omit it from content_traceability rather than guessing an id.
"""


def _build_content_model_section(content_model_json: Optional[str]) -> str:
    """Stage-1 output (see core/content_model_extractor.py): typed, id-tagged facts
    extracted independently of this template, used here purely for traceability —
    the raw source content below remains the authoritative grounding text."""
    if not content_model_json:
        return (
            "CONTENT MODEL: not available for this run — ground every field directly in the "
            "ORIGINAL SOURCE CONTENT below and omit content_traceability entirely."
        )
    return (
        "CONTENT MODEL (typed facts extracted from the source, each with a stable id — cite "
        "these ids in content_traceability; do not cite an id unless the field is genuinely "
        "supported by that item):\n"
        f"{content_model_json}"
    )


def _build_slide_count_guidance(requested_content_slide_count: Optional[int]) -> str:
    """Content-only target: excludes the always-added Cover/Agenda/Closing and the
    auto-inserted section dividers, so the LLM is never pushed to fabricate data for
    mandatory-adjacent sections just to hit a total."""
    if requested_content_slide_count is None:
        return (
            "No specific slide count was requested — populate every archetype above that "
            "the source content can genuinely support, and leave the rest empty."
        )
    return (
        f"REQUESTED CONTENT SLIDE COUNT: {requested_content_slide_count}\n"
        "This count covers ONLY the optional archetypes listed above (org_structure, "
        "achievements, priorities, action_tracker, the KPI dashboard, voice_of_customer, "
        "gemba_walk, ci_tracker, quality_org_structure, nc_review, nc_tracker, next_steps — "
        "a maximum of 11 distinct content slides). It does NOT include the Cover, Agenda, and "
        "Closing slides or the section-divider slides, which are always added automatically by "
        "the renderer. Aim to populate approximately this many archetypes, choosing whichever "
        "are BEST SUPPORTED by real evidence in the source. NEVER invent, guess, or pad data for "
        "an archetype merely to reach this count — if the source genuinely supports fewer, "
        "populate only those and leave the rest empty. Fewer fully-grounded slides is always "
        "preferable to fabricated content."
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
