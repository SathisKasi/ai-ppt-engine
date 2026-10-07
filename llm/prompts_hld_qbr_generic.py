"""
llm/prompts_hld_qbr_generic.py — Prompts for the generic, catalog-driven HLD
QBR planner (core/presentation_planner_hld_qbr_generic.py).

Two call types, mirroring the map-reduce / outline-then-fill pattern from
the reference architecture doc:
  1. Outline assignment: compact layout catalog (structure only, no sample
     text) + the FULL extracted ContentModel + requested slide count -> which
     catalog slide_ids to use and which content_item ids feed each one.
     Matching must be by STRUCTURAL FIT (a table needs tabular content, a
     3-item repeat group needs content with no more than 3 parallel items),
     never by whether the document happens to use the same business
     vocabulary as anything in the template.
  2. Content fill: for a batch of already-picked slides, the full catalog
     entry (real slots/maxChars/table/chart/repeat-group schema) + only the
     content items assigned to each -> actual slot text/table rows/chart
     series, respecting maxChars and repeat-group item counts as ceilings.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

SYSTEM_ROLE_HLD_QBR_OUTLINE = """\
You are an executive presentation architect for UPS Healthcare QBR decks.
Your objective is to design a high-density, strategic presentation from the source document.

Core Matching Principles:
1. STRATEGIC RELEVANCE: Prioritize substantive operational and performance topics (e.g. SLA delivery performance, cold-chain compliance, turnaround times, quality assurance, throughput, inventory accuracy, operational challenges & action plans). NEVER create a slide for isolated metadata, single dates, regulatory entity names (e.g. 'WHO', 'September 2025'), or minor daily fluctuations.
2. CAPACITY MATCHING: Match layout capacity to content depth:
   - For multi-slot or multi-card layouts (layouts with 4 to 10 slots or cards like slide_02), assign 4 to 8 distinct content_item_ids so every card/slot receives its own substantive, unique fact. NEVER assign only 1 or 2 items to a multi-slot/card layout.
   - For table layouts (has_table: true), assign items that contain structured metrics, tabular data, or multiple comparable attributes with values and benchmarks.
   - For chart layouts (has_chart: true), only assign if the content has multi-period or multi-category numeric series comparisons (e.g. quarterly metrics). Never pick charts for isolated single metrics.
3. DIVERSITY & NON-REPETITION: Select distinct topics across the source. Non-repeatable slide layouts may only be used once.
"""

HLD_QBR_OUTLINE_PROMPT = """\
AVAILABLE LAYOUTS:
{compact_catalog_json}

SOURCE CONTENT:
{content_model_json}
{exclude_block}
REQUESTED CONTENT SLIDES: {requested_slide_count}

INSTRUCTIONS:
1. Select {requested_slide_count} distinct, high-impact operational and performance topics from the source content.
2. Match each topic to the layout whose structure best fits its data shape (tabular metrics -> table, multi-point series -> chart, cards -> repeat group, narrative -> text).
3. CAPACITY MATCHING: Look at the "text_slots" and "repeats" capacity in AVAILABLE LAYOUTS:
   - If a layout has 6-10 text slots or cards, assign 5 to 8 distinct content_item_ids so all slots get unique substantive points.
   - If a layout has 3-4 cards/slots, assign 3 to 4 distinct content_item_ids.
   - Never assign only 1 or 2 items to multi-slot/card layouts.
4. CITE VALID IDS: Assign valid content_item_ids to each pick (never leave empty).
5. METADATA: Provide presentation_title (executive, professional title), facility_name (if mentioned, else ""), and date (if mentioned, else "").
6. AGENDAS: Provide agenda_topics: 4 to 6 high-level thematic pillars structuring the presentation narrative.

Return ONLY valid JSON:
{{
  "presentation_title": "...",
  "facility_name": "...",
  "date": "...",
  "agenda_topics": ["Pillar 1", "Pillar 2", "Pillar 3", "Pillar 4"],
  "picks": [
    {{"slide_id": "slide_XX", "content_item_ids": ["C001", "C002", "C003", "C004"]}}
  ]
}}
"""


def build_hld_qbr_outline_prompt(
    *,
    compact_catalog: List[Dict[str, Any]],
    content_model_json: str,
    always_include_slide_ids: Optional[List[str]] = None,
    requested_slide_count: Optional[int],
    exclude_slide_ids: Optional[List[str]] = None,
) -> str:
    count_str = f"exactly {requested_slide_count}" if requested_slide_count else "useful slides at AI discretion"
    exclude_block = ""
    if exclude_slide_ids:
        exclude_block = (
            f"\nDO NOT RE-PICK (already used): {json.dumps(sorted(set(exclude_slide_ids)), separators=(',', ':'))}\n"
        )
    return HLD_QBR_OUTLINE_PROMPT.format(
        compact_catalog_json=json.dumps(compact_catalog, separators=(',', ':'), ensure_ascii=False),
        content_model_json=content_model_json,
        exclude_block=exclude_block,
        requested_slide_count=count_str,
    )



def parse_outline_response(data: Any) -> Dict[str, Any]:
    """Light normalization — tolerate missing keys or non-dict input, never raise."""
    if not isinstance(data, dict):
        picks_source = data if isinstance(data, list) else []
        return {
            "presentation_title": "",
            "facility_name": "",
            "date": "",
            "agenda_topics": [],
            "picks": [
                {
                    "slide_id": p.get("slide_id"),
                    "content_item_ids": [i for i in (p.get("content_item_ids") or []) if isinstance(i, str)],
                }
                for p in picks_source
                if isinstance(p, dict) and p.get("slide_id")
            ],
        }
    raw_topics = data.get("agenda_topics")
    agenda_topics = [str(t).strip() for t in raw_topics if str(t).strip()] if isinstance(raw_topics, list) else []
    return {
        "presentation_title": data.get("presentation_title") or "",
        "facility_name": data.get("facility_name") or "",
        "date": data.get("date") or "",
        "agenda_topics": agenda_topics,
        "picks": [
            {
                "slide_id": p.get("slide_id"),
                "content_item_ids": [i for i in (p.get("content_item_ids") or []) if isinstance(i, str)],
            }
            for p in (data.get("picks") or [])
            if isinstance(p, dict) and p.get("slide_id")
        ],
    }


# ---------------------------------------------------------------------------
# Content fill
# ---------------------------------------------------------------------------

SYSTEM_ROLE_HLD_QBR_FILL = """\
You are an executive slide writer for UPS Healthcare Quarterly Business Reviews.
Your job is to transform assigned raw content items into rich, dense, executive-grade slide content.

Rules:
1. EXECUTIVE DEPTH & CONTENT ENRICHMENT: Write professional, high-impact business prose. Incorporate concrete quantitative metrics, targets, benchmarks, units, and operational context from the assigned items' text and attributes (e.g., "Achieved 99.4% on-time delivery against 98.0% SLA target across regional cold-chain lanes").
2. STRICT ZERO REPETITION: Every slot and card must express a DIFFERENT observation, metric, root cause, or business outcome. NEVER repeat the same phrase, sentence, or fragment across slots or cards.
3. GROUNDED IN TRUTH: Use ONLY the provided assigned content items and attributes. Never invent external facts or metrics.
4. FULL TABLE & CHART INTEGRATION:
   - For tables, populate EVERY column across all data rows (Metric Name, Operational Detail, Target, Actual, Status). Never leave cells empty ("") or output blank columns.
   - For chart slides ("has_chart": true), extract numerical metrics, percentages, or timeline comparisons from assigned items into "chart_categories" and "chart_series". Never leave charts empty or null on chart layouts.
"""

HLD_QBR_FILL_PROMPT = """\
Fill each slide using ONLY its assigned content items and attributes:
1. "title": Executive slide title (3-7 words, e.g. "Cold Chain SLA Performance & Quality Metrics"). Must synthesize the core business takeaway. Never use all-caps sentences or single generic words.
2. "slot_values": Provide substantive, non-repeating executive copy for every slot_id in "slots". Copy slot_ids exactly.
   - ZERO REPETITION: Every slot must be distinct.
   - ENRICHMENT: Integrate specific metrics, percentages, dollar amounts, targets, and operational details.
   - If there are more slots than assigned items, synthesize distinct operational facets (e.g. Performance Metric, Root Cause Analysis, Operational Impact, Strategic Next Step) rather than repeating text.
3. "repeat_items": For repeat groups, provide an object for each card up to max_items.
   - Each card object must contain keys matching item_slots (e.g. "item_slot_1": "Bold Metric / Key Takeaway", "item_slot_2": "Operational context, impact, and targets").
   - Ensure every card has unique content.
4. "table_headers" & "table_rows": For table layouts, populate headers matching column_count and provide data rows:
   - Every column must be populated with genuine data (Metric, Description, Target, Actual, Status). NEVER leave cells blank ("").
5. "chart_categories" & "chart_series":
   - For slides with "has_chart": true: You MUST extract numerical data points from assigned content items:
     * "chart_categories": list of strings for category/period labels (e.g. ["Q1", "Q2", "Q3", "Q4"] or ["Jan", "Dec"] or ["North Hub", "South Hub", "East Hub", "West Hub"]).
     * "chart_series": list of series objects with "name" and "values" containing numbers (e.g. [{"name": "Metric Name", "values": [98.2, 99.1, 99.5, 99.8]}]).
   - For slides with "has_chart": false: set both to null.

SLIDES TO FILL:
{slides_json}

Return ONLY valid JSON:
{{
  "slides": [
    {{
      "slide_id": "slide_XX",
      "title": "...",
      "slot_values": {{"slot_1": "...", "slot_2": "..."}},
      "repeat_items": [],
      "table_headers": null,
      "table_rows": null,
      "chart_categories": null,
      "chart_series": null
    }}
  ]
}}
"""


def build_hld_qbr_fill_prompt(*, slides_payload: List[Dict[str, Any]]) -> str:
    return HLD_QBR_FILL_PROMPT.format(
        slides_json=json.dumps(slides_payload, separators=(',', ':'), ensure_ascii=False)
    )

