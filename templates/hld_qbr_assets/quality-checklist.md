# Quality Checklist — HLD QBR Template

Checks for the asset-tree/catalog itself (not a per-run output checklist — the generation pipeline
enforces its own equivalent checks automatically; see "Automated equivalents" under each item).

## Content hygiene

- [ ] `layout_capability_catalog.json` carries no `title` or `sample_text` field anywhere (verify via
      `grep -i "sample_text\|\"title\"" templates/hld_qbr_assets/inventory/layout_capability_catalog.json`
      — should return nothing; catalog `"version"` must read `"2.0"` or later).
      *Automated equivalent:* `core/builders/hld_qbr_generic_builder.py`'s `_clear_template_text()`
      blanks every cloned slide's sample text/table cells before any generated value is written, and
      `scratch/hld_qbr/test_generic_pipeline_mock_e2e.py` asserts zero known template sample strings
      appear in a generated deck.
- [ ] `[CUSTOMER NAME]` / `[CLIENT NAME]` bracket tokens (seen in `slide_05`/`slide_06`/`slide_25`'s
      sample text) never appear in generated output — they are template authoring tokens, not data.
- [ ] "Required content" / "Example" / "EXAMPLE" author-guidance labels never reach the end user.
      *Automated equivalent:* `GUIDANCE_REGEX` / `_strip_guidance_shapes()` in
      `core/builders/hld_qbr_builder.py`, reused by the generic builder.
- [ ] `slide_30`'s legal/trademark footer text is preserved verbatim if rendered (it is required legal
      copy, not sample text) — currently blanked like all cloned text per the "never trust template
      text" policy; if this slide must always show real legal copy, special-case it explicitly.
- [ ] No slides from the Optional (`slide_32`–`slide_40`) or Guide-Only (`slide_41`–`slide_59`) ranges
      are selected via the catalog unless their category genuinely allows it — Guide-Only is already
      hard-excluded by `templates/build_hld_qbr_layout_catalog.py`'s `EXCLUDED_CATEGORIES`.

## Data integrity

- [ ] Every populated table matches its catalog `table_schema` column/row counts (`cols`/`rows`) — the
      fill-stage LLM response's `table_headers`/`table_rows` row length must match `cols`.
- [ ] Table row count changes are done by cloning an existing `<a:tr>` node, never by shrinking font
      size to fit more rows (`_fill_table_rows()`'s bounded font-scaling only, never below a floor).
- [ ] Any KPI cost-avoidance/impact dollar figures the LLM derives follow the
      `Impact = Volume x (Target - Industry) x Cost per Failure` formula in `chart-table-specs.md`
      when that specific framing is used, not arbitrary numbers.

## Brand/visual

- [ ] Only theme colors from `design-tokens.json` are used — no ad hoc RGB picks.
- [ ] Title text is Verdana Bold, 22pt, UPPERCASE; body text is Verdana, >=12pt (see `guidelines.md`).
- [ ] `llm/hld_qbr_guidelines.py`'s `BRAND_COLORS["accent5_teal"]` reads `"00857D"` (not `"008575"`) —
      must match `core/builders/hld_qbr_builder.py`'s `TEMPLATE_SERIES_COLORS` teal RGB exactly.

## Structural integrity (never touch)

- [ ] No edits to slide master/layout XML — only run text, table cells, and chart data are changed by
      the renderer.
- [ ] Section-divider slides (`slide_11`, `slide_21`, `slide_24`, `slide_28` in the core deck) are
      excluded from the fillable catalog entirely (`category: "Divider"`) — confirm no divider ever
      appears in `layout_capability_catalog.json`'s `slides` array.
- [ ] `templates/build_hld_qbr_layout_catalog.py` is re-run (`python templates/build_hld_qbr_layout_catalog.py`)
      after any change to `templates/hld_qbr_assets/metadata/*.json`, so the catalog never drifts from
      the underlying extraction.
