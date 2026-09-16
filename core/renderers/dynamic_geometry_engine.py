"""
core/renderers/dynamic_geometry_engine.py — Dynamic slide layout geometry calculator & renderer.

Renders arbitrary LLM-generated layout compositions inside the TechM_RefPPT-V3 content canvas.
Guarantees clean alignment, Aptos typography, TechM brand colors, and zero overlapping elements.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from llm.dynamic_layout_schemas import (
    CardItem,
    ComparisonColumn,
    DynamicLayoutComposition,
    DynamicSlideDefinition,
    HeroBlock,
    KPIMetricItem,
    ProcessStepItem,
    TableDataGrid,
    TimelineItem,
)
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# TechM Design System Tokens
# ---------------------------------------------------------------------------
COLOR_TECHM_RED = RGBColor(227, 24, 55)       # #E31837
COLOR_DARK_NAVY = RGBColor(27, 42, 74)        # #1B2A4A
COLOR_TEXT_PRIMARY = RGBColor(20, 25, 35)     # #141923
COLOR_TEXT_MUTED = RGBColor(100, 116, 139)    # #64748B
COLOR_BG_CARD = RGBColor(248, 249, 250)       # #F8F9FA
COLOR_BG_CARD_ALT = RGBColor(255, 255, 255)   # #FFFFFF
COLOR_BORDER = RGBColor(226, 232, 240)        # #E2E8F0
COLOR_BORDER_ACCENT = RGBColor(203, 213, 225) # #CBD5E1
COLOR_TAG_BG = RGBColor(241, 245, 249)        # #F1F5F9
COLOR_HIGHLIGHT_BG = RGBColor(254, 242, 242)  # #FEF2F2 (Soft Red tint)

FONT_FAMILY = "Aptos"
FONT_FAMILY_FALLBACK = "Calibri"


class DynamicGeometryEngine:
    """
    Renders dynamic visual layouts inside the 16:9 safe canvas of TechM_RefPPT-V3.
    """

    # Safe Content Bounding Box (in EMU)
    DEFAULT_LEFT = 350000       # 0.38 in
    DEFAULT_TOP = 850000        # 0.93 in (below header)
    DEFAULT_WIDTH = 11450000    # 12.52 in
    DEFAULT_HEIGHT = 5600000    # 6.12 in

    def __init__(self, font_name: str = FONT_FAMILY):
        self.font_name = font_name

    def render_slide_content(self, slide: Any, slide_def: DynamicSlideDefinition) -> None:
        """
        Renders the complete visual layout for a dynamic content slide.
        """
        curr_top = self.DEFAULT_TOP
        curr_height = self.DEFAULT_HEIGHT

        # 1. Render Executive Takeaway Banner (if provided)
        if slide_def.executive_takeaway:
            banner_height = 420000  # ~0.46 in
            self._render_executive_takeaway(
                slide,
                left=self.DEFAULT_LEFT,
                top=curr_top,
                width=self.DEFAULT_WIDTH,
                height=banner_height,
                takeaway_text=slide_def.executive_takeaway,
            )
            # Offset remaining canvas
            curr_top += banner_height + 180000  # ~0.20 in gap
            curr_height -= (banner_height + 180000)

        bounds = {
            "left": self.DEFAULT_LEFT,
            "top": curr_top,
            "width": self.DEFAULT_WIDTH,
            "height": curr_height,
        }

        comp = slide_def.composition
        pattern = (comp.pattern or "").upper()

        logger.info(
            "Rendering slide %d with dynamic pattern: %s",
            slide_def.slide_number,
            pattern,
        )

        if "METRIC_RIBBON" in pattern and comp.metrics:
            self._render_metric_ribbon_and_cards(slide, bounds, comp)
        elif "PROCESS" in pattern and comp.steps:
            self._render_process_pipeline(slide, bounds, comp.steps)
        elif "COMPARISON" in pattern and comp.comparison:
            self._render_comparison_split(slide, bounds, comp.comparison)
        elif "TABLE" in pattern and comp.table:
            self._render_data_matrix_table(slide, bounds, comp.table)
        elif "TIMELINE" in pattern and comp.timeline:
            self._render_timeline_roadmap(slide, bounds, comp.timeline)
        elif "HERO" in pattern and comp.hero:
            self._render_hero_and_sidebar(slide, bounds, comp)
        elif "KEY_HIGHLIGHTS" in pattern and comp.cards:
            self._render_key_highlights(slide, bounds, comp.cards)
        elif comp.cards:
            self._render_multi_column_cards(slide, bounds, comp.cards)
        else:
            # Fallback
            self._render_fallback(slide, bounds, comp)

    # -----------------------------------------------------------------------
    # Component Renderers
    # -----------------------------------------------------------------------

    def _render_executive_takeaway(
        self, slide: Any, left: int, top: int, width: int, height: int, takeaway_text: str
    ) -> None:
        """Renders a sleek executive takeaway banner under the header."""
        # Background container
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = COLOR_HIGHLIGHT_BG
        shape.line.color.rgb = COLOR_TECHM_RED
        shape.line.width = Pt(1.0)

        tf = shape.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.2)
        tf.margin_top = Inches(0.08)
        tf.margin_right = Inches(0.2)
        tf.margin_bottom = Inches(0.08)

        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT

        run_tag = p.add_run()
        run_tag.text = "KEY TAKEAWAY:  "
        run_tag.font.name = self.font_name
        run_tag.font.size = Pt(11)
        run_tag.font.bold = True
        run_tag.font.color.rgb = COLOR_TECHM_RED

        run_body = p.add_run()
        run_body.text = takeaway_text
        run_body.font.name = self.font_name
        run_body.font.size = Pt(11)
        run_body.font.bold = False
        run_body.font.color.rgb = COLOR_TEXT_PRIMARY

    def _render_metric_ribbon_and_cards(
        self, slide: Any, bounds: Dict[str, int], comp: DynamicLayoutComposition
    ) -> None:
        """Renders 2-4 KPI metric callouts on top + 2-3 content cards below."""
        metrics = comp.metrics or []
        cards = comp.cards or []

        ribbon_height = int(bounds["height"] * 0.32)
        cards_gap = 180000
        cards_top = bounds["top"] + ribbon_height + cards_gap
        cards_height = bounds["height"] - ribbon_height - cards_gap

        # Top KPI Ribbon
        n_metrics = min(max(len(metrics), 1), 4)
        m_gap = 150000
        total_m_gaps = (n_metrics - 1) * m_gap
        m_width = (bounds["width"] - total_m_gaps) // n_metrics

        for i, m in enumerate(metrics[:n_metrics]):
            m_left = bounds["left"] + i * (m_width + m_gap)
            self._draw_kpi_card(
                slide,
                left=m_left,
                top=bounds["top"],
                width=m_width,
                height=ribbon_height,
                value=m.value,
                label=m.label,
                delta=m.delta,
            )

        # Bottom Cards
        if cards:
            bottom_bounds = {
                "left": bounds["left"],
                "top": cards_top,
                "width": bounds["width"],
                "height": cards_height,
            }
            self._render_multi_column_cards(slide, bottom_bounds, cards)

    def _render_multi_column_cards(
        self, slide: Any, bounds: Dict[str, int], cards: List[CardItem]
    ) -> None:
        """Renders 2, 3, or 4 clean vertical cards with tags, titles, and bullets."""
        n_cards = min(max(len(cards), 1), 4)
        gap = 180000
        total_gaps = (n_cards - 1) * gap
        card_width = (bounds["width"] - total_gaps) // n_cards

        for i, card in enumerate(cards[:n_cards]):
            c_left = bounds["left"] + i * (card_width + gap)
            self._draw_content_card(
                slide,
                left=c_left,
                top=bounds["top"],
                width=card_width,
                height=bounds["height"],
                title=card.title,
                tag=card.tag,
                bullets=card.bullets,
                footer=card.footer,
            )

    def _render_process_pipeline(
        self, slide: Any, bounds: Dict[str, int], steps: List[ProcessStepItem]
    ) -> None:
        """Renders 3-5 sequential process chevrons / workflow step cards."""
        n_steps = min(max(len(steps), 1), 5)
        gap = 140000
        total_gaps = (n_steps - 1) * gap
        step_width = (bounds["width"] - total_gaps) // n_steps

        for i, step in enumerate(steps[:n_steps]):
            s_left = bounds["left"] + i * (step_width + gap)

            # Card background
            shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE, s_left, bounds["top"], step_width, bounds["height"]
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = COLOR_BG_CARD
            shape.line.color.rgb = COLOR_BORDER
            shape.line.width = Pt(1.0)

            # Step number badge at the top
            badge_h = 420000
            badge = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                s_left + 120000,
                bounds["top"] + 120000,
                step_width - 240000,
                badge_h,
            )
            badge.fill.solid()
            badge.fill.fore_color.rgb = COLOR_DARK_NAVY if i > 0 else COLOR_TECHM_RED
            badge.line.fill.background()

            btf = badge.text_frame
            btf.margin_top = Inches(0.04)
            bp = btf.paragraphs[0]
            bp.alignment = PP_ALIGN.CENTER
            brun = bp.add_run()
            brun.text = f"STEP {step.step_number}"
            brun.font.name = self.font_name
            brun.font.size = Pt(11)
            brun.font.bold = True
            brun.font.color.rgb = RGBColor(255, 255, 255)

            # Step Title & Description
            tf = shape.text_frame
            tf.word_wrap = True
            tf.margin_left = Inches(0.18)
            tf.margin_right = Inches(0.18)
            tf.margin_top = Inches(0.85)

            p_title = tf.paragraphs[0]
            p_title.alignment = PP_ALIGN.LEFT
            r_title = p_title.add_run()
            r_title.text = step.title
            r_title.font.name = self.font_name
            r_title.font.size = Pt(13)
            r_title.font.bold = True
            r_title.font.color.rgb = COLOR_TEXT_PRIMARY

            if step.tag:
                p_tag = tf.add_paragraph()
                p_tag.space_before = Pt(4)
                r_tag = p_tag.add_run()
                r_tag.text = f"[{step.tag}]"
                r_tag.font.name = self.font_name
                r_tag.font.size = Pt(9)
                r_tag.font.bold = True
                r_tag.font.color.rgb = COLOR_TECHM_RED

            p_desc = tf.add_paragraph()
            p_desc.space_before = Pt(8)
            r_desc = p_desc.add_run()
            r_desc.text = step.description
            r_desc.font.name = self.font_name
            r_desc.font.size = Pt(10.5)
            r_desc.font.color.rgb = COLOR_TEXT_MUTED

    def _render_comparison_split(
        self, slide: Any, bounds: Dict[str, int], cols: List[ComparisonColumn]
    ) -> None:
        """Renders 2 or 3 side-by-side contrast panels."""
        n_cols = min(max(len(cols), 1), 3)
        gap = 200000
        total_gaps = (n_cols - 1) * gap
        col_width = (bounds["width"] - total_gaps) // n_cols

        for i, col in enumerate(cols[:n_cols]):
            c_left = bounds["left"] + i * (col_width + gap)
            is_target = i == len(cols) - 1 and len(cols) > 1

            self._draw_content_card(
                slide,
                left=c_left,
                top=bounds["top"],
                width=col_width,
                height=bounds["height"],
                title=col.heading,
                tag=col.tag or ("Target State" if is_target else "Current State"),
                bullets=col.bullets,
                highlight_border=is_target,
            )

    def _render_data_matrix_table(
        self, slide: Any, bounds: Dict[str, int], table_data: TableDataGrid
    ) -> None:
        """Renders a structured, corporate-styled data table."""
        headers = table_data.headers or []
        rows = table_data.rows or []

        if not headers or not rows:
            return

        num_rows = min(len(rows) + 1, 8)
        num_cols = min(len(headers), 6)

        table_shape = slide.shapes.add_table(
            num_rows, num_cols, bounds["left"], bounds["top"], bounds["width"], bounds["height"]
        )
        table = table_shape.table

        # Format Headers
        for col_idx in range(num_cols):
            cell = table.cell(0, col_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = COLOR_DARK_NAVY
            cell.text = headers[col_idx]
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT
                for r in p.runs:
                    r.font.name = self.font_name
                    r.font.size = Pt(11)
                    r.font.bold = True
                    r.font.color.rgb = RGBColor(255, 255, 255)

        # Format Data Rows
        for row_idx, row in enumerate(rows[: num_rows - 1]):
            bg_color = COLOR_BG_CARD if row_idx % 2 == 0 else COLOR_BG_CARD_ALT
            for col_idx in range(num_cols):
                cell = table.cell(row_idx + 1, col_idx)
                cell.fill.solid()
                cell.fill.fore_color.rgb = bg_color
                val = row[col_idx] if col_idx < len(row) else ""
                cell.text = str(val)
                for p in cell.text_frame.paragraphs:
                    p.alignment = PP_ALIGN.LEFT
                    for r in p.runs:
                        r.font.name = self.font_name
                        r.font.size = Pt(10)
                        r.font.color.rgb = COLOR_TEXT_PRIMARY

    def _render_timeline_roadmap(
        self, slide: Any, bounds: Dict[str, int], timeline: List[TimelineItem]
    ) -> None:
        """Renders 3-5 sequential roadmap / milestone cards with connected chronology."""
        n_items = min(max(len(timeline), 1), 5)
        gap = 140000
        total_gaps = (n_items - 1) * gap
        item_width = (bounds["width"] - total_gaps) // n_items

        for i, item in enumerate(timeline[:n_items]):
            t_left = bounds["left"] + i * (item_width + gap)

            shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE, t_left, bounds["top"], item_width, bounds["height"]
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = COLOR_BG_CARD
            shape.line.color.rgb = COLOR_BORDER
            shape.line.width = Pt(1.0)

            # Date Pill
            pill_h = 360000
            pill = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                t_left + 120000,
                bounds["top"] + 120000,
                item_width - 240000,
                pill_h,
            )
            pill.fill.solid()
            pill.fill.fore_color.rgb = COLOR_TECHM_RED
            pill.line.fill.background()

            ptf = pill.text_frame
            ptf.margin_top = Inches(0.03)
            pp = ptf.paragraphs[0]
            pp.alignment = PP_ALIGN.CENTER
            pr = pp.add_run()
            pr.text = item.date
            pr.font.name = self.font_name
            pr.font.size = Pt(10.5)
            pr.font.bold = True
            pr.font.color.rgb = RGBColor(255, 255, 255)

            # Event Title & Details
            tf = shape.text_frame
            tf.word_wrap = True
            tf.margin_left = Inches(0.18)
            tf.margin_right = Inches(0.18)
            tf.margin_top = Inches(0.75)

            p_title = tf.paragraphs[0]
            r_title = p_title.add_run()
            r_title.text = item.event
            r_title.font.name = self.font_name
            r_title.font.size = Pt(12)
            r_title.font.bold = True
            r_title.font.color.rgb = COLOR_TEXT_PRIMARY

            p_desc = tf.add_paragraph()
            p_desc.space_before = Pt(8)
            r_desc = p_desc.add_run()
            r_desc.text = item.description
            r_desc.font.name = self.font_name
            r_desc.font.size = Pt(10)
            r_desc.font.color.rgb = COLOR_TEXT_MUTED

    def _render_hero_and_sidebar(
        self, slide: Any, bounds: Dict[str, int], comp: DynamicLayoutComposition
    ) -> None:
        """Renders 1/3 sidebar hero card + 2/3 main analytical cards."""
        hero = comp.hero
        cards = comp.cards or []

        sidebar_width = int(bounds["width"] * 0.32)
        gap = 180000
        main_left = bounds["left"] + sidebar_width + gap
        main_width = bounds["width"] - sidebar_width - gap

        # 1/3 Sidebar Hero
        if hero:
            shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                bounds["left"],
                bounds["top"],
                sidebar_width,
                bounds["height"],
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = COLOR_DARK_NAVY
            shape.line.fill.background()

            tf = shape.text_frame
            tf.word_wrap = True
            tf.margin_left = Inches(0.25)
            tf.margin_right = Inches(0.25)
            tf.margin_top = Inches(0.35)

            p_tag = tf.paragraphs[0]
            r_tag = p_tag.add_run()
            r_tag.text = "EXECUTIVE BRIEF"
            r_tag.font.name = self.font_name
            r_tag.font.size = Pt(10)
            r_tag.font.bold = True
            r_tag.font.color.rgb = COLOR_TECHM_RED

            p_head = tf.add_paragraph()
            p_head.space_before = Pt(10)
            r_head = p_head.add_run()
            r_head.text = hero.headline
            r_head.font.name = self.font_name
            r_head.font.size = Pt(16)
            r_head.font.bold = True
            r_head.font.color.rgb = RGBColor(255, 255, 255)

            p_sub = tf.add_paragraph()
            p_sub.space_before = Pt(10)
            r_sub = p_sub.add_run()
            r_sub.text = hero.subtext
            r_sub.font.name = self.font_name
            r_sub.font.size = Pt(11)
            r_sub.font.color.rgb = RGBColor(226, 232, 240)

        # 2/3 Main Grid
        if cards:
            main_bounds = {
                "left": main_left,
                "top": bounds["top"],
                "width": main_width,
                "height": bounds["height"],
            }
            self._render_multi_column_cards(slide, main_bounds, cards)

    def _render_key_highlights(
        self, slide: Any, bounds: Dict[str, int], cards: List[CardItem]
    ) -> None:
        """Renders 3-4 structured highlight cards with prominent accents."""
        self._render_multi_column_cards(slide, bounds, cards)

    def _render_fallback(
        self, slide: Any, bounds: Dict[str, int], comp: DynamicLayoutComposition
    ) -> None:
        """Safe fallback: renders a unified content card."""
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            bounds["left"],
            bounds["top"],
            bounds["width"],
            bounds["height"],
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = COLOR_BG_CARD
        shape.line.color.rgb = COLOR_BORDER

        tf = shape.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.3)
        tf.margin_top = Inches(0.3)
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = "Overview & Core Strategic Highlights"
        r.font.name = self.font_name
        r.font.size = Pt(14)
        r.font.bold = True
        r.font.color.rgb = COLOR_TEXT_PRIMARY

    # -----------------------------------------------------------------------
    # Primitive Drawing Helpers
    # -----------------------------------------------------------------------

    def _draw_kpi_card(
        self,
        slide: Any,
        left: int,
        top: int,
        width: int,
        height: int,
        value: str,
        label: str,
        delta: Optional[str] = None,
    ) -> None:
        """Renders a single high-impact KPI block."""
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = COLOR_BG_CARD
        shape.line.color.rgb = COLOR_BORDER
        shape.line.width = Pt(1.0)

        tf = shape.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.18)
        tf.margin_right = Inches(0.18)
        tf.margin_top = Inches(0.15)

        # Big Value Number
        p_val = tf.paragraphs[0]
        p_val.alignment = PP_ALIGN.LEFT
        r_val = p_val.add_run()
        r_val.text = value
        r_val.font.name = self.font_name
        r_val.font.size = Pt(28)
        r_val.font.bold = True
        r_val.font.color.rgb = COLOR_TECHM_RED

        # Label
        p_lbl = tf.add_paragraph()
        p_lbl.space_before = Pt(2)
        r_lbl = p_lbl.add_run()
        r_lbl.text = label
        r_lbl.font.name = self.font_name
        r_lbl.font.size = Pt(11)
        r_lbl.font.bold = True
        r_lbl.font.color.rgb = COLOR_TEXT_PRIMARY

        # Delta / Context
        if delta:
            p_del = tf.add_paragraph()
            p_del.space_before = Pt(2)
            r_del = p_del.add_run()
            r_del.text = delta
            r_del.font.name = self.font_name
            r_del.font.size = Pt(9.5)
            r_del.font.color.rgb = COLOR_TEXT_MUTED

    def _draw_content_card(
        self,
        slide: Any,
        left: int,
        top: int,
        width: int,
        height: int,
        title: str,
        tag: Optional[str] = None,
        bullets: Optional[List[str]] = None,
        footer: Optional[str] = None,
        highlight_border: bool = False,
    ) -> None:
        """Renders a structured content card with tag, title, and bullets."""
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = COLOR_BG_CARD
        shape.line.color.rgb = COLOR_TECHM_RED if highlight_border else COLOR_BORDER
        shape.line.width = Pt(1.5 if highlight_border else 1.0)

        tf = shape.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.2)
        tf.margin_right = Inches(0.2)
        tf.margin_top = Inches(0.2)

        # Tag
        if tag:
            p_tag = tf.paragraphs[0]
            r_tag = p_tag.add_run()
            r_tag.text = tag.upper()
            r_tag.font.name = self.font_name
            r_tag.font.size = Pt(9)
            r_tag.font.bold = True
            r_tag.font.color.rgb = COLOR_TECHM_RED
            p_title = tf.add_paragraph()
            p_title.space_before = Pt(4)
        else:
            p_title = tf.paragraphs[0]

        # Title
        r_title = p_title.add_run()
        r_title.text = title
        r_title.font.name = self.font_name
        r_title.font.size = Pt(13)
        r_title.font.bold = True
        r_title.font.color.rgb = COLOR_TEXT_PRIMARY

        # Bullets
        bullets = bullets or []
        for b_idx, bullet_text in enumerate(bullets):
            p_b = tf.add_paragraph()
            p_b.space_before = Pt(6)
            p_b.level = 0
            r_b = p_b.add_run()
            r_b.text = f"•  {bullet_text}"
            r_b.font.name = self.font_name
            r_b.font.size = Pt(10.5)
            r_b.font.color.rgb = COLOR_TEXT_PRIMARY

        # Optional bottom footer
        if footer:
            p_foot = tf.add_paragraph()
            p_foot.space_before = Pt(8)
            r_foot = p_foot.add_run()
            r_foot.text = footer
            r_foot.font.name = self.font_name
            r_foot.font.size = Pt(9.5)
            r_foot.font.italic = True
            r_foot.font.color.rgb = COLOR_TEXT_MUTED
