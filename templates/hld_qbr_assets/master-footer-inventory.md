# Master and Footer Inventory

The source `.potx` package contains 2 slide masters and 19 slide layouts in total, but this deck's 60
slides (`slide_00`–`slide_59`) only actually use 6 of those 19 layouts, all inherited from 1 of the 2
masters — the other master/layouts exist in the file but are unused by any slide. The original
PowerPoint remains the editable source; this file is a structural reference only.

## Masters

- `slideMaster1` (used): slide-number footer element.
- `slideMaster2` (unused by any slide in this deck).

## Layouts used (by `slide_id`)

| Layout | Master | Used by |
|---|---|---|
| "Blank" | `slideMaster1` | `slide_00`, `slide_30`, `slide_34` |
| "9_Section Header" | `slideMaster1` | `slide_01` |
| "Title Only" | `slideMaster1` | `slide_02`–`slide_09`, `slide_10`, `slide_12`–`slide_20`, `slide_22`, `slide_23`, `slide_25`–`slide_27`, `slide_29`, `slide_32`–`slide_40`, `slide_42`–`slide_56`, `slide_58`, `slide_59` |
| "1_Section Header_No Image" | `slideMaster1` | `slide_11`, `slide_21`, `slide_24`, `slide_28` |
| "2_Section Header_No Image_Blue BG" | `slideMaster1` | `slide_31`, `slide_41` |
| "1_Title and Content" | `slideMaster1` | `slide_57` |

(Cross-reference `inventory/slide_index.json`'s `layout` field per slide, or each slide's own
`metadata/slide_NN.json`'s `slide_layout_name`, for the authoritative per-slide mapping.)

## Rules

- Preserve the master footer and pagination treatment from the selected layout — never edit layout/
  master XML directly (see `quality-checklist.md`'s "Structural integrity" section).
- Section-divider layouts ("9_Section Header", "1_Section Header_No Image",
  "2_Section Header_No Image_Blue BG") intentionally omit body footer text — do not add it back.
- All "Divider"-category slides are excluded from `layout_capability_catalog.json` entirely; they are
  narrative beats the builder renders directly from `STRUCTURAL_ONLY_SLIDE_IDS`/narrative order, not
  content-fill targets.
