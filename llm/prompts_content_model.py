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
