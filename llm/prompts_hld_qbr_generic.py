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
Match source content to the most structurally appropriate slide layouts:
- Tables: Multi-attribute data rows and columns.
- Charts: Multi-category or multi-period numeric series comparisons. (Never use charts for isolated single metrics).
- Cards / Repeat Groups: 3-4 parallel items, capabilities, or metrics.
- Text Slides: Narrative, executive takeaways, or problem/solution.
Select distinct, high-impact topics and cite valid source content_item_ids.
Non-repeatable slide layouts may only be used once.
"""

HLD_QBR_OUTLINE_PROMPT = """\
AVAILABLE LAYOUTS:
{compact_catalog_json}

SOURCE CONTENT:
{content_model_json}
{exclude_block}
REQUESTED CONTENT SLIDES: {requested_slide_count}

INSTRUCTIONS:
1. Select {requested_slide_count} distinct, high-value topics from the source content.
2. Match each topic to the layout whose structure best fits its data shape (tabular -> table, multi-point numbers -> chart, cards -> repeat group, narrative -> text).
3. Assign valid content_item_ids to each pick (never leave empty).
4. Provide presentation_title, facility_name (if mentioned, else ""), and date (if mentioned, else "").
5. Provide agenda_topics: 4 to 6 high-level thematic pillars structuring the presentation narrative.

Return ONLY valid JSON:
{{
  "presentation_title": "...",
  "facility_name": "...",
  "date": "...",
  "agenda_topics": ["Pillar 1", "Pillar 2", "Pillar 3", "Pillar 4"],
  "picks": [
    {{"slide_id": "slide_XX", "content_item_ids": ["C001", "C002"]}}
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
You write concise, executive slide text for UPS Healthcare presentations using ONLY the assigned content.
Never invent metrics, names, or facts. Distribute assigned points across all designated text slots and cards.
"""

HLD_QBR_FILL_PROMPT = """\
Fill each slide using ONLY its assigned content items:
1. "title": Concise heading (<= 50 chars).
2. "slot_values": Provide non-empty text for every slot_id in "slots". Copy slot_ids exactly. Distribute distinct facts across slots.
3. "repeat_items": For repeat groups, provide an object for each card up to max_items.
4. "table_headers" & "table_rows": For table slides, provide headers and genuine data rows from the content (never invent rows).
5. "chart_categories" & "chart_series": If numeric series comparisons exist, provide category names and numeric values (numbers, never text). If no numeric series comparisons exist, set both to null.

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

