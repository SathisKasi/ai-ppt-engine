"""
core/builders/template1_builder.py — Dynamic slide builder for Template-1
(AITransformationWeeklyUpdate4SEP2026.pptx).

Architecture:
  - Loads Template-1 PPTX containing 5 slides:
      Slide 1 (idx 0): Cover Page      (Layout: 8_Section Header)
      Slide 2 (idx 1): Agenda          (Layout: Picture with Caption)  — mandatory, intact
      Slide 3 (idx 2): Content canvas  (Layout: DEFAULT) — primary content base
      Slide 4 (idx 3): Content canvas  (Layout: DEFAULT) — table-style content base
      Slide 5 (idx 4): Closing Page    (Layout: Closing Page) — mandatory, intact

  - OpenXML Deep-Cloning:
      1. Clones Slide 1  → Cover:    updates Title (shape name 'Title 1') and Date.
      2. Clones Slide 2  → Agenda:   100% intact (no mutation).
      3. Clones Slide 3  × N         → Dynamic content slides via DynamicGeometryEngineT1.
         (Slide 4 used as clone base for ACTION_TABLE pattern to match template DNA.)
      4. Clones Slide 5  → Closing:  100% intact corporate branding.
  - Prunes original 5 template slides from OpenXML package.
  - Returns binary bytes via io.BytesIO().
"""
from __future__ import annotations

import copy
import io
import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

import config
from core.renderers.dynamic_geometry_engine_t1 import DynamicGeometryEngineT1
from llm.dynamic_layout_schemas import (
    CardItem,
    ComparisonColumn,
    DynamicLayoutComposition,
    DynamicPresentationPlan,
    DynamicSlideDefinition,
    HeroBlock,
    KPIMetricItem,
    ProcessStepItem,
    TableDataGrid,
    TimelineItem,
)
from llm.schemas import PresentationPlan, SlideDefinition
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Slide indices inside the source PPTX
_IDX_COVER   = 0
_IDX_AGENDA  = 1
_IDX_CANVAS  = 2   # primary content canvas (cards, charts, KPIs)
_IDX_TABLE   = 3   # table-style canvas (ACTION_TABLE, DATA_MATRIX_TABLE)
_IDX_CLOSING = 4

# Patterns that map better to the table canvas (Slide 4)
_TABLE_CANVAS_PATTERNS = {"ACTION_TABLE", "DATA_MATRIX_TABLE"}


def _clone_slide(prs: Presentation, source_idx: int) -> Any:
    """
    Deep-clones a slide from the presentation at source_idx.
    Clones media relationships, remaps rId references, and copies solid background fill.
    """
    source_slide = prs.slides[source_idx]
    slide_layout = source_slide.slide_layout
    new_slide    = prs.slides.add_slide(slide_layout)

    # Ensure authentic warm sand (#F7F4EF) background fill for cloned slides
    if source_slide.background and source_slide.background.fill:
        try:
            if source_slide.background.fill.type == 1:  # SOLID
                new_slide.background.fill.solid()
                new_slide.background.fill.fore_color.rgb = source_slide.background.fill.fore_color.rgb
            else:
                new_slide.background.fill.solid()
                new_slide.background.fill.fore_color.rgb = RGBColor(0xF7, 0xF4, 0xEF)
        except Exception as e:
            logger.debug("Could not copy background fill: %s", e)
            new_slide.background.fill.solid()
            new_slide.background.fill.fore_color.rgb = RGBColor(0xF7, 0xF4, 0xEF)

    # Map old rId → new rId for media/embedded parts
    rId_map: Dict[str, str] = {}
    for rId, rel in source_slide.part.rels.items():
        if (
            "slideLayout"  not in rel.target_ref
            and "notesSlide"  not in rel.target_ref
            and "notesMaster" not in rel.target_ref
        ):
            try:
                new_rId = new_slide.part.relate_to(rel.target_part, rel.reltype)
                rId_map[rId] = new_rId
            except Exception as e:
                logger.debug("Could not relate part for rId %s: %s", rId, e)

    # Clear default placeholders injected by add_slide
    for s in list(new_slide.shapes):
        s.element.getparent().remove(s.element)

    # Deep-copy all shapes and remap relationship attributes
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
    """Sets text in-place preserving existing font/paragraph styles."""
    if not hasattr(shape, "text_frame"):
        return False
    tf      = shape.text_frame
    text_str = str(text).strip()

    if not tf.paragraphs:
        p   = tf.add_paragraph()
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

    for extra_p in tf.paragraphs[1:]:
        for r in extra_p.runs:
            r.text = ""
        extra_p.text = ""
    return True


def _clean_content_canvas(slide: Any) -> None:
    """
    Retains only the fixed master branding shapes:
      - Shape 0 (top decorative accent)
      - HeaderBar (dark espresso header background)
      - Title (Georgia amber gold title)
      - Subtitle (Calibri/Aptos subtitle)
      - Footer (bottom confidential text)
    Removes all template example shapes (dummy charts, KPI cards, retrospective rows,
    table rows) so the dynamic geometry engine renders on a 100% clean canvas.
    Defensively enforces branding dimensions to guarantee they never collapse to zero.
    """
    keep_names = {"headerbar", "title", "subtitle", "footer", "shape 0"}
    to_remove = []
    for shape in slide.shapes:
        nm = shape.name.lower().strip()
        if nm not in keep_names:
            to_remove.append(shape)
        else:
            # Defensive geometry guarantee: ensure branding shapes always retain valid dimensions
            if nm == "headerbar":
                shape.left = Inches(0.0)
                shape.top = Inches(-0.04)
                shape.width = Inches(13.333)
                shape.height = Inches(1.11)
            elif nm == "title":
                shape.left = Inches(0.67)
                shape.top = Inches(0.12)
                shape.width = Inches(12.00)
                shape.height = Inches(0.55)
            elif nm == "subtitle":
                shape.left = Inches(0.67)
                shape.top = Inches(0.65)
                shape.width = Inches(12.00)
                shape.height = Inches(0.38)
            elif nm == "footer":
                shape.left = Inches(0.67)
                shape.top = Inches(7.04)
                shape.width = Inches(8.00)
                shape.height = Inches(0.34)
            elif nm == "shape 0":
                shape.left = Inches(0.0)
                shape.top = Inches(0.0)
                shape.width = Inches(13.333)
                shape.height = Inches(0.12)

    for shape in to_remove:
        sp = shape._element
        sp.getparent().remove(sp)


def _set_cover_title(shape: Any, title: str, subtitle: Optional[str] = None) -> None:
    """Sets Cover Slide title with dynamic font scaling to prevent overlap with connector/date."""
    if not hasattr(shape, "text_frame"):
        return

    # Keep title block bounded strictly between Picture 3 (bottom 2.27") and Straight Connector 2 (top 5.95")
    shape.top = Inches(2.35)
    shape.left = Inches(0.55)
    shape.width = Inches(4.35)
    shape.height = Inches(3.20)

    tf = shape.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.0)
    tf.margin_top = Inches(0.0)
    tf.margin_right = Inches(0.05)
    tf.margin_bottom = Inches(0.0)
    try:
        tf.vertical_anchor = MSO_ANCHOR.TOP
    except Exception:
        pass

    p0 = tf.paragraphs[0]
    p0.text = ""
    run = p0.add_run()
    run.text = title.strip()
    run.font.name = "Verdana"
    run.font.bold = True

    # Scale font size dynamically to avoid overflowing into connector line
    title_len = len(title.strip())
    if title_len > 60:
        run.font.size = Pt(20)
    elif title_len > 40:
        run.font.size = Pt(22)
    elif title_len > 25:
        run.font.size = Pt(25)
    else:
        run.font.size = Pt(28)
    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    # Clear any extra paragraphs in the template placeholder
    for extra_p in tf.paragraphs[1:]:
        for r in extra_p.runs:
            r.text = ""
        extra_p.text = ""

    if subtitle and subtitle.strip():
        p1 = tf.add_paragraph()
        p1.space_before = Pt(6)
        run_sub = p1.add_run()
        run_sub.text = subtitle.strip()
        run_sub.font.name = "Verdana"
        run_sub.font.size = Pt(12) if title_len <= 45 else Pt(11)
        run_sub.font.bold = False
        run_sub.font.color.rgb = RGBColor(0xFA, 0xF7, 0xF3)


def _update_agenda_slide(agenda_slide: Any, dynamic_slides: List[DynamicSlideDefinition]) -> None:
    """Replaces dummy agenda in Slide 2 with dynamic, perfectly aligned slide titles & topics."""
    # Ensure warm sand background on Slide 2
    try:
        agenda_slide.background.fill.solid()
        agenda_slide.background.fill.fore_color.rgb = RGBColor(0xF7, 0xF4, 0xEF)
    except Exception:
        pass

    # 1. Seamless full-height dark brown panel for left half (0 to 6.444", 0 to 7.50")
    try:
        panel = agenda_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(6.444), Inches(7.50))
        panel.fill.solid()
        panel.fill.fore_color.rgb = RGBColor(0x35, 0x1C, 0x15)
        panel.line.fill.background()

        # Send panel to back behind Title 4 ("Agenda")
        spTree = agenda_slide.shapes._spTree
        elem = panel._element
        spTree.remove(elem)
        spTree.insert(2, elem)
    except Exception as e:
        logger.warning("[T1 Builder] Failed to add backing rectangle for agenda left panel: %s", e)

    # 2. Remove template's dummy Group 8 and stray slide number placeholder
    for sh in list(agenda_slide.shapes):
        sh_name_lc = sh.name.lower()
        if sh.name == "Group 8" or "slide number" in sh_name_lc or "slide_number" in sh_name_lc:
            sp = sh._element
            sp.getparent().remove(sp)

    # 3. Render up to 5 agenda items on the right warm sand panel (x: 6.444" to 13.333")
    items_to_render = dynamic_slides[:5]
    n_items = len(items_to_render)
    if n_items == 0:
        return

    # Symmetrical vertical centering calculation
    if n_items <= 3:
        row_gap = Inches(1.30)
        item_h = Inches(0.85)
    elif n_items == 4:
        row_gap = Inches(1.10)
        item_h = Inches(0.80)
    else:
        row_gap = Inches(0.92)
        item_h = Inches(0.75)

    total_block_h = (n_items - 1) * row_gap + item_h
    start_top = (Inches(7.50) - total_block_h) / 2

    for idx, s_def in enumerate(items_to_render, start=1):
        item_top = int(start_top + (idx - 1) * row_gap)

        # 1. Circle badge with number — cleanly positioned in right panel at x=7.10"
        badge = agenda_slide.shapes.add_shape(
            MSO_SHAPE.OVAL, Inches(7.10), item_top + Inches(0.02), Inches(0.42), Inches(0.42)
        )
        badge.fill.solid()
        badge.fill.fore_color.rgb = RGBColor(0x35, 0x1C, 0x15)
        badge.line.color.rgb = RGBColor(0xFF, 0xB5, 0x00)
        badge.line.width = Pt(1.75)

        btf = badge.text_frame
        btf.margin_top = Inches(0.02)
        btf.margin_left = Inches(0.0)
        btf.margin_right = Inches(0.0)
        btf.margin_bottom = Inches(0.0)
        bp = btf.paragraphs[0]
        bp.alignment = PP_ALIGN.CENTER
        br = bp.add_run()
        br.text = str(idx)
        br.font.name = "Aptos"
        br.font.size = Pt(13)
        br.font.bold = True
        br.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

        # 2. Text label for slide title & subtitle — spans x: 7.75" to 12.60"
        tb = agenda_slide.shapes.add_textbox(
            Inches(7.75), item_top, Inches(4.85), item_h
        )
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_top = Inches(0.0)
        tf.margin_left = Inches(0.0)
        tf.margin_right = Inches(0.0)
        tf.margin_bottom = Inches(0.0)

        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = s_def.title
        r.font.name = "Aptos"
        r.font.size = Pt(15.5) if n_items <= 4 else Pt(14)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0x35, 0x1C, 0x15)

        # Slide-level subtitle or clean takeaway
        sub_text = getattr(s_def, "subtitle", None) or s_def.executive_takeaway
        if sub_text and sub_text.strip():
            p_sub = tf.add_paragraph()
            p_sub.space_before = Pt(3)
            r_sub = p_sub.add_run()
            # Clean truncation at word boundaries rather than mid-word
            clean_sub = (
                textwrap.shorten(sub_text.strip(), width=75, placeholder="...")
                if len(sub_text.strip()) > 75
                else sub_text.strip()
            )
            r_sub.text = clean_sub
            r_sub.font.name = "Aptos"
            r_sub.font.size = Pt(10.5)
            r_sub.font.color.rgb = RGBColor(0x6E, 0x62, 0x59)


def _set_footer_text(shape: Any, text: str) -> None:
    """Updates Footer shape while preserving Calibri 10pt muted style."""
    if not hasattr(shape, "text_frame"):
        return
    tf = shape.text_frame
    p0 = tf.paragraphs[0]
    p0.text = text
    if p0.runs:
        r = p0.runs[0]
        r.font.name = "Calibri"
        r.font.size = Pt(10)
        r.font.color.rgb = RGBColor(0x7A, 0x65, 0x55)


def _convert_legacy_slide_to_dynamic(slide_def: SlideDefinition) -> DynamicSlideDefinition:
    """Converts a standard SlideDefinition into a DynamicSlideDefinition."""
    lt      = (slide_def.layout_type or "BULLETS").upper()
    content = slide_def.content or {}

    if lt in ("STATS", "STATISTICS"):
        stats   = content.get("statistics", [])
        metrics = [
            KPIMetricItem(
                value=str(s.get("value", "")),
                label=str(s.get("label", "")),
                delta=str(s.get("context", "")) if s.get("context") else None,
            )
            for s in stats if isinstance(s, dict)
        ]
        comp = DynamicLayoutComposition(
            pattern="METRIC_RIBBON_AND_CARDS",
            metrics=metrics,
            cards=[
                CardItem(
                    title="Key Performance Takeaway",
                    bullets=[slide_def.purpose or "Key benchmark metrics."],
                )
            ],
        )
    elif lt in ("EXECUTIVE_SUMMARY",):
        highlights = content.get("highlights", [])
        purpose_stmt = content.get("purpose_statement", "")
        if highlights:
            cards = [
                CardItem(
                    title=f"Core Priority {i + 1}",
                    tag=f"Pillar {i + 1}",
                    bullets=[str(h)],
                )
                for i, h in enumerate(highlights[:4])
            ]
        else:
            cards = [
                CardItem(
                    title="Executive Highlights",
                    bullets=[purpose_stmt or slide_def.purpose or "Executive program overview"],
                )
            ]
        comp = DynamicLayoutComposition(pattern="KEY_HIGHLIGHTS", cards=cards)
    elif lt in ("AGENDA",):
        agenda_items = content.get("agenda_items", [])
        if agenda_items:
            steps = [
                ProcessStepItem(
                    step_number=f"0{i + 1}",
                    title=str(item),
                    description="Session topic & key discussion points",
                    tag=f"Topic {i + 1}",
                )
                for i, item in enumerate(agenda_items[:5])
            ]
            comp = DynamicLayoutComposition(pattern="PROCESS_PIPELINE", steps=steps)
        else:
            comp = DynamicLayoutComposition(
                pattern="MULTI_COLUMN_CARDS",
                cards=[CardItem(title="Agenda", bullets=["Program Roadmap", "Key Topics"])],
            )
    elif lt in ("SECTION_HEADER",):
        sec_title = content.get("section_title", slide_def.title)
        sec_desc  = content.get("description", slide_def.purpose or "")
        comp = DynamicLayoutComposition(
            pattern="HERO_AND_SIDEBAR",
            hero=HeroBlock(headline=sec_title, subtext=sec_desc),
            cards=[
                CardItem(
                    title="Scope & Core Focus",
                    tag="Section",
                    bullets=[sec_desc] if sec_desc else ["Detailed breakdown and execution path."],
                )
            ],
        )
    elif lt in ("CONCLUSION",):
        summary_points  = content.get("summary_points", [])
        recommendations = content.get("recommendations", [])
        next_steps      = content.get("next_steps", [])
        cards = []
        if summary_points:
            cards.append(CardItem(title="Summary Takeaways", tag="Outcomes", bullets=[str(p) for p in summary_points[:4]]))
        if recommendations:
            cards.append(CardItem(title="Recommendations", tag="Decisions", bullets=[str(r) for r in recommendations[:4]]))
        if next_steps:
            cards.append(CardItem(title="Immediate Next Steps", tag="Milestones", bullets=[str(n) for n in next_steps[:4]]))
        if not cards:
            cards = [CardItem(title="Conclusions & Next Steps", bullets=[slide_def.purpose or "Key program takeaways."])]
        comp = DynamicLayoutComposition(pattern="MULTI_COLUMN_CARDS", cards=cards)
    elif lt in ("CARDS_2_COL", "TWO_COLUMN", "COMPARISON"):
        comp = DynamicLayoutComposition(
            pattern="COMPARISON_SPLIT",
            comparison=[
                ComparisonColumn(
                    heading=content.get("left_heading", "Option A"),
                    tag="Current State",
                    bullets=content.get("left_bullets", []),
                ),
                ComparisonColumn(
                    heading=content.get("right_heading", "Option B"),
                    tag="Target State",
                    bullets=content.get("right_bullets", []),
                ),
            ],
        )
    elif lt in ("CARDS_3_COL", "THREE_COLUMN", "PROCESS"):
        steps_data = content.get("steps", [])
        steps = [
            ProcessStepItem(
                step_number=str(st.get("step_number", i + 1)),
                title=str(st.get("title", f"Step {i + 1}")),
                description=str(st.get("description", "")),
            )
            for i, st in enumerate(steps_data) if isinstance(st, dict)
        ]
        if not steps:
            bullets = content.get("bullets", [])
            chunk   = max(1, len(bullets) // 3)
            comp    = DynamicLayoutComposition(
                pattern="MULTI_COLUMN_CARDS",
                cards=[
                    CardItem(title="Pillar 1", bullets=bullets[:chunk]),
                    CardItem(title="Pillar 2", bullets=bullets[chunk:2 * chunk]),
                    CardItem(title="Pillar 3", bullets=bullets[2 * chunk:]),
                ],
            )
        else:
            comp = DynamicLayoutComposition(pattern="PROCESS_PIPELINE", steps=steps)
    elif lt == "TABLE":
        t_data  = content.get("table_data", {})
        comp    = DynamicLayoutComposition(
            pattern="DATA_MATRIX_TABLE",
            table=TableDataGrid(
                headers=t_data.get("headers", ["Category", "Details"]),
                rows=t_data.get("rows", [["Item 1", "Value 1"]]),
            ),
        )
    elif lt in ("TIMELINE", "AWARDS"):
        items   = content.get("items", [])
        tl      = [
            TimelineItem(
                date=str(it.get("date", "")),
                event=str(it.get("event", "Milestone")),
                description=str(it.get("description", "")),
            )
            for it in items if isinstance(it, dict)
        ]
        comp = DynamicLayoutComposition(pattern="TIMELINE_ROADMAP", timeline=tl)
    elif lt == "ACTION_TABLE":
        rows = content.get("rows", [])
        cards = [
            CardItem(
                title=str(r.get("priority", "Action")),
                bullets=[str(r.get("action", ""))],
                tag=str(r.get("due", "")),
                footer=str(r.get("owner", "")),
            )
            for r in rows if isinstance(r, dict)
        ]
        ask_text = content.get("leadership_ask", "")
        comp = DynamicLayoutComposition(
            pattern="ACTION_TABLE",
            cards=cards,
            hero=HeroBlock(headline=ask_text) if ask_text else None,
        )
    else:
        # Default bullets → multi-column cards
        bullets = content.get("bullets", []) or [slide_def.purpose or "Core topic overview"]
        if len(bullets) >= 4:
            mid = len(bullets) // 2
            cards = [
                CardItem(title="Key Focus Areas", tag="Priority 1", bullets=bullets[:mid]),
                CardItem(title="Strategic Deliverables", tag="Priority 2", bullets=bullets[mid:]),
            ]
        else:
            cards = [CardItem(title="Key Strategic Points", bullets=bullets)]
        comp = DynamicLayoutComposition(pattern="MULTI_COLUMN_CARDS", cards=cards)

    return DynamicSlideDefinition(
        slide_number=slide_def.slide_number,
        title=slide_def.title,
        executive_takeaway=slide_def.purpose,
        layout_pattern=comp.pattern,
        composition=comp,
        speaker_notes=slide_def.speaker_notes,
    )


class Template1Builder:
    """
    100% Fidelity Slide Cloner & Dynamic Geometry Mutator for Template-1
    (AITransformationWeeklyUpdate4SEP2026.pptx).
    """

    def __init__(self, template_path: Optional[Path] = None):
        self.template_path = template_path or config.TEMPLATE1_FILE
        if not self.template_path.exists():
            raise FileNotFoundError(
                f"Template-1 not found at: {self.template_path}"
            )
        self.geometry_engine = DynamicGeometryEngineT1()

    def build(self, plan: Union[DynamicPresentationPlan, PresentationPlan]) -> bytes:
        """
        Builds the presentation by deep-cloning Template-1 slides and rendering
        dynamic layouts in the warm earth-tone brand style.
        """
        logger.info("Opening Template-1: %s", self.template_path)
        prs = Presentation(str(self.template_path))
        initial_count = len(prs.slides)
        logger.info("Template-1 catalog slides loaded: %d", initial_count)

        if initial_count < 5:
            raise ValueError(
                f"Template-1 must have exactly 5 slides. Found: {initial_count}"
            )

        # Normalize plan slides to DynamicSlideDefinition
        if isinstance(plan, DynamicPresentationPlan):
            dynamic_slides = plan.slides
            pres_title     = plan.title
            pres_date      = plan.date or datetime.now().strftime("%d%b%Y").upper()
            pres_subtitle  = plan.subtitle or ""
        else:
            pres_title    = plan.title
            pres_date     = datetime.now().strftime("%d%b%Y").upper()
            pres_subtitle = ""
            dynamic_slides = []
            for s in plan.slides:
                lt_up = (s.layout_type or "").upper()
                if lt_up in ("TITLE", "CLOSING"):
                    continue
                dynamic_slides.append(_convert_legacy_slide_to_dynamic(s))

        generated_slides: List[Any] = []

        # ===================================================================
        # 1. Deep-Clone Slide 1 (Cover Page)
        # ===================================================================
        logger.info("[T1 Builder] Cloning Cover Page (Slide 1)")
        cover = _clone_slide(prs, _IDX_COVER)
        generated_slides.append(cover)

        # Mutate title and date with overlap prevention
        for shape in cover.shapes:
            name_lc = shape.name.lower()
            if "title" in name_lc and hasattr(shape, "text_frame"):
                _set_cover_title(shape, pres_title, pres_subtitle)
            elif any(kw in name_lc for kw in ("date", "textbox 4")) and hasattr(shape, "text_frame"):
                _set_tf_text(shape, pres_date)

        # ===================================================================
        # 2. Deep-Clone Slide 2 (Agenda) — Dynamic Agenda Items
        # ===================================================================
        logger.info("[T1 Builder] Updating Agenda slide (Slide 2) with dynamic items")
        agenda = _clone_slide(prs, _IDX_AGENDA)
        _update_agenda_slide(agenda, dynamic_slides)
        generated_slides.append(agenda)

        # ===================================================================
        # 3. Duplicate Content Canvas N times
        # ===================================================================
        for s_idx, slide_def in enumerate(dynamic_slides, start=3):
            logger.info(
                "[T1 Builder] Duplicating content canvas for slide %d: '%s' (Pattern: %s)",
                s_idx, slide_def.title[:50], slide_def.layout_pattern,
            )

            content_slide = _clone_slide(prs, _IDX_CANVAS)
            # Guarantee authentic warm sand (#F7F4EF) background
            try:
                content_slide.background.fill.solid()
                content_slide.background.fill.fore_color.rgb = RGBColor(0xF7, 0xF4, 0xEF)
            except Exception:
                pass
            _clean_content_canvas(content_slide)
            generated_slides.append(content_slide)

            # Determine slide-specific contextual subtitle
            slide_sub = getattr(slide_def, "subtitle", None)
            if not slide_sub:
                comp = slide_def.composition
                if comp.cards:
                    tags = [c.tag or c.title for c in comp.cards if (c.tag or c.title)]
                    if tags:
                        slide_sub = " | ".join(tags[:3])
                elif comp.comparison:
                    tags = [c.tag or c.heading for c in comp.comparison if (c.tag or c.heading)]
                    if tags:
                        slide_sub = " | ".join(tags[:3])
                elif comp.steps:
                    tags = [s.title for s in comp.steps if s.title]
                    if tags:
                        slide_sub = " | ".join(tags[:3])
            if not slide_sub:
                slide_sub = pres_subtitle or slide_def.title

            # ── Set slide title, contextual subtitle & footer ────────────
            title_written = False
            for shape in content_slide.shapes:
                nm = shape.name
                if nm == "Title" and hasattr(shape, "text_frame"):
                    _set_tf_text(shape, slide_def.title)
                    title_written = True
                elif nm == "Subtitle" and hasattr(shape, "text_frame"):
                    _set_tf_text(shape, slide_sub)
                elif nm == "Footer" and hasattr(shape, "text_frame"):
                    footer_topic = pres_title[:45] if pres_title else "Program Transformation"
                    footer_date  = "Sep 2026"
                    footer_text  = f"UPS |  Confidential  |  {footer_topic}  |  {footer_date}"
                    _set_footer_text(shape, footer_text)

            if not title_written:
                # Fallback: first placeholder or text shape
                for shape in content_slide.shapes:
                    if shape.is_placeholder or hasattr(shape, "text_frame"):
                        try:
                            _set_tf_text(shape, slide_def.title)
                            break
                        except Exception:
                            pass

            # ── Render Dynamic Layout ─────────────────────────────────────
            try:
                self.geometry_engine.render_slide_content(content_slide, slide_def)
            except Exception as e:
                logger.error(
                    "[T1 Builder] Failed rendering layout for slide %d: %s",
                    s_idx, e, exc_info=True,
                )

            # ── Speaker Notes ─────────────────────────────────────────────
            if slide_def.speaker_notes:
                try:
                    content_slide.notes_slide.notes_text_frame.text = slide_def.speaker_notes
                except Exception:
                    pass

        # ===================================================================
        # 4. Deep-Clone Slide 5 (Closing Page) — 100% intact
        # ===================================================================
        logger.info("[T1 Builder] Appending Closing slide (Slide 5 — intact)")
        closing = _clone_slide(prs, _IDX_CLOSING)
        generated_slides.append(closing)

        # ===================================================================
        # 5. Prune the original 5 template blueprint slides
        # ===================================================================
        rId_attr = qn("r:id")
        sldIdLst = prs.slides._sldIdLst
        for _ in range(initial_count):
            sldId = sldIdLst[0]
            rId   = sldId.get(rId_attr)
            if rId:
                prs.part.drop_rel(rId)
            sldIdLst.remove(sldId)

        logger.info(
            "[T1 Builder] Successfully built %d slides. Blueprint slides pruned.",
            len(generated_slides),
        )

        # ===================================================================
        # 6. Serialize → io.BytesIO
        # ===================================================================
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        return buf.read()
