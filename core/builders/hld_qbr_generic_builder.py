"""
core/builders/hld_qbr_generic_builder.py — Generic, catalog-driven renderer
for the HLD QBR template.

Consumes llm.hld_qbr_generic_schemas.GenericHLDQBRPlan (produced by
core/presentation_planner_hld_qbr_generic.py) + templates/hld_qbr_assets/
inventory/layout_capability_catalog.json. Renders each slide by looking up
its shapes by shape_id (stable across clone, since _clone_slide deep-copies
the exact template XML) and setting values generically — no per-archetype
dispatch functions, no named topic fields.

Scope note (v1): covers the "slot-fill" pattern only — slides whose content
goes into the template's OWN pre-existing sample shapes (text/table/chart).
Blank-canvas composition (ad-hoc extra charts/tables beyond the slide's own
native ones, stat-highlight badges, process-flow chevrons, and the old rich
executive-summary bullet-cards) is not yet wired into this generic path.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_LEGEND_POSITION
from pptx.oxml.ns import qn
from pptx.util import Pt

import config
from core.builders.hld_qbr_builder import (
    TEMPLATE_SERIES_COLORS,
    _clone_slide,
    _fill_table_rows,
    _set_first_run_text,
    _strip_all_highlights,
    _strip_decorative_connectors,
    _strip_guidance_shapes,
)
from core.hld_qbr_catalog import STRUCTURAL_ONLY_SLIDE_IDS, get_entry
from llm.hld_qbr_generic_schemas import GenericHLDQBRPlan, SlideAssignment
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Default font sizes by slot kind, used when a slot's sample run had no
# explicit font.size captured (common — many runs inherit size from the
# layout/master rather than setting it directly on the run).
_DEFAULT_FONT_PT = {
    "placeholder_title": 20,
    "empty_title_box": 20,
    "text_box": 12,
    "auto_shape": 12,
}
TEXT_COLOR = RGBColor(0, 43, 73)


def _shape_by_id(slide: Any, shape_id: int) -> Optional[Any]:
    for shape in slide.shapes:
        if shape.shape_id == shape_id:
            return shape
    return None


def _clear_template_text(shapes: Any) -> None:
    """Blank cloned sample content while preserving the template geometry and
    formatting. Generated values are the only text subsequently written."""
    for shape in list(shapes):
        if getattr(shape, "has_text_frame", False):
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.text = ""
        if getattr(shape, "has_table", False):
            for row in shape.table.rows:
                for cell in row.cells:
                    cell.text = ""
        if getattr(shape, "shape_type", None) == 6:  # GROUP
            _clear_template_text(shape.shapes)


def _remove_unfilled_charts(slide: Any, assignment: Optional[SlideAssignment]) -> None:
    """A cloned chart retains its source workbook labels unless it is replaced
    with source-grounded data, so omit it when the assignment has no chart."""
    has_chart_data = bool(assignment and assignment.chart_categories and assignment.chart_series)
    if has_chart_data:
        return
    for shape in list(slide.shapes):
        if getattr(shape, "has_chart", False):
            shape.element.getparent().remove(shape.element)


def _set_text_generic(shape: Any, text: str, kind: str, sample_max_chars: Optional[int]) -> None:
    """Sets text generically, auto-scaling font size down a step when the new
    text is noticeably longer than what the slot was sized for. Multi-line
    text (e.g. a quote + attribution sharing one shape, as "\\n\\n"-separated
    lines) is distributed across the shape's EXISTING paragraphs positionally,
    preserving each paragraph's own formatting, instead of only ever touching
    paragraph 0 — generalizes to any multi-paragraph sample shape."""
    tf = shape.text_frame
    if not tf.paragraphs:
        return
    base_pt = _DEFAULT_FONT_PT.get(kind, 12)
    if sample_max_chars and len(text) > sample_max_chars:
        base_pt = max(8, base_pt - 2)

    lines = text.split("\n")
    existing_paras = list(tf.paragraphs)

    for i, para in enumerate(existing_paras):
        line = lines[i] if i < len(lines) else ""
        if para.runs:
            existing_size = para.runs[0].font.size
            para.runs[0].text = line
            for r in para.runs[1:]:
                r.text = ""
            if existing_size is None and line:
                para.runs[0].font.size = Pt(base_pt)
        elif line:
            run = para.add_run()
            run.text = line
            run.font.size = Pt(base_pt)

    for extra_line in lines[len(existing_paras):]:
        p = tf.add_paragraph()
        run = p.add_run()
        run.text = extra_line
        run.font.size = Pt(base_pt)


def _render_simple_slots(slide: Any, entry: Dict[str, Any], assignment: SlideAssignment) -> None:
    for slot in entry["slots"]:
        if slot["kind"] in ("table", "chart", "placeholder_title", "empty_title_box"):
            continue
        value = assignment.slot_values.get(slot["slot_id"])
        shape = _shape_by_id(slide, slot["shape_id"])
        if shape is None:
            continue
        if value:
            if shape.has_text_frame:
                _set_text_generic(shape, value, slot["kind"], slot.get("max_chars"))
        else:
            # Unfilled optional content shape — remove it rather than leave a
            # visible blank box occupying layout space.
            try:
                shape.element.getparent().remove(shape.element)
            except Exception:
                pass


def _render_auto_numbers(slide: Any, entry: Dict[str, Any], filled_count: int) -> None:
    """Sequence badges (e.g. achievement milestone numbers) next to whichever
    real content slots got filled — purely positional, auto-incrementing."""
    auto_ids = entry.get("auto_number_shape_ids") or []
    for i, shape_id in enumerate(auto_ids):
        shape = _shape_by_id(slide, shape_id)
        if shape is None or not shape.has_text_frame:
            continue
        if i < filled_count:
            _set_first_run_text(shape, str(i + 1))
        else:
            try:
                shape.element.getparent().remove(shape.element)
            except Exception:
                pass


def _render_repeat_groups(slide: Any, entry: Dict[str, Any], assignment: SlideAssignment) -> None:
    for rg in entry["repeat_groups"]:
        member_ids = rg["member_shape_ids"]
        items = assignment.repeat_items[: len(member_ids)]
        for i, shape_id in enumerate(member_ids):
            member = _shape_by_id(slide, shape_id)
            if member is None:
                continue
            if i >= len(items):
                try:
                    member.element.getparent().remove(member.element)
                except Exception:
                    pass
                continue
            item_values = items[i]
            text_children = sorted(
                (s for s in member.shapes if getattr(s, "has_text_frame", False)),
                key=lambda s: (round(s.top / 914400, 2), s.left),
            )
            for slot_def, child in zip(rg["item_slots"], text_children):
                value = item_values.get(slot_def["slot_id"])
                if value:
                    _set_text_generic(child, value, "auto_shape", slot_def.get("max_chars"))


def _render_table(slide: Any, entry: Dict[str, Any], assignment: SlideAssignment) -> None:
    table_slot = next((s for s in entry["slots"] if s["kind"] == "table"), None)
    if table_slot is None or not assignment.table_rows:
        return
    shape = _shape_by_id(slide, table_slot["shape_id"])
    if shape is None or not shape.has_table:
        return
    tbl = shape.table
    headers = assignment.table_headers or []
    for c_idx, header in enumerate(headers):
        if c_idx < len(tbl.columns):
            tbl.cell(0, c_idx).text = str(header)
    _fill_table_rows(tbl, assignment.table_rows, start_row=1, prune_unused_rows=False, text_color=TEXT_COLOR)


def _render_chart(slide: Any, entry: Dict[str, Any], assignment: SlideAssignment) -> None:
    chart_slot = next((s for s in entry["slots"] if s["kind"] == "chart"), None)
    if chart_slot is None or not (assignment.chart_categories and assignment.chart_series):
        return
    shape = _shape_by_id(slide, chart_slot["shape_id"])
    if shape is None or not shape.has_chart:
        return
    chart = shape.chart
    cd = CategoryChartData()
    cd.categories = assignment.chart_categories
    for series in assignment.chart_series:
        cd.add_series(series.name, series.values)
    chart.replace_data(cd)
    chart.has_title = False
    if len(assignment.chart_series) > 1:
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
    try:
        if chart.plots:
            for s_idx, series in enumerate(chart.plots[0].series):
                series.format.fill.solid()
                series.format.fill.fore_color.rgb = TEMPLATE_SERIES_COLORS[s_idx % len(TEMPLATE_SERIES_COLORS)]
    except Exception:
        pass


def _render_content_slide(prs: Presentation, assignment: SlideAssignment) -> None:
    entry = get_entry(assignment.slide_id)
    if entry is None:
        logger.warning("Skipping unknown slide_id %s", assignment.slide_id)
        return
    slide = _clone_slide(prs, entry["source_slide_index"])
    _strip_guidance_shapes(slide)
    _strip_decorative_connectors(slide)
    _clear_template_text(slide.shapes)
    _remove_unfilled_charts(slide, assignment)

    if assignment.title is not None:
        title_slot = next(
            (s for s in entry["slots"] if s["kind"] in ("placeholder_title", "empty_title_box")), None
        )
        if title_slot is not None:
            shape = _shape_by_id(slide, title_slot["shape_id"])
            if shape is not None and shape.has_text_frame:
                _set_text_generic(shape, assignment.title.upper(), title_slot["kind"], title_slot.get("max_chars"))

    _render_simple_slots(slide, entry, assignment)
    filled_simple_count = sum(1 for v in assignment.slot_values.values() if v)
    _render_auto_numbers(slide, entry, filled_simple_count)
    _render_repeat_groups(slide, entry, assignment)
    _render_table(slide, entry, assignment)
    _render_chart(slide, entry, assignment)


def _render_cover(prs: Presentation, plan: GenericHLDQBRPlan) -> None:
    entry = get_entry("slide_00")
    slide = _clone_slide(prs, entry["source_slide_index"])
    _clear_template_text(slide.shapes)
    for slot in entry["slots"]:
        shape = _shape_by_id(slide, slot["shape_id"])
        if shape is None or not shape.has_text_frame:
            continue
        if "date" in slot["slot_id"]:
            _set_first_run_text(shape, plan.date)
        else:
            # Every other cover text shape (title box, hero banner) shows the
            # presentation title — never left blank, no second content source
            # exists for the cover besides the title/date.
            _set_text_generic(shape, plan.presentation_title, slot["kind"], slot.get("max_chars"))


def _render_agenda(prs: Presentation, agenda_title: str, content_titles: List[str]) -> None:
    entry = get_entry("slide_01")
    slide = _clone_slide(prs, entry["source_slide_index"])
    _clear_template_text(slide.shapes)
    # The agenda has exactly 2 slots: a short title and a multi-line topics box
    # (the topics box is identified generically as whichever slot allows the
    # most characters — it's always the larger of the two on this slide).
    topics_slot = max(entry["slots"], key=lambda s: s.get("max_chars") or 0)
    title_slot = next((slot for slot in entry["slots"] if slot != topics_slot), None)
    if title_slot is not None:
        title_shape = _shape_by_id(slide, title_slot["shape_id"])
        if title_shape is not None and title_shape.has_text_frame:
            _set_text_generic(title_shape, agenda_title, title_slot["kind"], title_slot.get("max_chars"))
    shape = _shape_by_id(slide, topics_slot["shape_id"])
    if shape is not None and shape.has_text_frame and content_titles:
        joined = "\n".join(content_titles)
        max_chars = topics_slot.get("max_chars") or 250
        while len(joined) > max_chars and len(content_titles) > 1:
            content_titles = content_titles[:-1]
            joined = "\n".join(content_titles)
        tf = shape.text_frame
        p0 = tf.paragraphs[0]
        lines = joined.split("\n")
        if p0.runs:
            p0.runs[0].text = lines[0]
            for r in p0.runs[1:]:
                r.text = ""
        for extra_line in lines[1:]:
            p = tf.add_paragraph()
            p.text = extra_line


# Brand tagline + legal footer on the closing slide — required verbatim
# copy per guardrails.md, not per-engagement sample content, so it is never
# routed through the LLM like everything else on a generated slide.
_CLOSING_TAGLINE = "MOVING OUR WORLD FORWARD BY DELIVERING WHAT MATTERS\u2122"
_CLOSING_LEGAL_FOOTER = (
    "Proprietary and Confidential: This presentation may not be used or disclosed to "
    "other than employees or customers, unless expressly authorized by UPS.\u000b"
    "\u00a9 2026 United Parcel Service of America, Inc. UPS, the UPS brandmark and the "
    "color brown are trademarks of United Parcel Service of America, Inc. All rights reserved."
)


def _render_closing(prs: Presentation) -> None:
    entry = get_entry("slide_30")
    slide = _clone_slide(prs, entry["source_slide_index"])
    _clear_template_text(slide.shapes)
    texts_by_max_chars_desc = sorted(entry["slots"], key=lambda s: -(s.get("max_chars") or 0))
    for slot, text in zip(texts_by_max_chars_desc, (_CLOSING_LEGAL_FOOTER, _CLOSING_TAGLINE)):
        shape = _shape_by_id(slide, slot["shape_id"])
        if shape is not None and shape.has_text_frame:
            _set_text_generic(shape, text, slot["kind"], slot.get("max_chars"))


class HLDQBRGenericBuilder:
    """Generic counterpart to core.builders.hld_qbr_builder.HLDQBRBuilder."""

    def build(self, plan: GenericHLDQBRPlan) -> bytes:
        prs = Presentation(str(config.HLD_QBR_TEMPLATE_FILE))
        initial_count = len(prs.slides)

        content_slides = [s for s in plan.slides if s.slide_id not in STRUCTURAL_ONLY_SLIDE_IDS]
        exec_summary = next((s for s in content_slides if s.slide_id == "slide_03"), None)
        other_content = [s for s in content_slides if s.slide_id != "slide_03"]

        _render_cover(prs, plan)
        content_titles = [s.title for s in content_slides if s.title]
        _render_agenda(prs, plan.presentation_title, content_titles)
        if exec_summary is not None:
            _render_content_slide(prs, exec_summary)
        for assignment in other_content:
            _render_content_slide(prs, assignment)
        _render_closing(prs)

        # Prune the original 60 source slides, leaving only the generated ones
        # (new slides are always appended, so the originals are the first
        # initial_count entries in the slide id list).
        rId_attr = qn("r:id")
        sldIdLst = prs.slides._sldIdLst
        for _ in range(initial_count):
            sldId = sldIdLst[0]
            rId = sldId.get(rId_attr)
            if rId:
                prs.part.drop_rel(rId)
            sldIdLst.remove(sldId)

        logger.info("[HLD QBR Generic Builder] Built %d slides.", len(prs.slides))

        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()
