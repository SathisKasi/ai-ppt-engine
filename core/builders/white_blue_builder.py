"""
core/builders/white_blue_builder.py
Programmatic White+Blue builder — same draw-from-scratch approach as dark navy
but using a clean White+Blue corporate palette.
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from llm.schemas import PresentationPlan, SlideDefinition
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
BG_WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
BLUE_PRI     = RGBColor(0x00, 0x57, 0xB8)
BLUE_DEEP    = RGBColor(0x00, 0x3D, 0x82)
BLUE_LIGHT   = RGBColor(0x00, 0xA0, 0xE4)
BLUE_CARD    = RGBColor(0xF0, 0xF7, 0xFF)
BLUE_DIV     = RGBColor(0xD0, 0xE8, 0xF8)
BLUE_SEC     = RGBColor(0xE8, 0xF4, 0xFD)
BLUE_SOFT4   = RGBColor(0x5B, 0xA3, 0xD8)
TXT_DARK     = RGBColor(0x1A, 0x1A, 0x2A)
TXT_MED      = RGBColor(0x4A, 0x55, 0x68)
TXT_MUTED    = RGBColor(0x94, 0xA3, 0xB8)
TXT_WHITE    = RGBColor(0xFF, 0xFF, 0xFF)
ACCENT_ON_BLUE = RGBColor(0xC0, 0xDE, 0xFF)
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
FONT = "Calibri"

STAT_COLORS = [BLUE_PRI, BLUE_DEEP, BLUE_LIGHT, BLUE_SOFT4]
PROC_COLORS = [BLUE_PRI, BLUE_DEEP, BLUE_LIGHT, BLUE_SOFT4]
ARCH_COLORS = [BLUE_PRI, BLUE_DEEP, BLUE_LIGHT, BLUE_SOFT4]


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def _bg(slide, color=BG_WHITE):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _rect(slide, l, t, w, h, fill=BLUE_PRI, lc=None):
    s = slide.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = fill
    if lc: s.line.color.rgb = lc; s.line.width = Pt(0.5)
    else:  s.line.fill.background()
    return s


def _txt(slide, text, l, t, w, h, sz=18, bold=False, color=TXT_DARK,
         align=PP_ALIGN.LEFT, italic=False):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.alignment = align
    run = p.add_run(); run.text = str(text)
    run.font.size = Pt(sz); run.font.bold = bold; run.font.italic = italic
    run.font.color.rgb = color; run.font.name = FONT
    return tb


def _bullets(slide, items, l, t, w, h, sz=16, color=TXT_MED, char="\u25cf  "):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    for i, item in enumerate(items):
        cleaned = re.sub(r"^[\s\u2022\-\*\u2023\u25aa]+", "", str(item)).strip()
        if not cleaned: continue
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run(); run.text = f"{char}{cleaned}"
        run.font.size = Pt(sz); run.font.color.rgb = color; run.font.name = FONT
    return tb


def _ensure_list(val):
    if isinstance(val, list): return [str(v) for v in val if v]
    if isinstance(val, str) and val.strip(): return [val.strip()]
    return []


def _hdr(slide, title, sz=26):
    _rect(slide, 0, 0, 13.333, 1.3, BLUE_PRI)
    _rect(slide, 0, 1.3, 13.333, 0.04, BLUE_LIGHT)
    _txt(slide, title, 0.35, 0.1, 12.5, 1.0, sz=sz, bold=True, color=TXT_WHITE)


def _ftr(slide):
    _rect(slide, 0, 7.44, 13.333, 0.04, BLUE_DIV)


def _card(slide, l, t, w, h):
    return _rect(slide, l, t, w, h, BLUE_CARD, BLUE_DIV)


# ---------------------------------------------------------------------------
# Layout drawers
# ---------------------------------------------------------------------------

def _draw_title(slide, content: Dict, sd: SlideDefinition):
    _bg(slide)
    _rect(slide, 0, 0, 13.333, 0.05, BLUE_PRI)
    _rect(slide, 0, 0.05, 5.5, 7.45, BLUE_PRI)
    _rect(slide, 5.5, 0.05, 0.04, 7.45, BLUE_LIGHT)

    _txt(slide, sd.title, 0.4, 2.3, 4.8, 2.0,
         sz=36, bold=True, color=TXT_WHITE, align=PP_ALIGN.LEFT)

    subtitle  = content.get("subtitle", "")
    presenter = content.get("presenter", "")
    date_str  = content.get("date", "")
    parts = [p for p in [subtitle, presenter, date_str] if p]
    sub_text = " • ".join(parts) if parts else sd.purpose or ""
    if sub_text:
        _txt(slide, sub_text, 0.4, 4.4, 4.8, 0.7, sz=16,
             color=ACCENT_ON_BLUE)

    _txt(slide, "Presented by", 6.2, 2.9, 6.5, 0.4, sz=12,
         color=TXT_MUTED, italic=True)
    _txt(slide, presenter or "Author Name", 6.2, 3.3, 6.5, 0.5,
         sz=18, bold=True, color=TXT_DARK)
    org_date = " • ".join([p for p in [date_str] if p]) or "Organisation  •  Date"
    _txt(slide, org_date, 6.2, 3.85, 6.5, 0.4, sz=13, color=TXT_MED)
    _rect(slide, 0, 7.3, 13.333, 0.2, BLUE_DEEP)


def _draw_title_content(slide, content: Dict, sd: SlideDefinition):
    _bg(slide); _hdr(slide, sd.title)
    _card(slide, 0.4, 1.5, 12.55, 5.65)
    bullets   = _ensure_list(content.get("bullets", []))
    body_text = content.get("body_text", "")
    if bullets:
        _bullets(slide, bullets[:10], 0.65, 1.7, 12.1, 5.3)
    elif body_text:
        _txt(slide, body_text, 0.65, 1.7, 12.1, 5.3, sz=17, color=TXT_MED)
    else:
        _txt(slide, sd.purpose or "", 0.65, 1.7, 12.1, 5.3,
             sz=17, color=TXT_MUTED, italic=True)
    _ftr(slide)


def _draw_two_column(slide, content: Dict, sd: SlideDefinition):
    _bg(slide); _hdr(slide, sd.title)
    lh = content.get("left_heading",  "Left Column")
    rh = content.get("right_heading", "Right Column")
    lb = _ensure_list(content.get("left_bullets",  []))
    rb = _ensure_list(content.get("right_bullets", []))
    # Left
    _card(slide, 0.4, 1.5, 5.95, 5.65)
    _rect(slide, 0.4, 1.5, 5.95, 0.5, BLUE_PRI)
    _txt(slide, lh, 0.55, 1.56, 5.65, 0.4, sz=14, bold=True, color=TXT_WHITE)
    _bullets(slide, lb[:7], 0.6, 2.1, 5.5, 4.8)
    # Divider
    _rect(slide, 6.6, 1.5, 0.04, 5.65, BLUE_DIV)
    # Right
    _card(slide, 6.95, 1.5, 5.95, 5.65)
    _rect(slide, 6.95, 1.5, 5.95, 0.5, BLUE_DEEP)
    _txt(slide, rh, 7.1, 1.56, 5.65, 0.4, sz=14, bold=True, color=TXT_WHITE)
    _bullets(slide, rb[:7], 7.1, 2.1, 5.5, 4.8)
    _ftr(slide)


def _draw_section_header(slide, content: Dict, sd: SlideDefinition):
    _bg(slide, BLUE_SEC)
    _rect(slide, 0, 0, 13.333, 0.06, BLUE_PRI)
    _rect(slide, 0, 7.44, 13.333, 0.06, BLUE_PRI)
    _rect(slide, 1.5, 3.4, 10.333, 0.05, BLUE_PRI)
    section_title = content.get("section_title", sd.title)
    description   = content.get("description", sd.purpose or "")
    _txt(slide, "SECTION", 1.5, 2.2, 10.333, 0.5, sz=13, bold=True,
         color=BLUE_PRI, align=PP_ALIGN.CENTER)
    _txt(slide, section_title, 1.0, 2.7, 11.333, 1.4, sz=40, bold=True,
         color=TXT_DARK, align=PP_ALIGN.CENTER)
    if description:
        _txt(slide, description, 2.0, 3.6, 9.333, 0.6, sz=16,
             color=TXT_MED, align=PP_ALIGN.CENTER)


def _draw_image_text(slide, content: Dict, sd: SlideDefinition):
    _bg(slide); _hdr(slide, sd.title)
    _card(slide, 0.4, 1.5, 5.8, 5.65)
    _rect(slide, 0.4, 1.5, 5.8, 0.04, BLUE_PRI)
    _txt(slide, "[ Image / Diagram ]", 0.5, 3.6, 5.6, 0.9, sz=15,
         color=TXT_MUTED, align=PP_ALIGN.CENTER, italic=True)
    _card(slide, 6.6, 1.5, 6.35, 5.65)
    description = content.get("description", "")
    bullets = _ensure_list(content.get("bullets", []))
    if description:
        _txt(slide, description, 6.75, 1.65, 6.05, 0.6, sz=15,
             bold=True, color=BLUE_PRI)
        if bullets:
            _bullets(slide, bullets[:6], 6.75, 2.4, 6.05, 4.5)
    elif bullets:
        _bullets(slide, bullets[:7], 6.75, 1.65, 6.05, 5.3)
    _ftr(slide)


def _draw_comparison(slide, content: Dict, sd: SlideDefinition):
    _bg(slide); _hdr(slide, sd.title)
    lh = content.get("left_heading",  "Option A")
    rh = content.get("right_heading", "Option B")
    lp = _ensure_list(content.get("left_points",  []))
    rp = _ensure_list(content.get("right_points", []))
    _rect(slide, 0.4, 1.5, 6.0, 0.55, BLUE_PRI)
    _txt(slide, lh, 0.6, 1.57, 5.6, 0.42, sz=17, bold=True, color=TXT_WHITE)
    _card(slide, 0.4, 2.05, 6.0, 5.1)
    _bullets(slide, lp[:6], 0.6, 2.2, 5.6, 4.7)
    _txt(slide, "VS", 6.47, 3.7, 0.4, 0.6, sz=12, bold=True,
         color=BLUE_DEEP, align=PP_ALIGN.CENTER)
    _rect(slide, 6.95, 1.5, 6.0, 0.55, BLUE_DEEP)
    _txt(slide, rh, 7.1, 1.57, 5.6, 0.42, sz=17, bold=True, color=TXT_WHITE)
    _card(slide, 6.95, 2.05, 6.0, 5.1)
    _bullets(slide, rp[:6], 7.1, 2.2, 5.6, 4.7)
    _ftr(slide)


def _draw_timeline(slide, content: Dict, sd: SlideDefinition):
    _bg(slide); _hdr(slide, sd.title)
    _rect(slide, 0.5, 4.0, 12.333, 0.06, BLUE_PRI)
    items = content.get("items", [])
    if not items: return
    n = min(len(items), 4)
    xs = [1.0, 4.1, 7.2, 10.3][:n]
    for i, (item, x) in enumerate(zip(items, xs)):
        if isinstance(item, dict):
            date = str(item.get("date", f"Q{i+1}"))
            ev   = str(item.get("event", f"Event {i+1}"))
            desc = str(item.get("description", ""))
        else:
            date, ev, desc = str(item), f"Event {i+1}", ""
        _rect(slide, x+0.7, 3.8, 0.4, 0.4,
              BLUE_PRI if i % 2 == 0 else BLUE_DEEP)
        _txt(slide, date, x+0.55, 4.3, 0.7, 0.4, sz=12, bold=True,
             color=BLUE_PRI, align=PP_ALIGN.CENTER)
        ct = 2.0 if i % 2 == 0 else 4.9
        _card(slide, x+0.1, ct, 2.2, 1.5)
        card_text = f"{ev}\n{desc}".strip() if desc else ev
        _txt(slide, card_text, x+0.2, ct+0.1, 2.0, 1.2, sz=13,
             color=TXT_DARK, align=PP_ALIGN.CENTER)
    _ftr(slide)


def _draw_process(slide, content: Dict, sd: SlideDefinition):
    _bg(slide); _hdr(slide, sd.title)
    steps = content.get("steps", [])
    if not steps: return
    n = min(len(steps), 4)
    for i, step in enumerate(steps[:n]):
        if isinstance(step, dict):
            title = str(step.get("title", f"Step {i+1}"))
            desc  = str(step.get("description", ""))
            num   = str(step.get("step_number", i + 1))
        else:
            title, desc, num = str(step), "", str(i + 1)
        x = 0.5 + i * 3.15
        c = PROC_COLORS[i % len(PROC_COLORS)]
        _card(slide, x, 2.0, 2.7, 4.7)
        _rect(slide, x + 0.85, 1.7, 1.0, 1.0, c)
        _txt(slide, num, x+0.85, 1.7, 1.0, 1.0, sz=22, bold=True,
             color=TXT_WHITE, align=PP_ALIGN.CENTER)
        _txt(slide, title, x+0.1, 2.9, 2.5, 0.55, sz=14, bold=True,
             color=c, align=PP_ALIGN.CENTER)
        if desc:
            _txt(slide, desc, x+0.15, 3.55, 2.4, 2.9, sz=12,
                 color=TXT_MED, align=PP_ALIGN.CENTER)
        if i < n - 1:
            _txt(slide, "\u2192", x+2.68, 3.9, 0.5, 0.6, sz=22,
                 bold=True, color=BLUE_LIGHT, align=PP_ALIGN.CENTER)
    _ftr(slide)


def _draw_architecture(slide, content: Dict, sd: SlideDefinition):
    _bg(slide); _hdr(slide, sd.title)
    layers = content.get("layers", [])
    if not layers:
        layers = [{"name": c, "description": ""} for c in
                  _ensure_list(content.get("components", []))]
    if not layers: return
    for i, layer in enumerate(layers[:4]):
        if isinstance(layer, dict):
            nm   = str(layer.get("name", f"Layer {i+1}"))
            desc = str(layer.get("description", ""))
            sub  = [str(s) for s in layer.get("sub_components", [])]
        else:
            nm, desc, sub = str(layer), "", []
        y = 1.55 + i * 1.28
        c = ARCH_COLORS[i % len(ARCH_COLORS)]
        _rect(slide, 0.4, y, 12.5, 1.1, c)
        _txt(slide, nm, 0.6, y+0.06, 5.5, 0.5, sz=16, bold=True, color=TXT_WHITE)
        detail = desc
        if sub: detail = (detail + " — " if detail else "") + ", ".join(sub[:4])
        if detail:
            _txt(slide, detail, 6.2, y+0.06, 6.5, 0.5, sz=14,
                 color=RGBColor(0xC8, 0xE8, 0xFF))
        if i < min(len(layers), 4) - 1:
            _txt(slide, "\u2195", 6.4, y+1.1, 0.5, 0.22, sz=11,
                 color=TXT_MUTED, align=PP_ALIGN.CENTER)
    _ftr(slide)


def _draw_statistics(slide, content: Dict, sd: SlideDefinition):
    _bg(slide); _hdr(slide, sd.title)
    stats = content.get("statistics", [])
    if not stats:
        stats = [{"value": b, "label": "", "context": ""}
                 for b in _ensure_list(content.get("bullets", []))]
    if not stats: return
    for i, stat in enumerate(stats[:4]):
        if isinstance(stat, dict):
            value   = str(stat.get("value", ""))
            label   = str(stat.get("label", ""))
            context = str(stat.get("context", ""))
        else:
            value, label, context = str(stat), "", ""
        x = 0.45 + i * 3.2
        c = STAT_COLORS[i % len(STAT_COLORS)]
        _card(slide, x, 1.8, 2.85, 5.1)
        _rect(slide, x, 1.8, 2.85, 0.08, c)
        _txt(slide, value, x+0.1, 2.6, 2.65, 1.5,
             sz=52, bold=True, color=c, align=PP_ALIGN.CENTER)
        lbl_text = f"{label}\n{context}".strip() if context else label
        if lbl_text:
            _txt(slide, lbl_text, x+0.1, 4.3, 2.65, 2.0, sz=15,
                 color=TXT_MED, align=PP_ALIGN.CENTER)
    ctx = content.get("context_paragraph", "")
    if ctx:
        _txt(slide, ctx, 0.4, 6.85, 12.5, 0.4, sz=11,
             color=TXT_MUTED, align=PP_ALIGN.CENTER)
    _ftr(slide)


def _draw_executive_summary(slide, content: Dict, sd: SlideDefinition):
    """EXECUTIVE_SUMMARY slide — White+Blue two-column layout.

    Left panel (blue accent): Purpose statement + key metric.
    Right panel (white cards): 3-5 highlight bullet rows with numbered circles.
    """
    _bg(slide)
    # Top accent bar + title
    _rect(slide, 0, 0, 13.333, 1.4, BLUE_PRI)
    _rect(slide, 0, 1.4, 13.333, 0.04, BLUE_LIGHT)
    _txt(slide, sd.title or "Executive Summary", 0.35, 0.1, 9.0, 1.1,
         sz=30, bold=True, color=TXT_WHITE)
    _txt(slide, "EXECUTIVE SUMMARY", 9.5, 0.55, 3.5, 0.4,
         sz=10, bold=True, color=ACCENT_ON_BLUE, align=PP_ALIGN.RIGHT)

    highlights = _ensure_list(content.get("highlights", []))
    purpose_stmt = str(content.get("purpose_statement", "")).strip()
    key_metric = str(content.get("key_metric", "")).strip()

    # Fallbacks
    if not highlights:
        highlights = _ensure_list(content.get("summary_points", []))
    if not highlights:
        highlights = _ensure_list(content.get("bullets", []))
    if not highlights:
        highlights = [sd.purpose or "Key executive takeaways"]

    # --- Left panel: context/purpose ---
    _rect(slide, 0.4, 1.6, 4.3, 5.6, BLUE_DEEP)
    left_label = purpose_stmt or sd.purpose or "Business Context"
    _txt(slide, "PURPOSE", 0.6, 1.75, 3.9, 0.35,
         sz=10, bold=True, color=ACCENT_ON_BLUE)
    _txt(slide, left_label, 0.6, 2.15, 3.9, 2.8, sz=16, color=TXT_WHITE)
    if key_metric:
        _rect(slide, 0.55, 5.0, 3.95, 1.7, BLUE_LIGHT)
        _txt(slide, key_metric, 0.7, 5.1, 3.7, 1.5,
             sz=22, bold=True, color=TXT_DARK, align=PP_ALIGN.CENTER)

    # --- Right panel: highlight cards ---
    card_y = 1.6
    card_h = (5.6 / max(len(highlights[:5]), 1)) - 0.1
    for i, hl in enumerate(highlights[:5]):
        y = card_y + i * (card_h + 0.1)
        _card(slide, 5.1, y, 7.85, card_h)
        # Number circle
        _rect(slide, 5.2, y + (card_h - 0.45) / 2, 0.45, 0.45,
              BLUE_PRI if i % 2 == 0 else BLUE_DEEP)
        _txt(slide, str(i + 1), 5.2, y + (card_h - 0.45) / 2,
             0.45, 0.45, sz=14, bold=True, color=TXT_WHITE, align=PP_ALIGN.CENTER)
        # Highlight text
        _txt(slide, hl, 5.75, y + 0.05, 7.1, card_h - 0.1,
             sz=15, color=TXT_DARK)
    _ftr(slide)


def _draw_agenda(slide, content: Dict, sd: SlideDefinition):
    """AGENDA slide — White+Blue numbered chapter card layout.

    Renders up to 8 agenda items as coloured numbered cards in a 2-column grid.
    """
    _bg(slide)
    _rect(slide, 0, 0, 13.333, 1.4, BLUE_PRI)
    _rect(slide, 0, 1.4, 13.333, 0.04, BLUE_LIGHT)
    _txt(slide, sd.title or "Agenda", 0.35, 0.1, 9.0, 1.1,
         sz=30, bold=True, color=TXT_WHITE)
    _txt(slide, "CONTENTS", 9.5, 0.55, 3.5, 0.4,
         sz=10, bold=True, color=ACCENT_ON_BLUE, align=PP_ALIGN.RIGHT)

    items = _ensure_list(content.get("agenda_items", []))
    if not items:
        items = _ensure_list(content.get("items", []))
    if not items:
        items = _ensure_list(content.get("bullets", []))
    if not items:
        items = ["Introduction", "Key Findings", "Analysis", "Recommendations", "Conclusion"]

    items = items[:8]
    n = len(items)

    if n <= 4:
        # Single column layout
        for i, item in enumerate(items):
            y = 1.65 + i * 1.35
            _card(slide, 1.5, y, 10.333, 1.15)
            _rect(slide, 1.5, y, 0.6, 1.15,
                  BLUE_PRI if i % 2 == 0 else BLUE_DEEP)
            _txt(slide, str(i + 1).zfill(2), 1.5, y + 0.3, 0.6, 0.55,
                 sz=18, bold=True, color=TXT_WHITE, align=PP_ALIGN.CENTER)
            _txt(slide, item, 2.25, y + 0.28, 9.3, 0.65, sz=17, color=TXT_DARK)
    else:
        # Two-column layout
        cols = [(1.5, 4.2), (7.2, 4.2)]  # (left_x, right_x) - approx
        col_w = 5.45
        per_col = (n + 1) // 2
        for i, item in enumerate(items):
            col = i // per_col
            row = i % per_col
            x = 1.5 if col == 0 else 7.15
            y = 1.65 + row * ((5.5 / per_col) - 0.1)
            h = (5.5 / per_col) - 0.2
            _card(slide, x, y, col_w, h)
            _rect(slide, x, y, 0.5, h,
                  BLUE_PRI if i % 2 == 0 else BLUE_DEEP)
            _txt(slide, str(i + 1).zfill(2), x, y + (h - 0.4) / 2,
                 0.5, 0.4, sz=14, bold=True, color=TXT_WHITE, align=PP_ALIGN.CENTER)
            _txt(slide, item, x + 0.6, y + 0.05, col_w - 0.7, h - 0.1,
                 sz=14, color=TXT_DARK)
    _ftr(slide)


def _draw_conclusion(slide, content: Dict, sd: SlideDefinition):
    _bg(slide)
    _rect(slide, 0, 0, 13.333, 2.0, BLUE_PRI)
    _txt(slide, sd.title, 0.4, 0.3, 12.5, 1.4, sz=30, bold=True, color=TXT_WHITE)
    summary  = _ensure_list(content.get("summary_points", []))
    next_stp = _ensure_list(content.get("next_steps", []))
    cta      = content.get("call_to_action", "")
    # Summary card
    _card(slide, 0.4, 2.2, 7.6, 5.0)
    _rect(slide, 0.4, 2.2, 7.6, 0.35, BLUE_LIGHT)
    _txt(slide, "KEY TAKEAWAYS", 0.6, 2.24, 5.0, 0.28,
         sz=11, bold=True, color=TXT_WHITE)
    if summary:
        _bullets(slide, summary[:6], 0.6, 2.65, 7.2, 4.3, sz=17)
    # Next steps card
    _rect(slide, 8.35, 2.2, 4.6, 5.0, BLUE_DEEP)
    _txt(slide, "NEXT STEPS", 8.5, 2.3, 4.3, 0.4, sz=11,
         bold=True, color=ACCENT_ON_BLUE)
    if next_stp:
        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(next_stp[:5]))
        _txt(slide, steps_text, 8.5, 2.8, 4.2, 3.5, sz=15, color=TXT_WHITE)
    # CTA bar
    _rect(slide, 3.0, 7.1, 7.333, 0.3, BLUE_LIGHT)
    cta_text = cta if cta else "Thank You — Questions Welcome"
    _txt(slide, cta_text, 3.0, 7.1, 7.333, 0.3, sz=13, bold=True,
         color=TXT_WHITE, align=PP_ALIGN.CENTER)


_DRAWERS: Dict = {
    # ---- Universal visual archetypes (new — LLM-facing) ----
    "TITLE":             _draw_title,
    "EXECUTIVE_SUMMARY": _draw_executive_summary,   # NEW
    "AGENDA":            _draw_agenda,               # NEW
    "BULLETS":           _draw_title_content,        # replaces TITLE_AND_CONTENT
    "SECTION_HEADER":    _draw_section_header,
    "CARDS_2_COL":       _draw_two_column,           # replaces TWO_COLUMN / COMPARISON
    "CARDS_3_COL":       _draw_process,              # replaces PROCESS / THREE_COLUMN
    "TABLE":             _draw_conclusion,           # closest visual: structured layout
    "STATS":             _draw_statistics,           # replaces STATISTICS
    "IMAGE_TEXT":        _draw_image_text,           # replaces ARCHITECTURE
    "TIMELINE":          _draw_timeline,
    "CONCLUSION":        _draw_conclusion,
    # ---- Legacy names (backward compatibility) ----
    "TITLE_AND_CONTENT": _draw_title_content,
    "TWO_COLUMN":        _draw_two_column,
    "COMPARISON":        _draw_comparison,
    "TIMELINE_LEGACY":   _draw_timeline,
    "PROCESS":           _draw_process,
    "ARCHITECTURE":      _draw_architecture,
    "STATISTICS":        _draw_statistics,
}

ALIASES: Dict[str, str] = {
    # Cover
    "TITLE_SLIDE": "TITLE", "COVER": "TITLE", "OPENING": "TITLE",
    # EXECUTIVE_SUMMARY aliases
    "EXEC_SUMMARY": "EXECUTIVE_SUMMARY", "EXECUTIVE": "EXECUTIVE_SUMMARY",
    "HIGHLIGHTS": "EXECUTIVE_SUMMARY", "KEY_HIGHLIGHTS": "EXECUTIVE_SUMMARY",
    # BULLETS
    "BULLET_POINTS": "BULLETS", "CONTENT": "BULLETS",
    "GENERAL": "BULLETS", "DEFAULT": "BULLETS",
    "TITLE_AND_CONTENT": "BULLETS",
    # CARDS_2_COL
    "SPLIT": "CARDS_2_COL", "COLUMNS": "CARDS_2_COL",
    "TWO_COLUMN": "CARDS_2_COL", "COMPARISON": "CARDS_2_COL",
    # CARDS_3_COL
    "THREE_COLUMN": "CARDS_3_COL",
    "STEPS": "CARDS_3_COL", "WORKFLOW": "CARDS_3_COL",
    "FLOWCHART": "CARDS_3_COL", "PROCESS": "CARDS_3_COL",
    # SECTION_HEADER
    "HEADER": "SECTION_HEADER", "DIVIDER": "SECTION_HEADER",
    "CHAPTER": "SECTION_HEADER",
    # STATS
    "STATISTICS": "STATS", "METRICS": "STATS",
    "KPIS": "STATS", "NUMBERS": "STATS", "DATA": "STATS",
    # IMAGE_TEXT
    "SYSTEM": "IMAGE_TEXT", "TECH_STACK": "IMAGE_TEXT",
    "ARCHITECTURE": "IMAGE_TEXT", "IMAGE": "IMAGE_TEXT", "VISUAL": "IMAGE_TEXT",
    # TIMELINE
    "ROADMAP": "TIMELINE", "MILESTONES": "TIMELINE", "AWARDS": "TIMELINE",
    # TABLE
    "GRID": "TABLE", "MATRIX": "TABLE",
    # CONCLUSION
    "SUMMARY": "CONCLUSION", "CLOSING": "CONCLUSION", "TAKEAWAYS": "CONCLUSION",
}


class WhiteBlueBuilder:
    """
    Programmatic White+Blue corporate presentation builder.
    Draws slides from scratch using the White+Blue palette and shape primitives.
    """

    def build(self, plan: PresentationPlan) -> bytes:
        logger.info("WhiteBlueBuilder: '%s' (%d slides)", plan.title, len(plan.slides))
        prs = Presentation()
        prs.slide_width  = SLIDE_W
        prs.slide_height = SLIDE_H
        blank_layout = prs.slide_layouts[6]

        for slide_def in plan.slides:
            lt = slide_def.layout_type.upper().strip()
            lt = ALIASES.get(lt, lt)
            if lt not in _DRAWERS:
                lt = "TITLE_AND_CONTENT"

            slide   = prs.slides.add_slide(blank_layout)
            content = slide_def.content or {}
            try:
                _DRAWERS[lt](slide, content, slide_def)
            except Exception as e:
                logger.warning("WhiteBlueBuilder slide %d (%s) failed: %s",
                               slide_def.slide_number, lt, e)
                try:
                    _draw_title_content(slide, content, slide_def)
                except Exception:
                    pass

            if slide_def.speaker_notes:
                try:
                    slide.notes_slide.notes_text_frame.text = slide_def.speaker_notes
                except Exception:
                    pass

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        data = buf.read()
        logger.info("WhiteBlueBuilder: %d bytes, %d slides", len(data), len(prs.slides))
        return data
