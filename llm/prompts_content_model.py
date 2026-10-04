"""
llm/prompts_content_model.py — Stage 1 prompt: template-independent content extraction.

This prompt must never mention slides, layouts, or any specific template — its
only job is "what information actually exists in this document", so the
extraction layer stays reusable even if the presentation template changes.
"""
from __future__ import annotations

SYSTEM_ROLE_CONTENT_EXTRACTOR = """\
You are a meticulous document analyst. You extract exactly what is stated in a source
document into a structured list of atomic content items. You do not write slides, choose
layouts, or format a presentation — you only determine what information exists.

Rules:
1. Extract only facts, claims, and information genuinely present in the source text.
2. Never invent metrics, dates, people, organizations, quotes, or outcomes.
3. Prefer many small, specific items over few broad ones.
4. Preserve numbers/units exactly as stated in `attributes` when the item is a metric.
5. Include a `source_reference` hint (e.g. a page/section marker) whenever the source
   text makes one available; otherwise leave it as an empty string.
6. Identify relationships between items only when the source text itself implies them
   (e.g. a stated problem being addressed by a stated solution).
"""

CONTENT_MODEL_EXTRACTION_PROMPT = """\
Read the source document below and extract a Content Model: a flat list of atomic
content items plus any relationships the source itself implies between them.

Each content item must have:
- id: short stable id, e.g. "C001", "C002", ... (sequential)
- type: one of fact, claim, key_message, entity, person, organization, date, metric,
  process, step, problem, solution, benefit, risk, goal, outcome, comparison, quote,
  section (choose the closest fit; it is fine to reuse a type many times)
- text: the statement itself, in the source's own words/meaning
- attributes: an object for structured details (e.g. {{"value": 35, "unit": "%"}} for a
  metric); use {{}} when there is nothing structured to add
- source_reference: a page/section hint if available in the source, else ""

Do NOT require every category to appear — only extract what is genuinely present.
Do NOT skip content merely because it doesn't match a presentation template; this
extraction has no knowledge of any template.

SOURCE DOCUMENT:
{source_content}

Return ONLY valid JSON of the form:
{{
  "content_items": [ {{"id": "...", "type": "...", "text": "...", "attributes": {{}}, "source_reference": "..."}} ],
  "relationships": [ {{"from_id": "...", "to_id": "...", "type": "..."}} ]
}}
"""


def build_content_model_extraction_prompt(*, source_content: str) -> str:
    return CONTENT_MODEL_EXTRACTION_PROMPT.format(source_content=source_content)


# ---------------------------------------------------------------------------
# Reduce stage: merge/dedupe content items extracted independently from
# overlapping chunks of the same document (map-reduce extraction). Never
# invents new items — only merges near-duplicates the map stage produced
# because of chunk overlap, and may lightly reword for conciseness.
# ---------------------------------------------------------------------------

SYSTEM_ROLE_CONTENT_REDUCER = """\
You are a meticulous editor merging content items extracted independently from
overlapping chunks of the same source document. Your only job is deduplication —
you never invent new facts, metrics, people, or claims not already present in the
input list.
"""

CONTENT_MODEL_REDUCE_PROMPT = """\
The content items below were extracted independently from overlapping chunks of one
document, so the same fact may appear multiple times (reworded or verbatim) under
different ids. Merge duplicates/near-duplicates into a single item (keep the clearest
wording, keep the most specific source_reference and attributes), drop the redundant
copies, and keep every genuinely distinct item. Preserve each relationship, remapping
from_id/to_id to whichever surviving id now represents that item; drop a relationship
only if both its endpoints were duplicates of the same surviving item.

Do NOT add, infer, or invent any item not already present below. Do NOT drop a
genuinely distinct item merely to shorten the list.

MERGED CONTENT ITEMS (pre-dedupe):
{merged_content_model_json}

Return ONLY valid JSON of the same form:
{{
  "content_items": [ {{"id": "...", "type": "...", "text": "...", "attributes": {{}}, "source_reference": "..."}} ],
  "relationships": [ {{"from_id": "...", "to_id": "...", "type": "..."}} ]
}}
"""


def build_content_model_reduce_prompt(*, merged_content_model_json: str) -> str:
    return CONTENT_MODEL_REDUCE_PROMPT.format(merged_content_model_json=merged_content_model_json)
