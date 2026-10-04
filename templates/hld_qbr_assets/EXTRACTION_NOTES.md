# Extraction notes

## Phase 1 (`extract_hld_qbr_assets.py`) — zip/python-pptx only, no renderer
- `metadata/`, `inventory/`, `brand-assets/source-xml/`, `media/`,
  `brand-assets/decorative-media/`

## Phase 2 (`extract_hld_qbr_phase2_render.py`) — needs desktop PowerPoint
- `layouts/slide_NN.svg`: full-slide vector SVG, de-sampled afterwards
  (guidance-sticker text blanked via the same GUIDANCE_REGEX the real
  builder uses). 21/60 slides had guidance text to strip.
- `brand-assets/icons/set_N_*/icon_NNN.png`: individual icon crops from
  slides 54-56 (182 total — catalog says 183, off by one, not yet root-
  caused). These icons are vector freeform/group shapes, not embedded
  media, so they can't be pulled from `ppt/media/` directly.

### Why PDF + PyMuPDF instead of direct SVG/PNG export
No LibreOffice (`soffice`) is installed on this machine. Desktop
PowerPoint is (`C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE`)
but its `Slide.Export(path, "SVG")` filter isn't installed, and relying on
a raster `Slide.Export(path, "PNG", w, h)` per icon slide would need exact
px/inch bookkeeping. Instead: `Presentation.ExportAsFixedFormat` to PDF
(always available, native) once via `pywin32` COM, then PyMuPDF (already a
project dependency) does everything else — `page.get_svg_image(text_as_
path=False)` for true vector SVG per slide (keeps real `<text>` elements,
required for the de-sampling regex pass to find anything), and
`page.get_pixmap(matrix=..., clip=fitz.Rect(...))` for crisp per-icon PNG
crops using the bounding boxes already captured in Phase 1's metadata
(360 px/in, inches -> PDF points via *72 for the clip rect).

### Known size gap vs. the reference project
Icon crops here are tiny PNGs (~400KB total for all 182, vs. a 32.7MB
reference figure) since each icon is only ~0.3in x 0.3in cropped at
360dpi. Bump `ICON_RENDER_DPI` in extract_hld_qbr_phase2_render.py if
higher-resolution icon assets are needed later.
