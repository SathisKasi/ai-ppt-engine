# Image & Icon Rules — HLD QBR Template

This template ships four distinct icon sets, all inside the Guide-Only "FORMATTING HELP" tail
(`slide_53`–`slide_59`) — never customer-facing, never cloned into a generated deck.

## The four icon sets

| # | Slide(s) | Title in deck | Format | Count | Extracted to |
|---|---|---|---|---|---|
| 1 | `slide_54`\u2013`slide_56` | "ICONS 1\u201360" / "ICONS 61\u2013120" / "ICONS 121\u2013183" | Native PowerPoint vector shapes (grouped freeform paths) — **not** files in `ppt/media` | 183 (182 extracted — see `EXTRACTION_NOTES.md`'s known off-by-one) | `brand-assets/icons/set_1_icons_001_060/`, `set_2_icons_061_120/`, `set_3_icons_121_183/` (PNG crops, positionally named — these 183 shapes have **no thematic grouping** in the source template, so no semantic category name should ever be invented for them) |
| 2 | `slide_57` | "Harvey Ball Icons" | Real embedded SVG files, 8 unique source files (levels 10/20/25/35/50/65/85/100%) repeated as spare copies on-slide | 8 unique (27 on-slide instances) | `brand-assets/decorative-media/image44.svg`\u2013`image51.svg` |
| 3 | `slide_58` | "NEW ICONS" (outline set) | Raster PNG, embedded media; 2-tone outline/line icons grouped into 3 labeled categories (OUTCOMES, HOW WE WORK, EFFICIENCY) | ~10 | `media/` (real photo/PNG split — cross-reference `slide_58.json`'s picture shape list for exact files) |
| 4 | `slide_59` | "NEW ICONS" (logistics set) | Raster EMF, embedded media; solid UPS-blue/brown filled icons (shipping, devices, people, finance, quality/PPE) | ~55 | `brand-assets/decorative-media/*.emf` — cross-reference `slide_59.json`'s picture shape list for exact files |

`slide_53` itself is an untitled, leftover staging slide of vector icon shapes — low significance, safe
to exclude entirely (already excluded from `layout_capability_catalog.json` via the `Guide-Only`
category filter).

## Vector icon set (set 1 — `slide_54`\u2013`slide_56`)

Not files in `ppt/media` — drawn directly as grouped `<a:custGeom>`/freeform shapes on the reference
slides. To reuse one: open the source `.potx`, select the icon group on the relevant slide, copy/paste
onto the target slide (preserves vector fidelity + theme-color linkage), or right-click → "Save as
Picture" for a raster copy. The PNG crops under `brand-assets/icons/set_N_icons_*/` (from
`templates/extract_hld_qbr_phase2_render.py`) exist purely for low-res LLM/preview context, not
production-quality insertion — re-export from the source slide for a real deck.

## Harvey ball set (set 2 — `slide_57`)

Real files (`brand-assets/decorative-media/image44.svg`–`image51.svg`). Insert directly as an SVG
picture; recolor via "Graphics Fill" since they use the theme's `accent1` color. Status/progress
indicators only ("% complete" style call-outs) — not decorative icons.

## Raster icon sets (sets 3 and 4 — `slide_58`/`slide_59`)

Already ordinary embedded images. Insert via `python-pptx`'s `add_picture()` (EMF renders natively in
PowerPoint; convert to PNG first only if a pipeline needs a raster preview/thumbnail).

- **Set 3 (outline, categorized):** conceptual/outcome-oriented slides — value props, "why us"
  sections, capability summaries.
- **Set 4 (solid, logistics):** operational/process slides — shipping, facilities, devices, people,
  documents, payments, quality/safety. The larger, more literal library; default choice for QBR
  content slides (inbound/outbound/inventory/quality sections).

## General icon rules

- Never mix set 3 and set 4 icons on the same slide — one family per slide/section.
- Icons render in brand colors already (navy/blue or UPS-brown) — do not recolor set 4; set 3 may be
  recolored via "Graphics Fill" since it uses theme-linked colors.
- Harvey ball icons (set 2) are status/progress indicators only.
- None of these four sets are currently wired into `core/builders/hld_qbr_generic_builder.py` — v1
  scope is slot-fill text/table/chart only (see that module's own docstring "Scope note (v1)"). Adding
  icon placement is deferred, tracked only as a structural fact here, not a generation feature yet.
