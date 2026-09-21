"""
core/builders/hld_qbr_builder.py — Deep-clone builder for the HLD QBR Template
(UPS Healthcare Quarterly Business Review format).

Architecture (see HLD_QBR_TEMPLATE_PLAN.md for the full analysis):
  - Loads the 60-slide HLD QBR working copy (config.HLD_QBR_TEMPLATE_FILE).
  - OpenXML deep-clones only the specific CORE archetype slides needed for
    THIS plan (Cover/Agenda/Closing always; every other section only if the
    plan actually has content for it — graceful degradation, no filler).
  - Strips, on every cloned slide: guidance/instruction boxes (regex),
    decorative status-dot icons left over from the source slide's original
    column meaning, and stray text-highlight "replace me" markers.
  - Prunes the original 60 template slides, leaving only the generated ones.
  - Returns binary bytes via io.BytesIO().
"""
from __future__ import annotations

import copy
import io
import math
import re
from typing import Any, Dict, List, Optional

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_LEGEND_POSITION
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.parts.chart import ChartPart
from pptx.util import Inches, Pt

import config
from llm.hld_qbr_schemas import HLDQBRPresentationPlan
from utils.logging_utils import get_logger

logger = get_logger(__name__)

IDX_COVER = 0
IDX_AGENDA = 1
IDX_EXECUTIVE_SUMMARY = 3
IDX_ORG_STRUCTURE = 2
IDX_ACHIEVEMENTS = 4
IDX_PRIORITIES = 5
IDX_SECTION_PERF_MGMT = 11
IDX_TRACKER = 9
IDX_OPERATIONAL_CHART = 13
IDX_KPI_DASHBOARD = 12
IDX_VOICE_OF_CUSTOMER = 10
IDX_SECTION_CIP = 21
IDX_GEMBA_WALK = 22
IDX_CI_TRACKER = 23
IDX_SECTION_QUALITY = 24
IDX_QUALITY_ORG = 25
IDX_NC_REVIEW = 26
IDX_NC_TRACKER = 27
IDX_NEXT_STEPS = 29
IDX_CLOSING = 30

GUIDANCE_REGEX = re.compile(
    r"required content|required slide|\bexample\b|optional \||format option|"
    r"additional slides available|must be updated|formulas in notes",
    re.IGNORECASE,
)


def _clone_slide(prs: Presentation, source_idx: int) -> Any:
    """Deep-clones a slide, remapping media relationships and stripping template
    authoring artifacts (guidance boxes, decorative dots, highlight markers)."""
    source_slide = prs.slides[source_idx]
    slide_layout = source_slide.slide_layout
    new_slide = prs.slides.add_slide(slide_layout)

    if source_slide.background and source_slide.background.fill:
        try:
            if source_slide.background.fill.type == 1:  # SOLID
                new_slide.background.fill.solid()
                new_slide.background.fill.fore_color.rgb = source_slide.background.fill.fore_color.rgb
        except Exception:
            pass

    rId_map: Dict[str, str] = {}
    pkg = prs.part.package
    for rId, rel in source_slide.part.rels.items():
        if (
            "slideLayout" not in rel.target_ref
            and "notesSlide" not in rel.target_ref
            and "notesMaster" not in rel.target_ref
        ):
            try:
                if isinstance(rel.target_part, ChartPart):
                    # Decouple chart part: clone independently so slides never share chart parts or excel workbooks
                    source_chart_part = rel.target_part
                    new_chart_partname = pkg.next_partname("/ppt/charts/chart%d.xml")
                    new_chart_part = ChartPart.load(
                        new_chart_partname,
                        source_chart_part.content_type,
                        pkg,
                        source_chart_part.blob,
                    )
                    new_chart_part._element._remove_externalData()
                    for c_rId, c_rel in source_chart_part.rels.items():
                        if "chartStyle" in c_rel.reltype or "chartColorStyle" in c_rel.reltype:
                            new_chart_part.relate_to(c_rel.target_part, c_rel.reltype)
                    new_rId = new_slide.part.relate_to(new_chart_part, RT.CHART)
                    rId_map[rId] = new_rId
                else:
                    new_rId = new_slide.part.relate_to(rel.target_part, rel.reltype)
                    rId_map[rId] = new_rId
            except Exception:
                pass

    for s in list(new_slide.shapes):
        s.element.getparent().remove(s.element)

    for shape in source_slide.shapes:
        new_el = copy.deepcopy(shape.element)
        for elem in new_el.xpath(".//*[@r:embed or @r:link or @r:id]"):
            for attr in list(elem.attrib.keys()):
                if attr.endswith("embed") or attr.endswith("link") or attr.endswith("}id") or attr == "r:id":
                    old_val = elem.attrib[attr]
                    if old_val in rId_map:
                        elem.attrib[attr] = rId_map[old_val]
        new_slide.shapes._spTree.append(new_el)

    _strip_all_highlights(new_slide)
    return new_slide


def _strip_all_highlights(slide: Any) -> int:
    """Removes <a:highlight> marks (e.g. the template's magenta '[CUSTOMER NAME]'
    replace-me flag) slide-wide, including inside table cells."""
    removed = 0
    text_frames = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            text_frames.append(shape.text_frame)
        if shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    text_frames.append(cell.text_frame)
    for tf in text_frames:
        for para in tf.paragraphs:
            for run in para.runs:
                rPr = run._r.find(qn("a:rPr"))
                if rPr is None:
                    continue
                hl = rPr.find(qn("a:highlight"))
                if hl is not None:
                    rPr.remove(hl)
                    removed += 1
    return removed


def _strip_guidance_shapes(slide: Any) -> int:
    """Removes any shape whose text matches the guidance-box vocabulary."""
    removed = 0
    for shape in list(slide.shapes):
        if shape.has_text_frame and GUIDANCE_REGEX.search(shape.text_frame.text):
            shape.element.getparent().remove(shape.element)
            removed += 1
    return removed


def _strip_decorative_connectors(slide: Any) -> int:
    """Removes leftover red/yellow/green 'Flowchart: Connector' status-dot icons
    tied to one specific column's meaning in the ORIGINAL template slide."""
    removed = 0
    for shape in list(slide.shapes):
        if shape.name.startswith("Flowchart: Connector"):
            shape.element.getparent().remove(shape.element)
            removed += 1
    return removed


def _shape_by_name(slide: Any, name: str) -> Optional[Any]:
    for shape in slide.shapes:
        if shape.name == name:
            return shape
    return None


def _remove_shapes(slide: Any, predicate) -> int:
    """Removes every shape matching predicate(shape) -> bool. Used to clear a
    cloned slide's fixed decorative/placeholder shapes before freeform rendering."""
    removed = 0
    for shape in list(slide.shapes):
        if predicate(shape):
            shape.element.getparent().remove(shape.element)
            removed += 1
    return removed


def _set_first_run_text(shape: Any, text: str) -> None:
    """Sets paragraph-0 text in-place, preserving existing run formatting."""
    tf = shape.text_frame
    if not tf.paragraphs:
        return
    p0 = tf.paragraphs[0]
    if p0.runs:
        p0.runs[0].text = text
        for r in p0.runs[1:]:
            r.text = ""
    else:
        p0.text = text


def _set_cover_breadcrumb_blank(cover_slide: Any) -> None:
    """Blanks the center banner text (Rectangle 6) — the title lives in the
    right-corner Title 5 box; a duplicate title crammed into the narrow center
    zone reads as unprofessional (see HLD_QBR_TEMPLATE_PLAN.md follow-ups)."""
    shape = _shape_by_name(cover_slide, "Rectangle 6")
    if shape is None:
        return
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            run.text = ""


def _set_cover_title(cover_slide: Any, text: str) -> None:
    """Fills Title 5 (right-corner box). Ships EMPTY in the template (only an
    <a:endParaRPr>, no run) at Verdana 22pt Bold; longer text must shrink."""
    shape = _shape_by_name(cover_slide, "Title 5")
    if shape is None:
        return
    tf = shape.text_frame
    if not tf.paragraphs:
        return
    p0 = tf.paragraphs[0]
    if p0.runs:
        p0.runs[0].text = text
        for r in p0.runs[1:]:
            r.text = ""
        run = p0.runs[0]
    else:
        run = p0.add_run()
        run.text = text
    if len(text) > 24:
        run.font.size = Pt(14)
    elif len(text) > 16:
        run.font.size = Pt(18)


def _set_org_box(shape: Any, name: str, role: str) -> None:
    """Org-chart person card: paragraph 0 = name, paragraph 1 = role."""
    paras = shape.text_frame.paragraphs
    for i, val in enumerate((name, role)):
        if i < len(paras) and paras[i].runs:
            paras[i].runs[0].text = val
            for r in paras[i].runs[1:]:
                r.text = ""


def _set_or_remove_facility_placeholder(slide: Any, facility_name: str) -> None:
    """Fills Text Placeholder 3 with the facility name if provided; otherwise
    removes the placeholder element entirely so PowerPoint doesn't show ghost
    prompts like 'Sub-header' or 'Facility name or location'."""
    ph = _shape_by_name(slide, "Text Placeholder 3")
    if ph is not None:
        if facility_name and facility_name.strip():
            _set_first_run_text(ph, facility_name.strip())
        else:
            slide.shapes._spTree.remove(ph._element)


def _fill_priority_group(
    group_shape: Any,
    heading: str,
    body: str,
    center_x: Optional[int] = None,
    card_width: Optional[int] = None,
    target_body_top: int = 4220000,
) -> None:
    # 1. Update group bounds and child shape positions if center_x and card_width are provided
    if center_x is not None and card_width is not None:
        new_left = center_x - (card_width // 2)
        grp_xfrm = group_shape._element.find(qn("p:grpSpPr")).find(qn("a:xfrm"))
        if grp_xfrm is not None:
            off = grp_xfrm.find(qn("a:off"))
            ext = grp_xfrm.find(qn("a:ext"))
            chOff = grp_xfrm.find(qn("a:chOff"))
            chExt = grp_xfrm.find(qn("a:chExt"))
            if off is not None:
                off.set("x", str(new_left))
            if ext is not None:
                ext.set("cx", str(card_width))
            if chOff is not None:
                chOff.set("x", str(new_left))
            if chExt is not None:
                chExt.set("cx", str(card_width))

        # Center the circle and icon inside the group
        for s in group_shape.shapes:
            if s.name.startswith("Oval") or s.name.startswith("Freeform"):
                s.left = center_x - (s.width // 2)

    # 2. Identify heading & body text boxes
    text_boxes = [
        s for s in group_shape.shapes
        if getattr(s, "has_text_frame", False) and (s.shape_type == 17 or "Shape;" in s.name)
    ]
    text_boxes.sort(key=lambda s: s.top)
    if len(text_boxes) >= 2:
        heading_sub = text_boxes[0]
        body_sub = text_boxes[1]
    else:
        heading_sub = None
        body_sub = None
        for sub in group_shape.shapes:
            if not getattr(sub, "has_text_frame", False):
                continue
            current = sub.text_frame.text.strip().upper()
            if current.startswith("PRIORITY"):
                heading_sub = sub
            elif "SUPPORTING" in current:
                body_sub = sub

    if heading_sub and body_sub:
        # Widen heading & body boxes to card_width if provided, or match body width
        if center_x is not None and card_width is not None:
            new_left = center_x - (card_width // 2)
            heading_sub.left = new_left
            heading_sub.width = card_width
            body_sub.left = new_left
            body_sub.width = card_width
        else:
            heading_sub.left = body_sub.left
            heading_sub.width = body_sub.width

        # Heading formatting: STRICT 14PT BOLD across ALL cards (per template guideline)
        heading_sub.text_frame.word_wrap = True
        p_head = heading_sub.text_frame.paragraphs[0]
        p_head.text = heading

        # Strip 150% line spacing from the template paragraph so it renders single-spaced
        pPr = p_head._p.find(qn("a:pPr"))
        if pPr is not None:
            lnSpc = pPr.find(qn("a:lnSpc"))
            if lnSpc is not None:
                pPr.remove(lnSpc)

        if p_head.runs:
            run_h = p_head.runs[0]
            run_h.font.bold = True
            run_h.font.size = Pt(14)  # STRICT 14PT BOLD FOR ALL CARDS PER TEMPLATE GUIDELINE

        # Body formatting: dynamically auto-scale if text volume is high
        body_sub.text_frame.word_wrap = True
        p_body = body_sub.text_frame.paragraphs[0]
        p_body.text = body
        if p_body.runs:
            run_b = p_body.runs[0]
            if len(body) > 220 or target_body_top >= 4450000:
                run_b.font.size = Pt(10.5)
            elif len(body) > 160:
                run_b.font.size = Pt(11.0)
            else:
                run_b.font.size = Pt(12.0)

        # Set body baseline top coordinate to ensure clean spacing and alignment
        body_sub.top = target_body_top
    elif heading_sub:
        _set_first_run_text(heading_sub, heading)
    elif body_sub:
        _set_first_run_text(body_sub, body)



def _fill_table_rows(
    tbl: Any,
    rows: List[List[str]],
    start_row: int = 1,
    prune_unused_rows: bool = True,
) -> None:
    """Fills table rows with dynamic typography, cell margins, and row pruning."""
    if not rows:
        return
    max_cell_len = max(len(str(val)) for row in rows for val in row) if rows else 0
    if max_cell_len > 100:
        font_sz = Pt(9.0)
    elif max_cell_len > 60:
        font_sz = Pt(10.0)
    elif max_cell_len > 35:
        font_sz = Pt(10.5)
    else:
        font_sz = Pt(11.0)

    for r_offset, row_values in enumerate(rows):
        r_idx = start_row + r_offset
        if r_idx >= len(tbl.rows):
            break
        for c_idx, val in enumerate(row_values):
            if c_idx < len(tbl.columns):
                cell = tbl.cell(r_idx, c_idx)
                cell.text = str(val)
                cell.margin_top = Inches(0.04)
                cell.margin_bottom = Inches(0.04)
                cell.margin_left = Inches(0.06)
                cell.margin_right = Inches(0.06)
                for para in cell.text_frame.paragraphs:
                    for run in para.runs:
                        run.font.name = "Verdana"
                        run.font.size = font_sz

    used_through = start_row + len(rows)
    if prune_unused_rows:
        while len(tbl.rows) > used_through:
            last_tr = tbl.rows[len(tbl.rows) - 1]._tr
            tbl._tbl.remove(last_tr)
    else:
        for r_idx in range(used_through, len(tbl.rows)):
            for c_idx in range(len(tbl.columns)):
                tbl.cell(r_idx, c_idx).text = ""


class HLDQBRBuilder:
    """Builds an HLD QBR-branded .pptx from a validated HLDQBRPresentationPlan."""

    def __init__(self, template_path=None):
        self.template_path = template_path or config.HLD_QBR_TEMPLATE_FILE

    def build(self, plan: HLDQBRPresentationPlan) -> bytes:
        prs = Presentation(str(self.template_path))
        initial_count = len(prs.slides)

        # 1. Cover (always)
        cover = _clone_slide(prs, IDX_COVER)
        _set_cover_breadcrumb_blank(cover)
        date_ph = _shape_by_name(cover, "Date Placeholder 1")
        if date_ph is not None and plan.date:
            _set_first_run_text(date_ph, plan.date)
        _set_cover_title(cover, plan.presentation_title)

        # 2. Agenda (always; falls back to template's default topics if none given)
        agenda = _clone_slide(prs, IDX_AGENDA)
        if plan.agenda_topics:
            agenda_box = _shape_by_name(agenda, "TextBox 7")
            if agenda_box is not None:
                tf = agenda_box.text_frame
                tf.clear()
                n_topics = len(plan.agenda_topics)
                if n_topics <= 3:
                    ag_sz = Pt(18)
                    spc_after = Pt(16)
                elif n_topics <= 5:
                    ag_sz = Pt(16)
                    spc_after = Pt(12)
                else:
                    ag_sz = Pt(14)
                    spc_after = Pt(8)

                for i, topic in enumerate(plan.agenda_topics):
                    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                    p.text = topic
                    p.space_after = spc_after
                    for r in p.runs:
                        r.font.name = "Verdana"
                        r.font.size = ag_sz
                        r.font.color.rgb = RGBColor(0, 43, 73)

        # 3. Executive Summary (always mandatory)
        exec_summary = _clone_slide(prs, IDX_EXECUTIVE_SUMMARY)
        _strip_guidance_shapes(exec_summary)

        # 4. Organizational Structure (optional)
        if plan.org_structure:
            org_slide = _clone_slide(prs, IDX_ORG_STRUCTURE)
            org_boxes = sorted(
                (s for s in org_slide.shapes if s.name.startswith("Rectangle: Rounded Corners")),
                key=lambda s: (s.top, s.left),
            )
            for box, person in zip(org_boxes, plan.org_structure):
                if person.name:
                    _set_org_box(box, person.name, person.role)
            # Blank leftover template sample cards beyond the supplied people
            for box in org_boxes[len(plan.org_structure):]:
                _set_org_box(box, "", "")

        # 4. Previous Quarter Achievements (optional)
        if plan.achievements:
            achievements_slide = _clone_slide(prs, IDX_ACHIEVEMENTS)
            _strip_guidance_shapes(achievements_slide)
            _set_or_remove_facility_placeholder(achievements_slide, plan.facility_name)
            milestone_boxes = sorted(
                (s for s in achievements_slide.shapes if s.name == "Content Placeholder 42"),
                key=lambda s: s.top,
            )
            connectors = sorted(
                (s for s in achievements_slide.shapes if s.name.startswith("Flowchart: Connector")),
                key=lambda s: s.top,
            )

            n_ach = len(plan.achievements)
            max_ach_len = max(len(t) for t in plan.achievements) if plan.achievements else 0

            # Dynamic vertical spacing: distribute evenly across canvas
            TOP_MIN = 1200000  # ~1.31 inches
            TOP_MAX = 5400000  # ~5.91 inches
            spacing = (TOP_MAX - TOP_MIN) // (n_ach - 1) if n_ach > 1 else 0

            # Dynamic typography scaling
            if max_ach_len > 140 or n_ach >= 5:
                ach_font_sz = Pt(11.0)
            elif max_ach_len > 80:
                ach_font_sz = Pt(12.5)
            else:
                ach_font_sz = Pt(13.5)

            for i, (text, box, conn) in enumerate(zip(plan.achievements, milestone_boxes, connectors)):
                new_top = TOP_MIN + i * spacing if n_ach > 1 else (TOP_MIN + TOP_MAX) // 2
                conn.top = int(new_top)
                box.top = int(new_top)
                box.height = int(Inches(0.65))
                box.text_frame.word_wrap = True

                p = box.text_frame.paragraphs[0]
                p.text = text
                pPr = p._p.find(qn("a:pPr"))
                if pPr is not None:
                    lnSpc = pPr.find(qn("a:lnSpc"))
                    if lnSpc is not None:
                        pPr.remove(lnSpc)
                for r in p.runs:
                    r.font.name = "Verdana"
                    r.font.size = ach_font_sz
                    r.font.color.rgb = RGBColor(0, 43, 73)

                p_c = conn.text_frame.paragraphs[0]
                p_c.text = str(i + 1)
                for r in p_c.runs:
                    r.font.name = "Verdana"
                    r.font.bold = True
                    r.font.size = Pt(12)

            for box in milestone_boxes[n_ach:]:
                achievements_slide.shapes._spTree.remove(box._element)
            for conn in connectors[n_ach:]:
                achievements_slide.shapes._spTree.remove(conn._element)

        # 5. Customer Priorities (optional)
        if plan.priorities:
            priorities_slide = _clone_slide(prs, IDX_PRIORITIES)
            _strip_guidance_shapes(priorities_slide)
            _set_or_remove_facility_placeholder(priorities_slide, plan.facility_name)

            priority_title = _shape_by_name(priorities_slide, "Title 2")
            if priority_title is not None and priority_title.text_frame.paragraphs:
                p0 = priority_title.text_frame.paragraphs[0]
                clean_title = (
                    f"{plan.facility_name.upper()} PRIORITIES"
                    if plan.facility_name
                    else "CUSTOMER PRIORITIES"
                )
                p0.text = clean_title
                if p0.runs:
                    p0.runs[0].font.size = Pt(22)
                    p0.runs[0].font.bold = True

            # Dynamic column layout and widths based on priority count
            n_p = len(plan.priorities)
            SLIDE_WIDTH = 12192000  # 13.333 inches

            if n_p == 2:
                CARD_WIDTH_EMU = int(4.00 * 914400)
                CIRCLE_CENTERS = [int(SLIDE_WIDTH * 0.30), int(SLIDE_WIDTH * 0.70)]
            elif n_p == 1:
                CARD_WIDTH_EMU = int(5.50 * 914400)
                CIRCLE_CENTERS = [int(SLIDE_WIDTH * 0.50)]
            else:
                CARD_WIDTH_EMU = int(3.25 * 914400)
                CIRCLE_CENTERS = [2031252, 5987374, 10056673]

            # Dynamic line estimation for headings
            p_width_in = (CARD_WIDTH_EMU - int(0.20 * 914400)) / 914400
            chars_per_line = int(p_width_in * 9.5)
            max_head_lines = max(
                max(1, math.ceil(len(p.heading.strip()) / chars_per_line))
                for p in plan.priorities
            ) if plan.priorities else 1

            if max_head_lines >= 3:
                target_body_top = 4450000
            elif max_head_lines == 2:
                target_body_top = 4220000
            else:
                target_body_top = 3939696

            priority_groups = sorted(
                (s for s in priorities_slide.shapes if s.shape_type == 6),
                key=lambda s: s.left,
            )
            for col_idx, (group, item) in enumerate(zip(priority_groups, plan.priorities)):
                center_x = (
                    CIRCLE_CENTERS[col_idx]
                    if col_idx < len(CIRCLE_CENTERS)
                    else group.left + (group.width // 2)
                )
                _fill_priority_group(
                    group,
                    item.heading,
                    item.body,
                    center_x=center_x,
                    card_width=CARD_WIDTH_EMU,
                    target_body_top=target_body_top,
                )
            for group in priority_groups[len(plan.priorities):]:
                priorities_slide.shapes._spTree.remove(group._element)

        # 6. Section divider: Performance Management (only if any perf content exists)
        has_perf_section = bool(
            plan.action_tracker
            or plan.kpi_safety_quality
            or plan.kpi_operational
            or (plan.operational_chart and plan.operational_chart.categories and plan.operational_chart.series)
        )
        if has_perf_section:
            perf_divider = _clone_slide(prs, IDX_SECTION_PERF_MGMT)
            t = _shape_by_name(perf_divider, "Title 6")
            if t is not None:
                _set_first_run_text(t, "PERFORMANCE MANAGEMENT UPDATES")

        # 7. Action Item Tracker (optional)
        if plan.action_tracker:
            tracker = _clone_slide(prs, IDX_TRACKER)
            _strip_guidance_shapes(tracker)
            _strip_decorative_connectors(tracker)
            _set_or_remove_facility_placeholder(tracker, plan.facility_name)
            table_shape = _shape_by_name(tracker, "Table 4")
            if table_shape is not None and table_shape.has_table:
                rows = [[r.project, r.owner, r.next_step, r.comment, r.status] for r in plan.action_tracker]
                _fill_table_rows(table_shape.table, rows, start_row=1)

        # 8. Operational Chart (optional native clustered column chart + observations side panel)
        if plan.operational_chart and plan.operational_chart.categories and plan.operational_chart.series:
            chart_slide = _clone_slide(prs, IDX_OPERATIONAL_CHART)
            _strip_guidance_shapes(chart_slide)
            _strip_decorative_connectors(chart_slide)
            _set_or_remove_facility_placeholder(chart_slide, plan.facility_name)

            t = _shape_by_name(chart_slide, "Title 2")
            if t is not None:
                title_text = plan.operational_chart.chart_title or "OPERATIONAL PERFORMANCE SNAPSHOT"
                _set_first_run_text(t, title_text.upper())

            chart_shape = next((s for s in chart_slide.shapes if s.has_chart), None)
            if chart_shape is not None:
                c = chart_shape.chart
                cd = CategoryChartData()
                cd.categories = plan.operational_chart.categories
                for ser in plan.operational_chart.series:
                    cd.add_series(ser.name, ser.values)
                c.replace_data(cd)

                # Remove template's stale floating chart title ("Receipts")
                c.has_title = False

                if len(plan.operational_chart.series) > 1:
                    c.has_legend = True
                    c.legend.position = XL_LEGEND_POSITION.TOP
                    c.legend.include_in_layout = False
                    try:
                        c.legend.font.name = "Verdana"
                        c.legend.font.size = Pt(10)
                    except Exception:
                        pass

                try:
                    c.category_axis.tick_labels.font.name = "Verdana"
                    c.category_axis.tick_labels.font.size = Pt(9)
                    c.value_axis.tick_labels.font.name = "Verdana"
                    c.value_axis.tick_labels.font.size = Pt(9)
                except Exception:
                    pass

                try:
                    if c.plots:
                        c.plots[0].has_data_labels = True
                        c.plots[0].data_labels.font.name = "Verdana"
                        c.plots[0].data_labels.font.size = Pt(8)
                except Exception:
                    pass

            group11 = _shape_by_name(chart_slide, "Group 11")
            if group11 is not None:
                if plan.operational_chart.insights:
                    # Dynamic Content-Driven Layout Partitioning
                    insights = plan.operational_chart.insights
                    n_items = len(insights)
                    total_chars = sum(len(t) for t in insights)
                    avg_chars = total_chars / max(1, n_items)
                    max_chars = max(len(t) for t in insights) if insights else 0

                    TOTAL_CONTENT_WIDTH = Inches(12.533)
                    CONTENT_LEFT = Inches(0.40)
                    GAP = Inches(0.25)

                    # 1. Dynamic Card Width Allocation based on content volume
                    if max_chars > 85 or total_chars > 380 or (n_items >= 6 and avg_chars > 55):
                        CARD_WIDTH = int(Inches(3.85))
                    elif max_chars > 50 or total_chars > 200 or n_items >= 4:
                        CARD_WIDTH = int(Inches(3.48))
                    else:
                        CARD_WIDTH = int(Inches(3.00))

                    CHART_WIDTH = int(TOTAL_CONTENT_WIDTH - CARD_WIDTH - GAP)
                    CHART_LEFT = int(CONTENT_LEFT)
                    CARD_LEFT = int(CHART_LEFT + CHART_WIDTH + GAP)

                    CARD_TOP = int(Inches(1.45))
                    CARD_HEIGHT = int(Inches(5.25))

                    # 2. Dynamically reposition chart based on allocated width
                    if chart_shape is not None:
                        chart_shape.left = CHART_LEFT
                        chart_shape.top = int(Inches(1.40))
                        chart_shape.width = CHART_WIDTH
                        chart_shape.height = int(Inches(5.30))

                    # 3. Extract shapes from Group 11 to slide tree so they can be resized without group distortion
                    spTree = chart_slide.shapes._spTree
                    for sp in list(group11._element.xpath("p:sp")):
                        spTree.append(sp)
                    group11.element.getparent().remove(group11.element)

                    blue_card = next((sh for sh in chart_slide.shapes if "7" in sh.name and sh.shape_type == 1), None)
                    badge = next((sh for sh in chart_slide.shapes if "10" in sh.name and sh.shape_type == 1), None)

                    # 4. Dynamic Header Badge Sizing based on header text
                    insights_title = (getattr(plan.operational_chart, "insights_title", None) or "KEY OBSERVATIONS").strip().upper()
                    raw_badge_width = int(Inches(len(insights_title) * 0.125 + 0.40))
                    BADGE_WIDTH = int(min(max(raw_badge_width, Inches(2.20)), CARD_WIDTH - Inches(0.35)))
                    BADGE_HEIGHT = int(Inches(0.48))
                    BADGE_LEFT = int(CARD_LEFT + (CARD_WIDTH - BADGE_WIDTH) // 2)
                    BADGE_TOP = int(CARD_TOP - Inches(0.24))

                    if badge is not None:
                        badge.width = BADGE_WIDTH
                        badge.height = BADGE_HEIGHT
                        badge.left = BADGE_LEFT
                        badge.top = BADGE_TOP
                        tf_b = badge.text_frame
                        tf_b.margin_left = Inches(0.05)
                        tf_b.margin_right = Inches(0.05)
                        tf_b.margin_top = Inches(0.05)
                        tf_b.margin_bottom = Inches(0.05)
                        tf_b.word_wrap = False
                        p_b = tf_b.paragraphs[0]
                        if len(insights_title) > 28:
                            badge_font_sz = Pt(9.5)
                        elif len(insights_title) > 20:
                            badge_font_sz = Pt(10.5)
                        else:
                            badge_font_sz = Pt(12)
                        for r in p_b.runs:
                            r.font.name = "Verdana"
                            r.font.size = badge_font_sz
                            r.font.bold = True
                            r.font.color.rgb = RGBColor(255, 190, 0)

                    # 5. Dynamic Typography & Spacing for Observations Card
                    if blue_card is not None:
                        blue_card.left = CARD_LEFT
                        blue_card.top = CARD_TOP
                        blue_card.width = CARD_WIDTH
                        blue_card.height = CARD_HEIGHT
                        tf = blue_card.text_frame
                        tf.margin_left = Inches(0.18)
                        tf.margin_right = Inches(0.18)
                        tf.margin_top = Inches(0.45) # Clearance below badge
                        tf.word_wrap = True

                        sample_pPr = None
                        if len(tf.paragraphs) > 1 and tf.paragraphs[1]._p.pPr is not None:
                            sample_pPr = copy.deepcopy(tf.paragraphs[1]._p.pPr)
                        tf.clear()

                        # Dynamic font sizing based on estimated lines
                        printable_width_in = (CARD_WIDTH - Inches(0.36)) / Inches(1)
                        chars_per_line = int(printable_width_in * 14.5)
                        estimated_lines = sum(max(1, math.ceil(len(item) / chars_per_line)) for item in insights)

                        if estimated_lines <= 6 and n_items <= 3:
                            font_sz = Pt(11.5)
                        elif estimated_lines <= 9 and n_items <= 5:
                            font_sz = Pt(10.5)
                        elif estimated_lines <= 13:
                            font_sz = Pt(9.5)
                        else:
                            font_sz = Pt(8.5)

                        for i, item in enumerate(insights):
                            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                            p.text = item
                            p.font.name = "Verdana"
                            p.font.size = font_sz
                            for r in p.runs:
                                r.font.name = "Verdana"
                                r.font.size = font_sz
                                r.font.color.rgb = RGBColor(255, 255, 255)
                            if sample_pPr is not None:
                                if p._p.pPr is not None:
                                    p._p.remove(p._p.pPr)
                                p._p.insert(0, copy.deepcopy(sample_pPr))
                else:
                    group11.element.getparent().remove(group11.element)
                    if chart_shape is not None:
                        chart_shape.left = Inches(0.40)
                        chart_shape.width = Inches(12.50)

        # 9. KPI Dashboard (optional, 2 tables)
        if plan.kpi_safety_quality or plan.kpi_operational:
            kpi_slide = _clone_slide(prs, IDX_KPI_DASHBOARD)
            _set_or_remove_facility_placeholder(kpi_slide, plan.facility_name)
            kpi_tables = [s for s in kpi_slide.shapes if s.has_table]
            table_by_cols: Dict[int, Any] = {len(s.table.columns): s.table for s in kpi_tables}
            if 7 in table_by_cols:
                sq_tbl = table_by_cols[7]
                for i, row in enumerate(plan.kpi_safety_quality):
                    r = 2 + i
                    if r < len(sq_tbl.rows):
                        sq_tbl.cell(r, 0).text = row.label
                        for c in (1, 4):
                            sq_tbl.cell(r, c).text = row.actual
                        for c in (2, 5):
                            sq_tbl.cell(r, c).text = row.target
                        for c in (3, 6):
                            sq_tbl.cell(r, c).text = row.actual
                # Blank leftover template sample rows beyond the supplied data
                for r in range(2 + len(plan.kpi_safety_quality), len(sq_tbl.rows)):
                    for c in range(len(sq_tbl.columns)):
                        sq_tbl.cell(r, c).text = ""
            if 3 in table_by_cols and plan.kpi_operational:
                op_tbl = table_by_cols[3]
                op_tbl.cell(0, 0).text = "Operational Metric"
                op_tbl.cell(0, 1).text = "Actual"
                op_tbl.cell(0, 2).text = "Target"
                rows = [[r.label, r.actual, r.target] for r in plan.kpi_operational]
                _fill_table_rows(op_tbl, rows, start_row=1)

        # 9. Voice of the Customer (optional)
        if plan.voice_of_customer and plan.voice_of_customer.quote:
            voc_slide = _clone_slide(prs, IDX_VOICE_OF_CUSTOMER)
            _remove_shapes(voc_slide, lambda s: s.name == "TextBox 5")  # stale guidance placeholder
            bubble = _shape_by_name(voc_slide, "Speech Bubble: Rectangle with Corners Rounded 4")
            if bubble is not None:
                paras = bubble.text_frame.paragraphs
                if paras and paras[0].runs:
                    paras[0].runs[0].text = plan.voice_of_customer.quote
                if len(paras) > 2 and paras[2].runs:
                    paras[2].runs[0].text = plan.voice_of_customer.attribution

        # 10. Section divider: Continuous Improvement (only if any CI content exists)
        has_ci_section = bool(plan.gemba_walk or plan.ci_tracker)
        if has_ci_section:
            ci_divider = _clone_slide(prs, IDX_SECTION_CIP)
            t2 = _shape_by_name(ci_divider, "Title 6")
            if t2 is not None:
                _set_first_run_text(t2, "CONTINUOUS IMPROVEMENT PROGRAM UPDATES")

        # 11. Gemba Walk Summary (optional)
        if plan.gemba_walk:
            gemba_slide = _clone_slide(prs, IDX_GEMBA_WALK)
            _strip_guidance_shapes(gemba_slide)
            gemba_intro = _shape_by_name(gemba_slide, "TextBox 6")
            if gemba_intro is not None and plan.gemba_walk_intro:
                _set_first_run_text(gemba_intro, plan.gemba_walk_intro)
            gemba_table_shape = _shape_by_name(gemba_slide, "Table 5")
            if gemba_table_shape is not None and gemba_table_shape.has_table:
                rows = [[r.area, r.observation] for r in plan.gemba_walk]
                _fill_table_rows(gemba_table_shape.table, rows, start_row=1)

        # 12. CI Activity Tracker (optional)
        if plan.ci_tracker:
            ci_tracker_slide = _clone_slide(prs, IDX_CI_TRACKER)
            _strip_guidance_shapes(ci_tracker_slide)
            _strip_decorative_connectors(ci_tracker_slide)
            ci_table_shape = _shape_by_name(ci_tracker_slide, "Table 4")
            if ci_table_shape is not None and ci_table_shape.has_table:
                rows = [[r.activity, r.category, r.status, r.value, r.comment] for r in plan.ci_tracker]
                _fill_table_rows(ci_table_shape.table, rows, start_row=1)

        # 13. Section divider: Quality Management (only if any quality content exists)
        has_quality_section = bool(
            plan.quality_org_structure or plan.nc_review_narrative or plan.nc_tracker
        )
        if has_quality_section:
            quality_divider = _clone_slide(prs, IDX_SECTION_QUALITY)
            t3 = _shape_by_name(quality_divider, "Title 6")
            if t3 is not None:
                _set_first_run_text(t3, "QUALITY MANAGEMENT SYSTEM UPDATES")

        # 14. Quality Organizational Structure (optional)
        if plan.quality_org_structure:
            quality_org_slide = _clone_slide(prs, IDX_QUALITY_ORG)
            _strip_guidance_shapes(quality_org_slide)
            quality_title = _shape_by_name(quality_org_slide, "Title 1")
            if quality_title is not None:
                title_runs = quality_title.text_frame.paragraphs[0].runs
                if len(title_runs) > 1:
                    title_runs[1].text = plan.presentation_title
            quality_boxes = sorted(
                (s for s in quality_org_slide.shapes if s.name.startswith("Rectangle: Rounded Corners")),
                key=lambda s: (s.top, s.left),
            )
            for box, person in zip(quality_boxes, plan.quality_org_structure):
                _set_org_box(box, person.name, f"{person.role}\nUPS Healthcare")
            # Blank leftover template sample cards beyond the supplied people
            for box in quality_boxes[len(plan.quality_org_structure):]:
                _set_org_box(box, "", "")

        # 15. Non-Conformance Review (optional)
        if plan.nc_review_narrative or plan.nc_review_summary:
            nc_review_slide = _clone_slide(prs, IDX_NC_REVIEW)
            _strip_guidance_shapes(nc_review_slide)
            _set_or_remove_facility_placeholder(nc_review_slide, plan.facility_name)
            nc_narrative = _shape_by_name(nc_review_slide, "TextBox 7")
            if nc_narrative is not None and plan.nc_review_narrative:
                nc_narrative.text_frame.text = plan.nc_review_narrative
            nc_summary_table = _shape_by_name(nc_review_slide, "Table 5")
            if nc_summary_table is not None and nc_summary_table.has_table and plan.nc_review_summary:
                tbl = nc_summary_table.table
                for c_idx, val in enumerate(plan.nc_review_summary[: len(tbl.columns)]):
                    tbl.cell(1, c_idx).text = val

        # 16. Non-Conformance Tracker (optional)
        if plan.nc_tracker:
            nc_tracker_slide = _clone_slide(prs, IDX_NC_TRACKER)
            _strip_guidance_shapes(nc_tracker_slide)
            _strip_decorative_connectors(nc_tracker_slide)
            nc_tracker_table = _shape_by_name(nc_tracker_slide, "Table 4")
            if nc_tracker_table is not None and nc_tracker_table.has_table:
                rows = [[r.period, r.nc_id, r.event, r.due_date, r.status] for r in plan.nc_tracker]
                _fill_table_rows(nc_tracker_table.table, rows, start_row=1)

        # 17. Next Steps (optional)
        if plan.next_steps:
            next_steps_slide = _clone_slide(prs, IDX_NEXT_STEPS)
            ns_table_shape = _shape_by_name(next_steps_slide, "Table 8")
            if ns_table_shape is not None and ns_table_shape.has_table:
                rows = [[s.step, s.date] for s in plan.next_steps]
                _fill_table_rows(ns_table_shape.table, rows, start_row=0)

        # 18. Mandatory Closing (always, intact)
        _clone_slide(prs, IDX_CLOSING)

        # Prune the original 60 source slides, leaving only the generated ones
        rId_attr = qn("r:id")
        sldIdLst = prs.slides._sldIdLst
        for _ in range(initial_count):
            sldId = sldIdLst[0]
            rId = sldId.get(rId_attr)
            if rId:
                prs.part.drop_rel(rId)
            sldIdLst.remove(sldId)

        logger.info("[HLD QBR Builder] Built %d slides.", len(prs.slides))

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        return buf.read()
