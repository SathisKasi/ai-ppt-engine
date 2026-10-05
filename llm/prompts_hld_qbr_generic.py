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
You assemble a slide outline for a fixed PowerPoint template.
Decide WHICH TOPICS deserve a slide FIRST, ranked by importance -- THEN pick the catalog slide_id whose
structure best fits each chosen topic. Never pick a slide structure first and search for content to fill it.
Importance signals: more supporting content items, concrete metrics/numbers, risks/problems/decisions/outcomes,
or topics the source clearly emphasizes rank higher than a single minor, generic fact.
Match each selected topic to a slide by STRUCTURE (tables need tabular data, repeat-groups need parallel items,
charts need numeric series). If no ideal structure remains available for an important topic, place it in the
closest available plain-text slide instead of dropping it -- a text slide can always hold any topic as a fallback.
Every selected slide must cite valid content_item_ids from the source.
Each slide_id is single-use for one deck, EXCEPT slide_ids marked "repeatable": true (table/chart slides) —
those may be picked more than once if the source has multiple distinct tabular/numeric datasets, one per slide.
The TOTAL number of picks (including repeats) must still equal the requested slide count exactly.
"""

HLD_QBR_OUTLINE_PROMPT = """\
LAYOUT CAPABILITIES:
{compact_catalog_json}

CONTENT MODEL:
{content_model_json}

ALWAYS-INCLUDED SLIDES (handled separately, do NOT pick these):
{always_include_slide_ids}
{exclude_block}
REQUESTED CONTENT SLIDES: {requested_slide_count}

INSTRUCTIONS:
1. Review every topic in the content model. Rank them by importance: more supporting content items, concrete
   numbers/metrics, risks/problems/decisions/outcomes, or topics the source clearly emphasizes rank higher.
2. Select the {requested_slide_count} most important, distinct topics per that ranking. Do not cover the same
   topic twice unless it is genuinely large enough to need more than one slide.
3. For EACH selected topic, choose the catalog slide_id whose structure best fits that topic's content shape
   (tabular data -> table slide, numeric series -> chart slide, several parallel items -> repeat-group slide,
   narrative content -> text slide). If no ideal structure remains available, use the closest available
   plain-text slide instead of dropping the topic.
4. Assign matching content_item_ids to each slide. Use only IDs present in the content model. Never leave content_item_ids empty.
5. For repeat-groups (max_items > 1), assign enough distinct content items to utilize the layout capacity.
6. Every slide_id may be picked only ONCE, EXCEPT a slide_id marked "repeatable": true — pick that one
   again (once per extra pick) only if the source document has another distinct table/chart-worthy dataset
   for it. Never repeat a non-repeatable slide_id.
7. The TOTAL number of picks must equal {requested_slide_count} exactly -- if fewer high-importance topics
   exist than requested slides, include your next-most-important remaining topics rather than leaving slides unused.
8. Provide presentation_title, facility_name (if mentioned, else ""), and date (if mentioned, else "").

Return ONLY valid JSON:
{{
  "presentation_title": "...",
  "facility_name": "...",
  "date": "...",
  "picks": [
    {{"slide_id": "slide_XX", "content_item_ids": ["C001", "C002"]}}
  ]
}}
"""


def build_hld_qbr_outline_prompt(
    *,
    compact_catalog: List[Dict[str, Any]],
    content_model_json: str,
    always_include_slide_ids: List[str],
    requested_slide_count: Optional[int],
    exclude_slide_ids: Optional[List[str]] = None,
) -> str:
    count_str = f"exactly {requested_slide_count}" if requested_slide_count else "useful slides at AI discretion"
    exclude_block = ""
    if exclude_slide_ids:
        # Used only for the gap-fill retry: these slide_ids already have a good pick from an
        # earlier attempt, so the AI should cover NEW topics instead of repeating them (unless repeatable).
        exclude_block = (
            "\nALREADY-USED SLIDE IDS (already picked in an earlier pass \u2014 do NOT pick these again "
            "unless marked \"repeatable\" in the catalog above):\n"
            f"{json.dumps(sorted(set(exclude_slide_ids)), separators=(',', ':'))}\n"
        )
    return HLD_QBR_OUTLINE_PROMPT.format(
        compact_catalog_json=json.dumps(compact_catalog, separators=(',', ':'), ensure_ascii=False),
        content_model_json=content_model_json,
        always_include_slide_ids=json.dumps(always_include_slide_ids, separators=(',', ':')),
        exclude_block=exclude_block,
        requested_slide_count=count_str,
    )



def parse_outline_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Light normalization — tolerate missing keys, never raise."""
    return {
        "presentation_title": data.get("presentation_title") or "",
        "facility_name": data.get("facility_name") or "",
        "date": data.get("date") or "",
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
You write slide text for a batch of already-chosen PowerPoint template slides.
Rules:
- Use ONLY the assigned content items for each slide — never invent facts, names, metrics, or dates.
- FILL EVERY SLOT. Each "slot_id" in the slides payload is a separate visible text box that MUST receive text.
  A slide with empty slots is broken output. Map one content item (or part of one) per slot.
- For slides with many slots (e.g. slot_2 through slot_11), treat each as an independent bullet/card.
  Distribute the assigned content items across ALL the slots — do not cluster everything in slot_1 and slot_2.
- For repeat_groups: produce one object per content item, up to max_items. Never return an empty repeat_items list
  when there are assigned content items.
- Copy each slot_id back EXACTLY as given (e.g. "slot_3") — a single wrong character silently drops that slot.
- Respect each slot's max_chars. Write substantive phrases, not terse fragments.
"""

HLD_QBR_FILL_PROMPT = """\
Fill the slides below using ONLY the assigned content items.
Each slot_id in the "slots" array is a separate text box that MUST receive a non-empty value.
Never leave a slot empty if any assigned content can fill it.

KEY RULES:
1. DISTRIBUTE content items across slots — one distinct item (or fact) per slot.
   If a slide has slot_2 through slot_11, that is 10 separate text boxes: give each one its own text.
2. For "title", derive a concise heading from the assigned content (≤ 50 chars).
3. For repeat_groups: produce one {{item_slot_id: text}} object per content item, up to max_items.
4. For tables: use the column schema to write meaningful headers and data rows from the content.
5. For charts: if numeric data exists, provide "chart_categories" (strings) and "chart_series" with "name" and "values" (MUST be numbers: floats or ints, NEVER text). If no numeric data exists in assigned content, set BOTH "chart_categories": null and "chart_series": null.
6. "slot_values" is ONLY for the text slots listed in "slots". Copy slot_ids back EXACTLY ("slot_1", "slot_2", etc.) — values must be non-empty strings, never null.
7. Never reference or repeat template placeholder text.

SLIDES TO FILL:
{slides_json}

Return ONLY valid JSON — one entry per input slide:
{{
  "slides": [
    {{
      "slide_id": "slide_02",
      "title": "<concise heading from content>",
      "slot_values": {{"slot_1": "...", "slot_2": "...", "slot_3": "..."}},
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

