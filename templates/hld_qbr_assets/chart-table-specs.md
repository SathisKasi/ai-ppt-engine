# Chart & Table Specs — HLD QBR Template

Structural reference only. Column/row **counts** below are what
`layout_capability_catalog.json`'s `table_schema`/`chart_schema` actually expose at runtime (`cols`,
`rows`, `category_count`, `series_count` — no header text or sample labels, per the catalog's
version-`2.0`, fully structural contract). The verbatim sample header names listed here are for human
orientation only and are never read by the planner or renderer.

## Real data tables found in the deck (by `slide_id`)

| Slide | Table | Columns (sample headers, for orientation only) | Notes |
|---|---|---|---|
| `slide_09` | Action Item Tracker | Project, Owner, Next Steps, Comment, Status | Blank sample rows are a ready-to-fill tracker pattern, not overflow. |
| `slide_12` | Operation highlights | Operation highlights, 1st Quarter, 2nd Quarter | Grouped-row table (section label row + metric rows). |
| `slide_12` | KPI table | KPI, Delivered/Committed/YTD \u00d7 2 quarters | 2-level header (quarter over Delivered/Committed/YTD). |
| `slide_22` | Gemba Walk Summary | Area, Observation | Multi-line observation cells — wrap, don't shrink font. |
| `slide_23` | CI Activity Tracker | CIP Activity, Category, Status, Annual Estimated Value, Comments | Keep the trailing totals row. |
| `slide_26` | Non-Conformance Review | Total NC Initiated, Total CAPAs Assigned, Total CAPAs Closed to Date, Percent Complete | Small KPI-style single-row table. |
| `slide_27` | Non-Conformance Tracker | Period, NC#, Event, Due Date, Status | |
| `slide_29` | Next Steps | Step description, Date (Optional) | Already fully generic sample. |
| `slide_32` | KPI Scorecard (Format A) | Quarterly, On-Time Receiving, On-Time Shipping, Inventory Accuracy, Shipment Accuracy, Comments | Optional-category layout. |
| `slide_33` | KPI Scorecard (Format B) | KPI, Target, Q1, Q2, Q3, Q4, Comments | Alternate to `slide_32` — same shape, transposed. |
| `slide_35` | Value-Centric Approach / KPI compliance | Operational KPI Targets, Industry Average, UPS Healthcare Results & Impact | See cost-avoidance formula below. |
| `slide_47` | Sample tables (\u00d74 regions) | Category, Amount, % | Formatting reference only (Guide-Only, excluded from the catalog). |
| `slide_48` | Sample tables (checkmark glyphs) | Row titles, Header 1\u20137 | Demonstrates inline-glyph status marker (Guide-Only). |
| `slide_49` | Sample tables (cell formatting) | (unlabeled), Header 1\u20134 | Demonstrates wrap + single-cell highlight-fill (Guide-Only). |

## Row/column overflow handling

Clone an existing data row's `<a:tr>` XML (carrying its fill/border/font styling) once per extracted
row via `core/builders/hld_qbr_builder.py`'s `_fill_table_rows()`, then replace cell text only; delete
unused sample rows. Never shrink font size to force-fit extra rows.

## Recovered business logic: KPI cost-avoidance formula (from `slide_35`'s speaker notes)

Not sample data — the reusable calculation methodology behind that slide's dollar "Annual Impact"
figures:

```
Impact = Volume x (Target - Industry Average) x Cost per Failure
```

Example given (On-Time Receiving): Customer volume 2,153 receipts x (99.5% UPS target - 97% industry
average = 2.5% gap) x $30 cost per failure = **$1,615** annual impact.

Cost-per-failure constants from the example (tune per engagement, not universal):

| KPI | Cost per failure |
|---|---|
| On-Time Receiving | $30 ($10 rehandling + $15 inventory delay/stockout + $5 admin/re-scheduling) |
| Shipment Accuracy | $45 |
| On-Time Shipping | $18 |
| Inventory Accuracy | $20 |
| Returns On-Time | $12 |

## Table status conventions found in the source deck (content, not layout)

`slide_48`/`slide_49` (both Guide-Only, excluded from the catalog) demonstrate two per-cell status
conventions, neither a slide-layout feature:

1. **Inline checkmark glyph** (`slide_48`): a Wingdings checkmark character (U+F0FC) typed directly
   into a cell — reproduce by typing the glyph in the Wingdings font, not by inserting a picture/icon.
2. **Single-cell highlight fill** (`slide_49`): one cell gets a solid background fill to draw attention
   to a value. Use an approved theme color (`design-tokens.json`), not the caption's literal color name.

## Charts (graphic frames, not tables)

- `slide_51` "CHART SAMPLES": one native chart graphic frame (pie-style) — style/font reference only.
- `slide_52` "SAMPLE GRAPHS": two native chart graphic frames — same purpose.
- Real chartable slides (e.g. `slide_13`, the Inbound/Operational chart) are populated via
  `core/builders/hld_qbr_generic_builder.py`'s `_render_chart()`: `CategoryChartData` replaces the
  cloned chart part's data in place, so the template's own color/font styling is inherited for free.
