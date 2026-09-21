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
import re
from typing import Any, Dict, List, Optional

from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Pt

import config
from llm.hld_qbr_schemas import HLDQBRPresentationPlan
from utils.logging_utils import get_logger

logger = get_logger(__name__)

IDX_COVER = 0
IDX_AGENDA = 1
IDX_ORG_STRUCTURE = 2
IDX_ACHIEVEMENTS = 4
IDX_PRIORITIES = 5
IDX_SECTION_PERF_MGMT = 11
IDX_TRACKER = 9
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
    for rId, rel in source_slide.part.rels.items():
        if (
            "slideLayout" not in rel.target_ref
            and "notesSlide" not in rel.target_ref
            and "notesMaster" not in rel.target_ref
        ):
            try:
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


def _fill_priority_group(group_shape: Any, heading: str, body: str) -> None:
    for sub in group_shape.shapes:
        if not getattr(sub, "has_text_frame", False):
            continue
        current = sub.text_frame.text.strip()
        if current.upper().startswith("PRIORITY"):
            _set_first_run_text(sub, heading)
        elif current == "Supporting text here":
            _set_first_run_text(sub, body)


def _fill_table_rows(tbl: Any, rows: List[List[str]], start_row: int = 1) -> None:
    for r_offset, row_values in enumerate(rows):
        r_idx = start_row + r_offset
        if r_idx >= len(tbl.rows):
            break
        for c_idx, val in enumerate(row_values):
            if c_idx < len(tbl.columns):
                tbl.cell(r_idx, c_idx).text = val
    used_through = start_row + len(rows)
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
                paras = agenda_box.text_frame.paragraphs
                for i, para in enumerate(paras):
                    if para.runs:
                        para.runs[0].text = plan.agenda_topics[i] if i < len(plan.agenda_topics) else ""

        # 3. Organizational Structure (optional)
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
            milestone_boxes = sorted(
                (s for s in achievements_slide.shapes if s.name == "Content Placeholder 42"),
                key=lambda s: s.top,
            )
            for box, text in zip(milestone_boxes, plan.achievements):
                _set_first_run_text(box, text)
            # Blank leftover template sample milestones beyond the supplied achievements
            for box in milestone_boxes[len(plan.achievements):]:
                _set_first_run_text(box, "")

        # 5. Customer Priorities (optional)
        if plan.priorities:
            priorities_slide = _clone_slide(prs, IDX_PRIORITIES)
            _strip_guidance_shapes(priorities_slide)
            priority_title = _shape_by_name(priorities_slide, "Title 2")
            if priority_title is not None and priority_title.text_frame.paragraphs[0].runs:
                priority_title.text_frame.paragraphs[0].runs[0].text = plan.presentation_title
            priority_groups = sorted(
                (s for s in priorities_slide.shapes if s.shape_type == 6),
                key=lambda s: s.left,
            )
            for group, item in zip(priority_groups, plan.priorities):
                _fill_priority_group(group, item.heading, item.body)

        # 6. Section divider: Performance Management (only if any perf content exists)
        has_perf_section = bool(plan.action_tracker or plan.kpi_safety_quality or plan.kpi_operational)
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
            facility_ph = _shape_by_name(tracker, "Text Placeholder 3")
            if facility_ph is not None and plan.facility_name:
                _set_first_run_text(facility_ph, plan.facility_name)
            table_shape = _shape_by_name(tracker, "Table 4")
            if table_shape is not None and table_shape.has_table:
                rows = [[r.project, r.owner, r.next_step, r.comment, r.status] for r in plan.action_tracker]
                _fill_table_rows(table_shape.table, rows, start_row=1)

        # 8. KPI Dashboard (optional, 2 tables)
        if plan.kpi_safety_quality or plan.kpi_operational:
            kpi_slide = _clone_slide(prs, IDX_KPI_DASHBOARD)
            kpi_facility_ph = _shape_by_name(kpi_slide, "Text Placeholder 3")
            if kpi_facility_ph is not None and plan.facility_name:
                _set_first_run_text(kpi_facility_ph, plan.facility_name)
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
            nc_facility_ph = _shape_by_name(nc_review_slide, "Text Placeholder 3")
            if nc_facility_ph is not None and plan.facility_name:
                _set_first_run_text(nc_facility_ph, plan.facility_name)
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
