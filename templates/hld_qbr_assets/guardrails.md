# Guardrails — HLD QBR Template

Adapted from the template's own "GUARDRAILS" slide (`slide_42`, Guide-Only — never cloned into a
generated deck; see `core/builders/hld_qbr_builder.py`'s `GUIDE_ONLY` exclusion and
`templates/build_hld_qbr_layout_catalog.py`'s `EXCLUDED_CATEGORIES`).

## Verbatim rules from the template's own "GUARDRAILS" slide

1. Do not import any slides that are not in the current HC (Healthcare) brand guidelines. Insert a new
   slide within the existing presentation and copy only the content over.
2. Product slide verbiage cannot be changed; the header can be customized but must remain one line.
3. Newly created product slides need to be approved by SME, product owners, or Seismic.
4. All claims must be sourced.
5. Per legal, customer logos or personal data cannot be used without written consent.
6. Translation services are not available — content other than English cannot be included.
7. Updates need to be provided at least 48 hours before the deadline; if the meeting/call is
   postponed, sales needs to inform PF ASAP with the new date (so PF can reschedule priorities).
8. Sales must provide PF with the final deck and indicate their changes within two business days after
   the meeting.

(Machine-readable copy: `llm/hld_qbr_guidelines.py`'s `CONTENT_GUARDRAILS`, injected into the LLM
system prompt via `build_llm_guidelines_prompt()`.)

## Derived rules for this project's generation pipeline

These follow from how the template actually ships (pre-filled with a real example account, BioRidge
Pharma) and from this project's architecture (`core/presentation_planner_hld_qbr_generic.py` +
`core/builders/hld_qbr_generic_builder.py`):

- **No sample/placeholder content from the template ever reaches a generated deck.** Every visible
  string (slide titles, agenda topics, table/chart values, card text) must come from the LLM's content
  fill stage, grounded in `llm.content_model_extractor.extract_content_model_full()`'s output — never
  from `layout_capability_catalog.json` (which, as of catalog version `2.0`, carries no `title` or
  `sample_text` fields at all — pure structure only: slot kinds, `max_chars`, table/chart
  row/column/series counts, repeat-group item counts). See
  `core/builders/hld_qbr_generic_builder.py`'s `_clear_template_text()` — every cloned slide has its
  sample text/table cells blanked before any generated value is written, and an unfilled chart
  placeholder is removed outright rather than left showing its source workbook's sample series.
- **"Required content" / "Example" / "EXAMPLE" author-guidance labels are never surfaced or enforced.**
  The template author left several yellow-highlighted callout boxes with these labels (e.g. on
  `slide_05`/`slide_06`/`slide_07`/`slide_09`). `core/builders/hld_qbr_builder.py`'s `GUIDANCE_REGEX` /
  `_strip_guidance_shapes()` identifies and removes this authoring-only text at render time; the
  catalog builder's `_slot_from_shape()` also refuses to turn a guidance-sticker shape into a fillable
  slot in the first place.
- **Structural framework labels are not sample content — table column headers and fixed section labels
  are part of the slide's design,** but per this project's "never trust template text" fix, even these
  are now blanked on clone and only ever re-populated with LLM-returned, source-grounded header text
  (see `_render_table()` in `core/builders/hld_qbr_generic_builder.py` — `table_headers` always comes
  from the fill-stage response, never from the catalog's row/column counts alone).
- **The closing slide's legal/trademark footer (`slide_30`) is real, required legal copy**, not sample
  text — do not strip or edit it. (It still gets cloned with its sample run cleared like every other
  slide; if this legal text should always render verbatim, special-case it in
  `_render_closing()` rather than relying on any LLM round trip.)
- **Never select slides from the "Optional" (`slide_32`–`slide_40`) or "Guide-Only" (`slide_41`–
  `slide_59`) ranges as structural containers automatically.** `templates/build_hld_qbr_layout_catalog.py`'s
  `EXCLUDED_CATEGORIES = {"Divider", "Guide-Only"}` already drops dividers/guide-only pages from the
  catalog; "Optional"/"Alternate" category slides ARE included as pickable layouts (they're real,
  reusable slide structures) but must still only ever receive source-grounded content, same as "Core".
- **Row/column overflow:** never shrink font size to force-fit extra rows — see
  `core/builders/hld_qbr_builder.py`'s `_fill_table_rows()`, which scales font size by content length
  within a bounded range rather than arbitrarily, and prefer cloning an existing styled `<a:tr>` row
  over inventing new row XML.
