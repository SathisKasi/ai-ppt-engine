# Slide Inventory — HLD QBR Template (60 slides, `slide_00`–`slide_59`)

Legend for **Category** (matches `metadata/slide_NN.json`'s `category` field and
`templates/build_hld_qbr_layout_catalog.py`'s filtering): `Mandatory` = always included structurally
(cover/agenda/closing) · `Core`/`Optional`/`Alternate` = pickable content layouts in
`layout_capability_catalog.json` · `Divider` = section-break slide, excluded from the catalog · `Guide-
Only` = brand/icon reference appendix, excluded from the catalog, never customer-facing.

Numbering here is 0-indexed (`slide_00`–`slide_59`), matching `templates/hld_qbr_assets/metadata/` and
`inventory/slide_index.json`. **Title column:** generic, structure-derived labels (layout name + slot/
table/chart/repeat-group counts via `templates/build_hld_qbr_layout_catalog.py`'s `describe_structure()`)
— never the template's own sample/placeholder heading text. The "Sample content" the ORIGINAL template
ships with (e.g. "Organizational Structure", "Gemba Walk Summary") is historical/human-reference-only
information and is never available to the generation pipeline
(`layout_capability_catalog.json` version 2.0+ carries no title/sample-text fields at all).

| Slide | Title (generic, structure-derived) | Layout | Category | Originally sampled as (human reference only) |
|---|---|---|---|---|
| `slide_00` | Blank — 3 text slot(s) | Blank | Mandatory | (Cover) |
| `slide_01` | 9_Section Header — 2 text slot(s) | 9_Section Header | Mandatory | Today's Discussion (Agenda) |
| `slide_02` | Title Only — 11 text slot(s) | Title Only | Core | Organizational Structure |
| `slide_03` | Title Only — 1 text slot(s) | Title Only | Mandatory | Executive Summary |
| `slide_04` | Title Only — 7 text slot(s) | Title Only | Core | Previous Quarter Achievements |
| `slide_05` | Title Only — repeat-group of 3 (2 slot(s) each), 1 text slot(s) | Title Only | Core | Customer Priorities (Format 1) |
| `slide_06` | Title Only — 7 text slot(s) | Title Only | Alternate | Customer Priorities (Format 2) |
| `slide_07` | Title Only — 7 text slot(s) | Title Only | Core | UPS Healthcare Priorities |
| `slide_08` | Title Only — 1 text slot(s) | Title Only | Guide-Only | Supplemental Gallery Pointer (6 thumbnail images) |
| `slide_09` | Title Only — table (5x8), 2 text slot(s) | Title Only | Core | Action Item Tracker |
| `slide_10` | Title Only — 3 text slot(s) | Title Only | Optional | Voice of the Customer |
| `slide_11` | 1_Section Header_No Image — 1 text slot(s) | 1_Section Header_No Image | Divider | Section: Performance Management |
| `slide_12` | Title Only — table (3x13), 2 text slot(s) | Title Only | Core | Key Performance Indicator Dashboard (2 tables) |
| `slide_13` | Title Only — chart (COLUMN_CLUSTERED), 2 text slot(s) | Title Only | Core | Inbound Summary / Operational Chart |
| `slide_14` | Title Only — chart (COLUMN_CLUSTERED), 3 text slot(s) | Title Only | Core | Outbound Summary |
| `slide_15` | Title Only — chart (COLUMN_CLUSTERED), 3 text slot(s) | Title Only | Core | Inventory Accuracy |
| `slide_16` | Title Only — chart (COLUMN_CLUSTERED), 3 text slot(s) | Title Only | Core | Customer Forecast Accuracy |
| `slide_17` | Title Only — chart (COLUMN_CLUSTERED), 3 text slot(s) | Title Only | Core | Space Utilization |
| `slide_18` | Title Only — chart (COLUMN_CLUSTERED), 3 text slot(s) | Title Only | Core | Spend Summary |
| `slide_19` | Title Only — chart (COLUMN_CLUSTERED), 3 text slot(s) | Title Only | Optional | Accounts Receivable Updates |
| `slide_20` | Title Only — 1 text slot(s) | Title Only | Core | Master Data Management KPIs |
| `slide_21` | 1_Section Header_No Image — 1 text slot(s) | 1_Section Header_No Image | Divider | Section: Continuous Improvement |
| `slide_22` | Title Only — table (2x5), 1 text slot(s) | Title Only | Core | Gemba Walk Summary |
| `slide_23` | Title Only — table (5x9), 1 text slot(s) | Title Only | Core | CI Activity Tracker |
| `slide_24` | 1_Section Header_No Image — 1 text slot(s) | 1_Section Header_No Image | Divider | Section: Quality Management System |
| `slide_25` | Title Only — 6 text slot(s) | Title Only | Core | Quality Organizational Structure |
| `slide_26` | Title Only — table (4x2), 3 text slot(s) | Title Only | Core | Non-Conformance Review |
| `slide_27` | Title Only — table (5x8), 2 text slot(s) | Title Only | Core | Non-Conformance Tracker |
| `slide_28` | 1_Section Header_No Image — 1 text slot(s) | 1_Section Header_No Image | Divider | Section: Next Steps |
| `slide_29` | Title Only — table (2x4), 1 text slot(s) | Title Only | Core | Next Steps |
| `slide_30` | Blank — 2 text slot(s) | Blank | Mandatory | (Closing) |
| `slide_31` | 2_Section Header_No Image_Blue BG — 1 text slot(s) | 2_Section Header_No Image_Blue BG | Divider | Section: Optional Slides |
| `slide_32` | Title Only — table (6x6), 2 text slot(s) | Title Only | Optional | KPI Scorecard Quarterly Summary (Format A) |
| `slide_33` | Title Only — table (7x6), 2 text slot(s) | Title Only | Optional | KPI Scorecard Quarterly Summary (Format B) |
| `slide_34` | Blank — 8 text slot(s) | Blank | Optional | Performance Summary Callouts |
| `slide_35` | Title Only — table (3x8), 3 text slot(s) | Title Only | Optional | Value-Centric Approach |
| `slide_36` | Title Only — chart (COLUMN_CLUSTERED), repeat-group of 3 (2 slot(s) each), 2 text slot(s) | Title Only | Optional | Financial Value (3-Up Charts) |
| `slide_37` | Title Only — 4 text slot(s) | Title Only | Optional | Cost / Data / Trend Analysis (Format A) |
| `slide_38` | Title Only — 4 text slot(s) | Title Only | Optional | Cost / Data / Trend Analysis (Format B) |
| `slide_39` | Title Only — 7 text slot(s) | Title Only | Optional | Forward Looking Roadmap |
| `slide_40` | Title Only — 3 text slot(s) | Title Only | Optional | Technology & Digital Enablement |
| `slide_41` | 2_Section Header_No Image_Blue BG — 1 text slot(s) | 2_Section Header_No Image_Blue BG | Guide-Only | Section: Formatting Help |
| `slide_42` | Title Only — 2 text slot(s) | Title Only | Guide-Only | Guardrails |
| `slide_43` | Title Only — 5 text slot(s) | Title Only | Guide-Only | Brand Approved Colors |
| `slide_44` | Title Only — 3 text slot(s) | Title Only | Guide-Only | Typography Hierarchy |
| `slide_45` | Title Only — chart (DOUGHNUT), 5 text slot(s) | Title Only | Guide-Only | 4-Up Mini Data Visualizations |
| `slide_46` | Title Only — 6 text slot(s) | Title Only | Guide-Only | Data Visualization Callout Badges |
| `slide_47` | Title Only — table (3x5), 1 text slot(s) | Title Only | Guide-Only | Sample Tables (Multi-Column, x4) |
| `slide_48` | Title Only — table (8x9), 1 text slot(s) | Title Only | Guide-Only | Sample Table (Condensed) |
| `slide_49` | Title Only — table (5x4), 1 text slot(s) | Title Only | Guide-Only | Sample Table (Data Matrix) |
| `slide_50` | Title Only — 10 text slot(s) | Title Only | Guide-Only | Process Flow Comparison |
| `slide_51` | Title Only — chart (COLUMN_CLUSTERED), 1 text slot(s) | Title Only | Guide-Only | Chart Samples (Full Width) |
| `slide_52` | Title Only — chart (LINE), 1 text slot(s) | Title Only | Guide-Only | Sample Graphs (Line Charts, x2) |
| `slide_53` | Title Only — no fillable content | Title Only | Guide-Only | (untitled — leftover vector icon shapes) |
| `slide_54` | Title Only — 1 text slot(s) | Title Only | Guide-Only | Vector Icon Library 1 (1-60) |
| `slide_55` | Title Only — 1 text slot(s) | Title Only | Guide-Only | Vector Icon Library 2 (61-120) |
| `slide_56` | Title Only — 1 text slot(s) | Title Only | Guide-Only | Vector Icon Library 3 (121-183) |
| `slide_57` | Title and Content — 1 text slot(s) | 1_Title and Content | Guide-Only | Harvey Ball Icons (27 icons, 8 unique) |
| `slide_58` | Title Only — 4 text slot(s) | Title Only | Guide-Only | New Icons (Outline Set, ~10 icons) |
| `slide_59` | Title Only — 1 text slot(s) | Title Only | Guide-Only | New Icons (Logistics Set, ~55 icons) |

**Generic-title note (2026-10-04):** every `title` in `metadata/slide_NN.json` / `inventory/
slide_index.json` / `metadata/manifest.json` is now computed purely from layout name + structural
facts (`templates/build_hld_qbr_layout_catalog.py`'s `describe_structure()` — table/chart dimensions,
repeat-group counts, plain text-slot counts) rather than transcribed from the template's own sample/
placeholder heading text. This replaces an earlier pass where `SLIDE_CATALOG` in
`templates/extract_hld_qbr_assets.py` hand-carried topic-specific titles like "Organizational
Structure" or "Gemba Walk Summary" for every slide — the exact hardcoded-topic-name pattern this
project's generation pipeline was built to avoid, just one layer removed (human-facing metadata rather
than the runtime catalog, which already excluded titles entirely as of `layout_capability_catalog.json`
version 2.0). The "Originally sampled as" column above is kept purely as historical/human-reference
context (what the BioRidge Pharma example deck called that slide) and is never read by any code path.
`slide_53`/`slide_58`/`slide_59` in particular were previously mis-transcribed even in that older,
topic-named scheme ("Harvey Ball Icon Palette", "New Icons (Logistics & Tech)", "New Icons (Customer
Care)" — heuristic guesses, not the deck's real content); that correction is now moot since no slide's
title is transcribed from the deck at all, generic or otherwise.

## Notes on the repeated facility-summary framework (`slide_14`–`slide_20`, `slide_37`)

These share one fixed analysis skeleton — not sample data:

```
Facility name or location
[chart/KPI visual area]           Q1 INSIGHTS
What changed
Why
Missed KPIs
RCA
CAPA
What's next
```

Only "Facility name or location" is a real substitution field; the six framework labels and "Q1
INSIGHTS" chart-title are fixed design. Per this project's grounding policy, even these fixed labels
are blanked on clone and only ever re-populated from LLM-returned, source-grounded text — see
`core/builders/hld_qbr_generic_builder.py`'s `_clear_template_text()`.
