# Guidelines — HLD QBR Template

Extracted from the template's own "FORMATTING HELP" section (`slide_41`–`slide_50`), the template
author's in-deck style guide. All Guide-Only — never cloned into a generated deck.

## Typography (`slide_44`, "TITLE IS 22 PT VERDANA BOLD UPPERCASE")

- Title: 22 pt Verdana Bold, UPPERCASE.
- Sub-headline: 18 pt Verdana.
- First level body text: 18 pt Verdana, Gray 1 (or another theme color if it functions as a title).
- Use PowerPoint's "Promote/Demote" buttons to change bullet level — never the bullet on/off toggle.
- Spacing/alignment are preset by the template; if text overflows, reduce line/paragraph spacing first.
- If still necessary, reduce font size down to 12 pt — never smaller; prefer splitting content across
  a duplicated slide instead (see `guardrails.md`).
- Theme fonts (`ppt/theme/theme1.xml`): major/heading font **Georgia**, minor/body font **Verdana**.
  In practice title placeholders render Verdana Bold per the rule above.

(Machine-readable copy: `llm/hld_qbr_guidelines.py`'s `TYPOGRAPHY` dict.)

## Color usage (`slide_43`, "BRAND APPROVED COLORS")

- Default slide background is white.
- Normal body text is UPS dark brown tone (`accent3`, `#330000`); **UPS Blue is the default emphasis
  color** for bullets/highlights, but other theme colors may be used as needed.
- Title and subtitle text is UPS dark brown tone.
- **Only use the colors defined in this template's theme** — never PowerPoint's generic "Standard
  Colors" row. See `design-tokens.json` for exact values.

(Machine-readable copy: `llm/hld_qbr_guidelines.py`'s `BRAND_COLORS` / `COLOR_USAGE_RULES`;
`core/builders/hld_qbr_builder.py`'s `TEMPLATE_SERIES_COLORS` for the exact RGB tuples used when
rendering real chart series.)

## Tables (`slide_47`–`slide_49`, "Sample tables created using the table function")

- Multiple parallel tables with the same column schema (e.g. one per region/site) are an accepted
  pattern — keep each table's row/column structure identical across instances.
- Headers can be bottom-aligned; row titles go in the first column.
- Cells may wrap onto two-plus lines; use this instead of shrinking font size.
- A single cell can be highlighted with a solid fill to call out a value. The template's own example
  (`slide_49`) captions this as "filling with lt. green" but the cell actually uses `accent4` (UPS
  Gold, `#FFBE00`) — treat the *technique* as the rule, not the caption's color name.
- Table cells may carry inline Wingdings checkmark glyphs (character U+F0FC, seen on `slide_48`) as a
  lightweight "done/selected" marker — a per-cell content choice, not an icon-catalog shape.

## Process flow diagrams (`slide_50`)

- Preferred process-flow color is **UPS Gray 4**; highlight one segment with a secondary accent color
  when a single stage needs emphasis.
- If more than one color is needed, use a left-to-right darkening gradient of grays before introducing
  a second brand hue.
- Segment titles are initial-cap and left-aligned.

## Charts (`slide_45`, `slide_46`, `slide_51`, `slide_52`)

- Prefer monochromatic secondary-color families for charts/graphs/tables rather than mixing many
  unrelated hues.
- Always source/cite external stats used in a callout (the template's own example on `slide_46` cites
  an external UPS consumer survey — a demonstration of the *sourcing convention*, not real content).
- Chart samples on `slide_51`/`slide_52` are real embedded chart graphic frames (pie + bar/line) — use
  these as the reference chart style. `core/builders/hld_qbr_generic_builder.py`'s `_render_chart()`
  reuses the template's own chart part (cloned, then `chart.replace_data()`), so the chart's native
  style/theme-color wiring survives automatically — never rebuild a chart's styling from scratch.

## Section dividers

- Section header slides (layouts `9_Section Header`, `1_Section Header_No Image`,
  `2_Section Header_No Image_Blue BG`) carry only a title — no body content. Used at `slide_01`
  (Today's Discussion — a content slide on this layout, not a pure divider), `slide_11`, `slide_21`,
  `slide_24`, `slide_28` (section dividers inside the real deck), `slide_31` ("Section: Optional
  Slides"), and `slide_41` ("Section: Formatting Help"). All "Divider"-category slides are excluded
  from `layout_capability_catalog.json` — they are structural narration beats, not content containers.
