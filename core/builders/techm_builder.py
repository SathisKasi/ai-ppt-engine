"""
core/builders/techm_builder.py
Builds presentations using the TechM corporate template as visual identity.

Strategy: 100% Fidelity Template Cloner & In-Place Mutator
  - Loads the original TechM PowerPoint.pptx with all 35 template slides intact.
  - Treats the 35 template slides as a live blueprint catalog.
  - For each slide in the presentation plan, deep-clones the exact blueprint slide
    (preserving 100% of shapes, official TechM logos, vector connectors, pre-formatted
    tables, KPI groupings, and Aptos typography).
  - Mutates the text, table cells, and KPI figures in-place with AI-generated content.
  - Ensures official TechM closing branding (Slide 35) is always attached.
  - Prunes the original 35 template blueprint slides so only the generated deck remains.
"""
from __future__ import annotations

import copy
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Pt

from llm.schemas import PresentationPlan, SlideDefinition
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Blueprint catalog index mapping (0-indexed into the 35 template slides)
# New universal visual archetype keys (LLM-facing) + legacy aliases
# ---------------------------------------------------------------------------
TECHM_BLUEPRINT_CATALOG: Dict[str, int] = {
    # ---- Universal visual archetypes (new — LLM-facing) ----
    "TITLE":             5,   # Slide 6:  Headline Goes Here (Cover)
    "EXECUTIVE_SUMMARY": 14,  # Slide 15: 1_Large Text — two-column (Left=purpose, Right=highlights)
    "AGENDA":            8,   # Slide 9:  Agenda [1] (5 numbered chapter cards)
    "BULLETS":           14,  # Slide 15: 1_Large Text (Content & Bullet Points)
    "SECTION_HEADER":    10,  # Slide 11: 4_Section Header [1] (Chapter divider)
    "CARDS_2_COL":       16,  # Slide 17: Sections Content [1] (Two-Column Cards)
    "CARDS_3_COL":       17,  # Slide 18: Sections Content [1] (Three-Column Cards)
    "TABLE":             28,  # Slide 29: 1_Title Only (Pre-styled 5x5 Table)
    "STATS":             29,  # Slide 30: Data Background [1] (3 KPI metric cards)
    "IMAGE_TEXT":        21,  # Slide 22: Title, Base Content and Image [2]
    "TIMELINE":          33,  # Slide 34: Statement [1] (5 Award/Milestone cards)
    "CONCLUSION":        14,  # Slide 15: 1_Large Text (Summary & Next Steps)
    "CLOSING":           34,  # Slide 35: 9_Blank Slide (Official TechM closing)
    # ---- Legacy names (backward compatibility) ----
    "TITLE_AND_CONTENT": 14,  # → BULLETS
    "TWO_COLUMN":        16,  # → CARDS_2_COL
    "THREE_COLUMN":      17,  # → CARDS_3_COL
    "PROCESS":           17,  # → CARDS_3_COL
    "ARCHITECTURE":      21,  # → IMAGE_TEXT
    "COMPARISON":        16,  # → CARDS_2_COL
    "STATISTICS":        29,  # → STATS
    "AWARDS":            33,  # → TIMELINE
}

TECHM_FALLBACK_INDEX = 14     # Slide 15 (Large Text)

TECHM_BLUEPRINT_NAMES: Dict[int, str] = {
    5:  "Slide 06: 1_Statement [2] (Cover Slide)",
    8:  "Slide 09: Agenda [1] (Numbered Agenda Cards)",
    10: "Slide 11: 4_Section Header [1] (Chapter Divider 01, 02)",
    14: "Slide 15: 1_Large Text (Content & Bullet Points)",
    16: "Slide 17: Sections Content [1] (Two-Column Comparison)",
    17: "Slide 18: Sections Content [1] (Three-Column / Process Cards)",
    21: "Slide 22: Title, Base Content and Image [2] (Image & Text Layout)",
    28: "Slide 29: 1_Title Only (Pre-Styled 5x5 Corporate Table)",
    29: "Slide 30: Data Background [1] (3 KPI Metric Cards)",
    33: "Slide 34: Statement [1] (5 Awards & Recognitions Badges)",
    34: "Slide 35: 9_Blank Slide (Official TechM Logo & Brand Closing)",
}


def _format_item_string(val: Any) -> str:
    """Formats string or structured dictionary (timeline/process/kpi) into readable text."""
    if isinstance(val, dict):
        date = str(val.get("date", "")).strip()
        event = str(val.get("event", "")).strip()
        desc = str(val.get("description", "")).strip()
        title = str(val.get("title", "")).strip()
        val_num = str(val.get("value", "")).strip()
        lbl = str(val.get("label", "")).strip()

        if date or event:
            prefix = f"{date}: {event}" if (date and event) else (date or event)
            return f"{prefix} — {desc}" if desc else prefix
        if title or desc:
            return f"{title} — {desc}" if (title and desc) else (title or desc)
        if val_num or lbl:
            return f"{val_num} {lbl}"
        parts = [f"{k}: {v}" for k, v in val.items() if v and not isinstance(v, (dict, list))]
        return " | ".join(parts)
    return str(val).strip()


def _ensure_list(val: Any) -> List[str]:
    """Ensures a list of clean, human-readable strings from strings or dictionaries."""
    if isinstance(val, list):
        res = []
        for v in val:
            formatted = _format_item_string(v)
            if formatted:
                res.append(formatted)
        return res
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    if isinstance(val, dict):
        formatted = _format_item_string(val)
        return [formatted] if formatted else []
    return []


def _clone_slide(prs: Presentation, source_idx: int) -> Any:
    """
    Deep-clones a slide from the presentation catalog at source_idx.
    Properly clones media relationships (images, SVGs, EMFs) and remaps rId references
    so that no pictures are broken or missing.
    """
    source_slide = prs.slides[source_idx]
    slide_layout = source_slide.slide_layout
    new_slide = prs.slides.add_slide(slide_layout)

    # Map old relationship rId to new slide relationship rId
    rId_map = {}
    for rId, rel in source_slide.part.rels.items():
        # Only copy media, drawing, and content parts (skip layout and notes links)
        if (
            "slideLayout" not in rel.target_ref
            and "notesSlide" not in rel.target_ref
            and "notesMaster" not in rel.target_ref
        ):
            try:
                new_rId = new_slide.part.relate_to(rel.target_part, rel.reltype)
                rId_map[rId] = new_rId
            except Exception as e:
                logger.debug("Could not relate part for rId %s: %s", rId, e)

    # Clear default placeholders injected by add_slide
    for s in list(new_slide.shapes):
        sp = s.element
        sp.getparent().remove(sp)

    # Deep-copy all shapes and remap blip/rId references to new relationships
    for shape in source_slide.shapes:
        new_el = copy.deepcopy(shape.element)
        for elem in new_el.xpath(".//*[@r:embed or @r:link or @r:id]"):
            for attr in list(elem.attrib.keys()):
                if attr.endswith("embed") or attr.endswith("link") or attr.endswith("}id") or attr == "r:id":
                    old_val = elem.attrib[attr]
                    if old_val in rId_map:
                        elem.attrib[attr] = rId_map[old_val]
        new_slide.shapes._spTree.append(new_el)

    return new_slide


def _set_tf_text(shape: Any, text: str) -> bool:
    """Sets plain text in-place preserving paragraph and run styling."""
    if not hasattr(shape, "text_frame"):
        return False
    tf = shape.text_frame
    text_str = str(text).strip()
    if not tf.paragraphs:
        p = tf.add_paragraph()
        run = p.add_run()
        run.text = text_str
        return True

    p0 = tf.paragraphs[0]
    if p0.runs:
        p0.runs[0].text = text_str
        for r in p0.runs[1:]:
            r.text = ""
    else:
        p0.text = text_str

    # Blank out any extra paragraphs from the template sample text
    for extra_p in tf.paragraphs[1:]:
        for r in extra_p.runs:
            r.text = ""
        extra_p.text = ""
    return True


def _set_tf_bullets(shape: Any, items: List[str]) -> bool:
    """Sets multi-line bullet text in-place while keeping font formatting."""
    if not shape.has_text_frame:
        return False
    tf = shape.text_frame
    cleaned = [re.sub(r"^[\s\u2022\-\*]+", "", str(i)).strip() for i in items if str(i).strip()]
    if not cleaned:
        return False

    tf.clear()
    for j, item in enumerate(cleaned):
        p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
        run = p.add_run()
        run.text = item
    return True


def _set_footer(slide: Any, presentation_title: str, slide_num: int) -> None:
    """Updates the 'Chapter title' and slide number footer fields across the slide."""
    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            # 14 is the TechM 'Chapter title' placeholder
            if p_idx == 14 and s.has_text_frame:
                _set_tf_text(s, presentation_title)
            # 4 is the slide number placeholder
            elif p_idx == 4 and s.has_text_frame:
                _set_tf_text(s, str(slide_num))
        elif s.has_text_frame and "chapter title" in s.text_frame.text.lower():
            _set_tf_text(s, presentation_title)


# ---------------------------------------------------------------------------
# Specific Blueprint Slide In-Place Mutators
# ---------------------------------------------------------------------------

def _mutate_cover(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 6 (Cover Blueprint): Title 10, Subtitle 11, Date/CoE."""
    title = slide_def.title or pres_title
    subtitle = content.get("subtitle", "")
    presenter = content.get("presenter", "")
    date_str = content.get("date", "")
    parts = [p for p in [subtitle, presenter, date_str] if p]
    sub_text = " • ".join(parts) if parts else slide_def.purpose or ""

    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            if p_idx == 0:  # Title
                _set_tf_text(s, title)
            elif p_idx == 1:  # Subtitle
                _set_tf_text(s, sub_text)
            elif p_idx == 13:  # Date / CoE
                _set_tf_text(s, "Tech Mahindra AI CoE")


def _mutate_agenda(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 9 (Agenda Blueprint): Title (ph 20) and chapter cards (ph 15-19).

    Reads agenda_items first (new LLM schema key), then falls back to legacy
    keys (items, agenda, bullets) for backward compatibility.
    TechM Slide 9 supports exactly 5 chapter cards (ph 15, 16, 17, 18, 19).
    If more than 5 items are provided, only the first 5 are shown.
    """
    # Primary key from new LLM schema
    agenda_items = _ensure_list(content.get("agenda_items", []))
    # Legacy fallbacks
    if not agenda_items:
        agenda_items = _ensure_list(content.get("items", []))
    if not agenda_items:
        agenda_items = _ensure_list(content.get("agenda", []))
    if not agenda_items:
        bullets = _ensure_list(content.get("bullets", []))
        agenda_items = bullets[:5] if bullets else [
            "Introduction", "Key Findings", "Analysis", "Recommendations", "Next Steps"
        ]

    # TechM Agenda slide 9 has exactly 5 numbered card placeholders
    ph_map = [15, 16, 17, 18, 19]
    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            if p_idx == 20:  # Agenda slide title
                _set_tf_text(s, slide_def.title or "Agenda")
            elif p_idx in ph_map:
                item_idx = ph_map.index(p_idx)
                if item_idx < len(agenda_items):
                    _set_tf_text(s, agenda_items[item_idx])
                else:
                    _set_tf_text(s, "")


def _mutate_divider(slide: Any, content: Dict, slide_def: SlideDefinition,
                    pres_title: str, section_idx: int) -> None:
    """Mutates Slide 11 (Divider Blueprint): Title 1, Text 2, and chapter number 01."""
    section_title = content.get("section_title", slide_def.title)
    description = content.get("description", slide_def.purpose or "")
    num_str = f"{section_idx:02d}"

    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            if p_idx == 0:
                _set_tf_text(s, section_title)
            elif p_idx == 1:
                _set_tf_text(s, description)
            elif p_idx == 14:  # Large chapter number
                _set_tf_text(s, num_str)


def _mutate_content(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 15 (Content Blueprint): Title 6, Lead paragraph (ph 15), Bullets (ph 16)."""
    bullets = _ensure_list(content.get("bullets", []))
    body_text = content.get("body_text", "")

    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            if p_idx == 0:
                _set_tf_text(s, slide_def.title)
            elif p_idx == 15:  # Lead paragraph
                lead = body_text or (bullets[0] if bullets else slide_def.purpose or "")
                _set_tf_text(s, lead)
            elif p_idx == 16:  # Supporting bullet points
                sub_bullets = bullets[1:] if (body_text and bullets) else bullets
                if sub_bullets:
                    _set_tf_bullets(s, sub_bullets)
                else:
                    _set_tf_text(s, "")


def _mutate_two_column(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 17 (Two-Column Blueprint): ph 1 (left) and ph 15 (right)."""
    left_h = content.get("left_heading", "")
    right_h = content.get("right_heading", "")
    left_b = _ensure_list(content.get("left_bullets", []))
    right_b = _ensure_list(content.get("right_bullets", []))

    left_items = ([left_h] if left_h else []) + left_b
    right_items = ([right_h] if right_h else []) + right_b

    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            if p_idx == 1:
                _set_tf_bullets(s, left_items or [slide_def.title])
            elif p_idx == 15:
                _set_tf_bullets(s, right_items or [slide_def.purpose or ""])
            elif p_idx == 16:
                _set_tf_text(s, "")


def _mutate_three_column(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 18 (Three-Column Blueprint): ph 1, ph 15, ph 16."""
    steps = content.get("steps", [])
    components = content.get("components", [])
    bullets = _ensure_list(content.get("bullets", []))

    col_items: List[str] = []
    if steps:
        for i, st in enumerate(steps[:3]):
            if isinstance(st, dict):
                col_items.append(f"{st.get('title', f'Step {i+1}')}\n{st.get('description', '')}")
            else:
                col_items.append(str(st))
    elif components:
        for c in components[:3]:
            if isinstance(c, dict):
                col_items.append(f"{c.get('name', 'Component')}\n{c.get('description', '')}")
            else:
                col_items.append(str(c))
    elif bullets:
        n = len(bullets)
        chunk = max(1, n // 3)
        col_items = [
            "\n".join(bullets[:chunk]),
            "\n".join(bullets[chunk:2*chunk]),
            "\n".join(bullets[2*chunk:3*chunk] or bullets[2*chunk:])
        ]

    while len(col_items) < 3:
        col_items.append("")

    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            if p_idx == 1:
                _set_tf_text(s, col_items[0])
            elif p_idx == 15:
                _set_tf_text(s, col_items[1])
            elif p_idx == 16:
                _set_tf_text(s, col_items[2])


def _mutate_image_text(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 22 (Image + Text Blueprint): Title 1 & Content 2."""
    bullets = _ensure_list(content.get("bullets", []))
    desc = content.get("description", slide_def.purpose or "")
    items = ([desc] if desc else []) + bullets

    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            if p_idx == 0:
                _set_tf_text(s, slide_def.title)
            elif p_idx == 1:
                _set_tf_bullets(s, items)


def _mutate_table(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 29 (Table Blueprint): Title 3 and 5x5 Table 5."""
    for s in slide.shapes:
        if s.is_placeholder and s.placeholder_format.idx == 0:
            _set_tf_text(s, slide_def.title)
        elif s.has_table:
            tbl = s.table
            rows_data = content.get("table_data", {}).get("rows", [])
            headers = content.get("table_data", {}).get("headers", [])

            # If not in table_data format, try comparison structure
            if not rows_data:
                left_p = _ensure_list(content.get("left_points", []))
                right_p = _ensure_list(content.get("right_points", []))
                if left_p or right_p:
                    headers = [content.get("left_heading", "Dimension"), "Current State", "Future Target", "Impact", "Status"]
                    rows_data = []
                    for i in range(max(len(left_p), len(right_p))):
                        lp = left_p[i] if i < len(left_p) else ""
                        rp = right_p[i] if i < len(right_p) else ""
                        rows_data.append([f"Item {i+1}", lp, rp, "High", "Active"])

            # Fallback table if no structured table data
            if not headers:
                headers = ["Capability", "Current State", "Target Vision", "Value Driver", "Priority"]
            if not rows_data:
                bullets = _ensure_list(content.get("bullets", []))
                rows_data = [[f"Area {i+1}", b[:35], "Optimized", "Enhanced ROI", "P1"] for i, b in enumerate(bullets[:4])]

            # Populate headers
            for c_idx in range(len(tbl.columns)):
                cell = tbl.cell(0, c_idx)
                val = headers[c_idx] if c_idx < len(headers) else ""
                _set_tf_text(cell, val)

            # Populate data rows
            for r_idx in range(1, len(tbl.rows)):
                data_r_idx = r_idx - 1
                row_vals = rows_data[data_r_idx] if data_r_idx < len(rows_data) else []
                for c_idx in range(len(tbl.columns)):
                    cell = tbl.cell(r_idx, c_idx)
                    val = str(row_vals[c_idx]) if c_idx < len(row_vals) else ""
                    _set_tf_text(cell, val)


def _mutate_statistics(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 30 (Stats Blueprint): Group 32 with 3 KPI metric cards."""
    stats = content.get("statistics", [])
    bullets = _ensure_list(content.get("bullets", []))

    stat_cards = []
    if stats:
        for st in stats[:3]:
            if isinstance(st, dict):
                stat_cards.append((str(st.get("value", "")), str(st.get("label", "")) + " " + str(st.get("context", ""))))
            else:
                stat_cards.append((str(st), ""))
    elif bullets:
        for b in bullets[:3]:
            parts = b.split(":", 1) if ":" in b else b.split("—", 1)
            if len(parts) == 2:
                stat_cards.append((parts[0].strip(), parts[1].strip()))
            else:
                stat_cards.append((b[:20], b[20:]))

    while len(stat_cards) < 3:
        stat_cards.append(("", ""))

    for s in slide.shapes:
        if s.shape_type == 6 and s.name == "Group 32":  # Group shape
            sub_shapes = list(s.shapes)
            # sub[2]: Headline
            if len(sub_shapes) > 2 and sub_shapes[2].has_text_frame:
                _set_tf_text(sub_shapes[2], slide_def.title)
            # Card 1
            if len(sub_shapes) > 4 and sub_shapes[4].has_text_frame:
                _set_tf_text(sub_shapes[4], stat_cards[0][0])
            if len(sub_shapes) > 5 and sub_shapes[5].has_text_frame:
                _set_tf_text(sub_shapes[5], stat_cards[0][1])
            # Card 2
            if len(sub_shapes) > 6 and sub_shapes[6].has_text_frame:
                _set_tf_text(sub_shapes[6], stat_cards[1][0])
            if len(sub_shapes) > 7 and sub_shapes[7].has_text_frame:
                _set_tf_text(sub_shapes[7], stat_cards[1][1])
            # Card 3
            if len(sub_shapes) > 8 and sub_shapes[8].has_text_frame:
                _set_tf_text(sub_shapes[8], stat_cards[2][0])
            if len(sub_shapes) > 9 and sub_shapes[9].has_text_frame:
                _set_tf_text(sub_shapes[9], stat_cards[2][1])


def _mutate_awards(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 34 (Awards Blueprint): Title 8 and placeholders 21-25."""
    awards = _ensure_list(content.get("items", []))
    if not awards:
        awards = _ensure_list(content.get("bullets", []))
    if not awards:
        awards = [
            "Recognized amongst the Leaders in Digital Transformation",
            "Highest Rating for Sustainability and Corporate Governance",
            "Top Tier Partner for Global Enterprise Cloud Adoption",
            "Premier Excellence Award for AI & Intelligent Automation",
            "Recognized as a Leading Employer for Global Tech Talent"
        ]

    badge_phs = [21, 22, 23, 24, 25]
    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            if p_idx == 0:
                _set_tf_text(s, slide_def.title or "Awards & Recognitions")
            elif p_idx in badge_phs:
                idx = badge_phs.index(p_idx)
                if idx < len(awards):
                    _set_tf_text(s, awards[idx])
                else:
                    _set_tf_text(s, "")


def _mutate_executive_summary(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 15 (1_Large Text Blueprint) for EXECUTIVE_SUMMARY layout.

    TechM Slide 15 layout (1_Large Text):
      ph 0  — Slide title (top bar)
      ph 14 — Chapter category label (small, top-left)
      ph 15 — LEFT column (5.92" wide, 4.35" tall) — populated with purpose_statement + key_metric
      ph 16 — RIGHT column (5.92" wide, 4.35" tall) — populated with highlights as bullet list

    Reads from new LLM schema fields:
      highlights       — list of 3-5 crisp executive one-liners
      purpose_statement — one sentence describing the presentation goal
      key_metric        — optional single impactful number/stat
    """
    highlights = _ensure_list(content.get("highlights", []))
    purpose_stmt = str(content.get("purpose_statement", "")).strip()
    key_metric = str(content.get("key_metric", "")).strip()

    # Fallback: if LLM produced summary_points or bullets instead of highlights
    if not highlights:
        highlights = _ensure_list(content.get("summary_points", []))
    if not highlights:
        highlights = _ensure_list(content.get("bullets", []))
    if not highlights:
        highlights = [slide_def.purpose or "Key executive highlights"]

    # Build left column: purpose statement + optional key metric
    left_lead = purpose_stmt or slide_def.purpose or "Key business highlights for decision-makers."
    left_items: List[str] = [left_lead]
    if key_metric:
        left_items.append(f"Key Metric: {key_metric}")

    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            if p_idx == 0:   # Title
                _set_tf_text(s, slide_def.title or "Executive Summary")
            elif p_idx == 14:  # Chapter category label
                _set_tf_text(s, pres_title)
            elif p_idx == 15:  # Left column — purpose/context
                _set_tf_bullets(s, left_items)
            elif p_idx == 16:  # Right column — highlights bullets
                _set_tf_bullets(s, highlights[:5])


def _mutate_conclusion(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Mutates Slide 15 (Content Blueprint) for CONCLUSION layout.

    Left column (ph 15): Summary points + recommendations
    Right column (ph 16): Next steps (numbered)
    """
    summary = _ensure_list(content.get("summary_points", []))
    next_steps = _ensure_list(content.get("next_steps", []))
    conclusions = _ensure_list(content.get("conclusions", []))
    recommendations = _ensure_list(content.get("recommendations", []))
    takeaways = _ensure_list(content.get("takeaways", []))
    bullets = _ensure_list(content.get("bullets", []))
    cta = str(content.get("call_to_action", "")).strip()
    body_text = str(content.get("body_text", "")).strip()

    points = summary or conclusions or takeaways or bullets
    if not points:
        points = recommendations

    # Left column: summary + recommendations
    lead = body_text or cta or (points[0] if points else "") or slide_def.purpose or "Key Takeaways & Action Plan"
    left_items: List[str] = []
    if body_text or cta:
        left_items.extend(points)
    else:
        left_items.extend(points[1:] if len(points) > 1 else points)
    if recommendations and recommendations not in [points]:
        if left_items:
            left_items.append("Recommendations:")
        for r in recommendations[:3]:
            left_items.append(f"→ {r}")

    # Right column: numbered next steps
    right_items: List[str] = []
    if next_steps:
        for i, step in enumerate(next_steps[:5]):
            right_items.append(f"{i+1}. {step}")

    for s in slide.shapes:
        if s.is_placeholder:
            p_idx = s.placeholder_format.idx
            if p_idx == 0:
                _set_tf_text(s, slide_def.title or "Conclusions & Next Steps")
            elif p_idx == 14:
                _set_tf_text(s, pres_title)
            elif p_idx == 15:  # Left: summary + recommendations
                _set_tf_text(s, lead)
            elif p_idx == 16:  # Right: bullet points + next steps
                all_items = left_items + (["Next Steps:"] + right_items if right_items else [])
                if all_items:
                    _set_tf_bullets(s, all_items)
                else:
                    _set_tf_text(s, "")


def _mutate_closing(slide: Any, content: Dict, slide_def: SlideDefinition, pres_title: str) -> None:
    """Slide 35: Official TechM closing slide. Preserves Picture 7, 8, 9 unchanged."""
    pass


# ---------------------------------------------------------------------------
# Mutator Dispatcher
# ---------------------------------------------------------------------------
_MUTATORS = {
    # ---- Universal visual archetypes ----
    "TITLE":             _mutate_cover,
    "EXECUTIVE_SUMMARY": _mutate_executive_summary,   # NEW — two-column highlights layout
    "AGENDA":            _mutate_agenda,
    "BULLETS":           _mutate_content,
    "SECTION_HEADER":    _mutate_divider,
    "CARDS_2_COL":       _mutate_two_column,
    "CARDS_3_COL":       _mutate_three_column,
    "TABLE":             _mutate_table,
    "STATS":             _mutate_statistics,
    "IMAGE_TEXT":        _mutate_image_text,
    "TIMELINE":          _mutate_awards,
    "CONCLUSION":        _mutate_conclusion,
    "CLOSING":           _mutate_closing,
    # ---- Legacy names (backward compatibility) ----
    "TITLE_AND_CONTENT": _mutate_content,
    "TWO_COLUMN":        _mutate_two_column,
    "THREE_COLUMN":      _mutate_three_column,
    "PROCESS":           _mutate_three_column,
    "ARCHITECTURE":      _mutate_image_text,
    "COMPARISON":        _mutate_two_column,
    "STATISTICS":        _mutate_statistics,
    "AWARDS":            _mutate_awards,
}


# ---------------------------------------------------------------------------
# TechMBuilder Class
# ---------------------------------------------------------------------------

class TechMBuilder:
    """
    Builds presentations using 100% exact TechM corporate template slides.
    Deep-clones original template slides and mutates text/data in-place.
    """

    def __init__(self, template_path: Path) -> None:
        if not template_path.exists():
            raise FileNotFoundError(f"TechM template not found: {template_path}")
        self._template_path = template_path
        logger.info("TechMBuilder (100%% Fidelity Cloner) initialized: %s", template_path.name)

    def build(self, plan: PresentationPlan) -> bytes:
        logger.info("TechMBuilder: building '%s' (%d slides) via Direct Slide Cloning", plan.title, len(plan.slides))

        prs = Presentation(str(self._template_path))
        initial_slide_count = len(prs.slides)  # Typically 35 blueprint slides

        aliases = {
            # New universal names → canonical keys
            "TITLE_SLIDE": "TITLE", "COVER": "TITLE", "OPENING": "TITLE",
            # EXECUTIVE_SUMMARY aliases
            "EXEC_SUMMARY": "EXECUTIVE_SUMMARY", "EXECUTIVE": "EXECUTIVE_SUMMARY",
            "HIGHLIGHTS": "EXECUTIVE_SUMMARY", "KEY_HIGHLIGHTS": "EXECUTIVE_SUMMARY",
            # BULLETS aliases
            "BULLET_POINTS": "BULLETS", "CONTENT": "BULLETS",
            "GENERAL": "BULLETS", "DEFAULT": "BULLETS",
            "TITLE_AND_CONTENT": "BULLETS",
            # CARDS_2_COL aliases
            "SPLIT": "CARDS_2_COL", "COLUMNS": "CARDS_2_COL",
            "TWO_COLUMN": "CARDS_2_COL", "COMPARISON": "CARDS_2_COL",
            # CARDS_3_COL aliases
            "THREE_COLUMN": "CARDS_3_COL",
            "STEPS": "CARDS_3_COL", "WORKFLOW": "CARDS_3_COL",
            "FLOWCHART": "CARDS_3_COL", "PROCESS": "CARDS_3_COL",
            # SECTION_HEADER aliases
            "HEADER": "SECTION_HEADER", "DIVIDER": "SECTION_HEADER",
            "CHAPTER": "SECTION_HEADER",
            # STATS aliases
            "STATISTICS": "STATS", "METRICS": "STATS",
            "KPIS": "STATS", "NUMBERS": "STATS", "DATA": "STATS",
            # IMAGE_TEXT aliases
            "SYSTEM": "IMAGE_TEXT", "TECH_STACK": "IMAGE_TEXT",
            "ARCHITECTURE": "IMAGE_TEXT", "IMAGE": "IMAGE_TEXT", "VISUAL": "IMAGE_TEXT",
            # TIMELINE aliases
            "ROADMAP": "TIMELINE", "MILESTONES": "TIMELINE", "AWARDS": "TIMELINE",
            # TABLE aliases
            "GRID": "TABLE", "MATRIX": "TABLE",
            # CONCLUSION aliases
            "SUMMARY": "CONCLUSION", "TAKEAWAYS": "CONCLUSION",
        }

        generated_slides: List[Any] = []
        matching_records: List[Dict[str, Any]] = []
        section_counter = 1
        total_plan_slides = len(plan.slides)

        for slide_idx, slide_def in enumerate(plan.slides, start=1):
            raw_lt = slide_def.layout_type.upper().strip()
            lt = aliases.get(raw_lt, raw_lt)
            if lt not in TECHM_BLUEPRINT_CATALOG:
                lt = "TITLE_AND_CONTENT"

            # Fetch blueprint slide index from catalog
            blueprint_idx = TECHM_BLUEPRINT_CATALOG.get(lt, TECHM_FALLBACK_INDEX)
            if blueprint_idx >= initial_slide_count:
                blueprint_idx = TECHM_FALLBACK_INDEX

            blueprint_desc = TECHM_BLUEPRINT_NAMES.get(blueprint_idx, f"Slide {blueprint_idx + 1}")
            logger.info(
                "  [Slide %02d/%02d] '%s' | Layout: %s (raw: '%s') -> Cloned from TechM %s",
                slide_idx, total_plan_slides, slide_def.title[:45], lt, raw_lt, blueprint_desc
            )

            # Clone the blueprint slide
            cloned_slide = _clone_slide(prs, blueprint_idx)
            generated_slides.append(cloned_slide)
            matching_records.append({
                "gen_idx": slide_idx,
                "title": slide_def.title[:40],
                "layout": f"{lt} ({raw_lt})" if lt != raw_lt else lt,
                "blueprint": blueprint_desc,
            })

            content = slide_def.content or {}
            mutator = _MUTATORS.get(lt, _mutate_content)

            try:
                if lt == "SECTION_HEADER":
                    mutator(cloned_slide, content, slide_def, plan.title, section_counter)
                    section_counter += 1
                else:
                    mutator(cloned_slide, content, slide_def, plan.title)
            except Exception as e:
                logger.warning("TechMBuilder slide %d (%s) mutation error: %s — using content fallback", slide_idx, lt, e)
                try:
                    _mutate_content(cloned_slide, content, slide_def, plan.title)
                except Exception as e2:
                    logger.error("TechMBuilder fallback also failed: %s", e2)

            # Update footer & slide number
            _set_footer(cloned_slide, plan.title, slide_idx)

            # Speaker notes
            if slide_def.speaker_notes:
                try:
                    cloned_slide.notes_slide.notes_text_frame.text = slide_def.speaker_notes
                except Exception:
                    pass

        # Mandatory TechM Closing Slide (Slide 35 / index 34)
        # Guarantees the official branded closing slide with all original imagery is always attached
        has_closing = any(
            aliases.get(s.layout_type.upper().strip(), s.layout_type.upper().strip()) == "CLOSING"
            for s in plan.slides
        )
        if not has_closing and initial_slide_count > 34:
            closing_slide = _clone_slide(prs, 34)
            generated_slides.append(closing_slide)
            matching_records.append({
                "gen_idx": len(generated_slides),
                "title": "TechM Official Closing Slide",
                "layout": "CLOSING",
                "blueprint": "Slide 35: 9_Blank Slide (Official TechM closing)",
            })
            logger.info("  [Slide %02d (Mandatory Closing)] TechM Slide 35 appended with 100%% intact branding", len(generated_slides))

        # Summary table log for easy debugging
        summary_lines = [
            f"  {r['gen_idx']:02d} | {r['title']:<40} | {r['layout']:<22} | {r['blueprint']}"
            for r in matching_records
        ]
        logger.info(
            "\n" + "=" * 95 + "\n"
            + f"TECHM TEMPLATE SLIDE MATCHING SUMMARY ({len(generated_slides)} Total Slides Generated)\n"
            + "-" * 95 + "\n"
            + "  #  | Generated Slide Title                    | Layout Type            | Template Blueprint\n"
            + "  ---+------------------------------------------+------------------------+-------------------------------------------------\n"
            + "\n".join(summary_lines) + "\n"
            + "=" * 95
        )

        # Prune the original 35 template blueprint slides so only the generated deck remains
        rId_attr = qn("r:id")
        sldIdLst = prs.slides._sldIdLst
        for _ in range(initial_slide_count):
            sldId = sldIdLst[0]
            rId = sldId.get(rId_attr)
            if rId:
                try:
                    prs.part.drop_rel(rId)
                except Exception:
                    pass
            sldIdLst.remove(sldId)

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        data = buf.read()
        logger.info("TechMBuilder: completed %d slides, %d bytes", len(prs.slides), len(data))
        return data
