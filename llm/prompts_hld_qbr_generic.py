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
You are assembling a slide outline for an existing, fixed PowerPoint template.
You cannot create new slide designs — you only decide WHICH of the template's
existing slide capabilities to use and WHAT already-extracted content feeds each
one. Match content to a slide by its STRUCTURE (a table needs tabular data, a
repeat-group with N max items needs content with at most N parallel entries,
a chart needs a numeric series) — never by whether the document uses the same
words as anything about the slide. A slide with no genuinely fitting content
must be left unpicked rather than force-fed a weak match.
"""

HLD_QBR_OUTLINE_PROMPT = """\
LAYOUT CAPABILITY CATALOG (structural only — slide_id, slot kinds/maxChars,
table/chart schema, repeat-group max item counts; no topic names):
{compact_catalog_json}

EXTRACTED CONTENT MODEL (everything genuinely found in the source document —
atomic items with an id, type, text, attributes, and source_reference; this is
the ONLY content you may reference):
{content_model_json}

These slide_ids are always included regardless of your picks (structural
slides — cover/agenda/closing — handled separately, do not pick them here):
{always_include_slide_ids}

Requested number of CONTENT slides: {requested_slide_count}

Task: choose up to {requested_slide_count} slide_ids (from the catalog above,
excluding the always-included ones) that have genuinely fitting content, and
for each, list the content_item ids (from the content model above) that will
feed it. Prefer slides where the structural fit is strong. Do not invent a
content_item id that isn't in the content model above. Do not pick the same
content_item id for more than one slide unless the slide's repeat-group
structure genuinely calls for reusing a broader theme across sub-items.

Also provide: a concise presentation_title, a facility_name if the source
names a specific site/location, and a date if the source states one
(otherwise leave facility_name/date as empty strings).

Return ONLY valid JSON:
{{
  "presentation_title": "...",
  "facility_name": "...",
  "date": "...",
  "picks": [
    {{"slide_id": "...", "content_item_ids": ["C001", "C004"]}}
  ]
}}
"""


def build_hld_qbr_outline_prompt(
    *,
    compact_catalog: List[Dict[str, Any]],
    content_model_json: str,
    always_include_slide_ids: List[str],
    requested_slide_count: Optional[int],
) -> str:
    return HLD_QBR_OUTLINE_PROMPT.format(
        compact_catalog_json=json.dumps(compact_catalog, ensure_ascii=False),
        content_model_json=content_model_json,
        always_include_slide_ids=json.dumps(always_include_slide_ids),
        requested_slide_count=requested_slide_count if requested_slide_count else "AI's discretion",
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
You write the actual slide text for a batch of already-chosen template slides.
You may ONLY use facts from the content items you are given for each slide —
never invent names, metrics, dates, or claims. Respect every maxChars limit
(write shorter, not truncated-looking, text) and never exceed a repeat-group's
max item count (fewer items than the max is fine and expected when the
content doesn't support more).
"""

HLD_QBR_FILL_PROMPT = """\
For EACH slide below, write its content using ONLY the content items listed
for that slide. Sample_text values (if present) show the ORIGINAL template's
placeholder content purely for sizing/format reference — never reuse those
names/numbers/wording as if they were real; they are not part of your source.
If a slot's sample_text contains multiple lines (e.g. a quote on one line and
an attribution on another), your replacement value should use the same "\\n"
line structure so each part lands in its own line.

SLIDES TO FILL:
{slides_json}

For each slide, return:
- "slide_id": matching the input
- "title": text for its title slot, if it has one (omit otherwise)
- "slot_values": {{slot_id: text}} for every simple text slot you filled
  (respect each slot's max_chars)
- "repeat_items": for slides with a repeat_group, a list of objects
  {{item_slot_id: text, ...}}, at most max_items entries, one object per
  card/badge instance
- "table_headers" / "table_rows": for slides with a table slot, if the
  catalog's table_schema implies fixed headers reuse them verbatim in
  table_headers; table_rows is a list of rows, each row a list of strings
  matching the header count
- "chart_categories" / "chart_series": for slides with a chart slot,
  chart_categories is a list of category labels, chart_series is a list of
  {{"name": "...", "values": [numbers]}}

Omit any key that doesn't apply to a given slide. Omit a slide entirely from
your response only if NONE of its assigned content items turned out to be
usable (should be rare, since matching already happened upstream).

Return ONLY valid JSON:
{{
  "slides": [
    {{"slide_id": "...", "title": "...", "slot_values": {{}}, "repeat_items": [],
      "table_headers": [], "table_rows": [], "chart_categories": [], "chart_series": []}}
  ]
}}
"""


def build_hld_qbr_fill_prompt(*, slides_payload: List[Dict[str, Any]]) -> str:
    return HLD_QBR_FILL_PROMPT.format(slides_json=json.dumps(slides_payload, ensure_ascii=False))
