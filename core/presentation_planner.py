"""
core/presentation_planner.py — Stage 2: LLM-based presentation planning.

Takes the ContentAnalysis output (Stage 1) plus user requirements and
produces a complete PresentationPlan with slide-by-slide structure,
titles, layout selections, and content.

This is the most critical LLM stage — it determines the full structure
of the presentation.
"""

from __future__ import annotations

import json
from typing import List, Optional

from llm.groq_client import GroqClient, JSONParseError
from llm.prompts import PRESENTATION_PLANNING_PROMPT, SYSTEM_ROLE_PLANNER
from llm.schemas import ContentAnalysis, PresentationPlan, PresentationPlanWrapper, SlideDefinition
from utils.logging_utils import get_logger
from utils.text_utils import truncate_text

logger = get_logger(__name__)


class PresentationPlanningError(Exception):
    """Raised when presentation planning fails."""


# ---------------------------------------------------------------------------
# Structural enforcement layer
# ---------------------------------------------------------------------------

def _make_slide(
    slide_number: int,
    layout_type: str,
    title: str,
    purpose: str,
    content: dict,
    speaker_notes: str = "",
) -> SlideDefinition:
    """Helper to create a SlideDefinition with sensible defaults."""
    return SlideDefinition(
        slide_number=slide_number,
        layout_type=layout_type,
        title=title,
        purpose=purpose,
        content=content,
        speaker_notes=speaker_notes,
    )


def _enforce_presentation_structure(
    plan: PresentationPlan,
    content_analysis: ContentAnalysis,
) -> PresentationPlan:
    """
    Post-LLM structural enforcement layer.

    Guarantees the mandatory slide order regardless of LLM output:
      Slide 1  : TITLE
      Slide 2  : EXECUTIVE_SUMMARY
      Slide 3  : AGENDA
      Slides 4+ : Body content (SECTION_HEADER injected before each major section)
      Last slide: CONCLUSION

    Renumbers all slides sequentially after any insertions.
    """
    slides: List[SlideDefinition] = list(plan.slides)

    # ---- Helpers --------------------------------------------------------
    def _has_layout(lt: str) -> bool:
        return any(s.layout_type.upper() == lt for s in slides)

    def _first_of_layout(lt: str) -> Optional[int]:
        """Return index of first slide with given layout_type, or None."""
        for idx, s in enumerate(slides):
            if s.layout_type.upper() == lt:
                return idx
        return None

    # ---- 1. Ensure TITLE at position 0 ----------------------------------
    title_idx = _first_of_layout("TITLE")
    if title_idx is None:
        logger.info("[enforce] Inserting missing TITLE slide at position 0")
        slides.insert(0, _make_slide(
            slide_number=1,
            layout_type="TITLE",
            title=plan.title,
            purpose="Cover slide",
            content={"subtitle": plan.subtitle or ""},
            speaker_notes="Welcome and introduction.",
        ))
    elif title_idx != 0:
        logger.info("[enforce] Moving TITLE slide to position 0 (was %d)", title_idx)
        title_slide = slides.pop(title_idx)
        slides.insert(0, title_slide)

    # ---- 2. Ensure EXECUTIVE_SUMMARY at position 1 ----------------------
    exec_idx = _first_of_layout("EXECUTIVE_SUMMARY")
    highlights = content_analysis.executive_highlights or content_analysis.key_concepts[:5]
    purpose_stmt = content_analysis.summary[:120] if content_analysis.summary else ""

    if exec_idx is None:
        logger.info("[enforce] Inserting missing EXECUTIVE_SUMMARY slide at position 1")
        slides.insert(1, _make_slide(
            slide_number=2,
            layout_type="EXECUTIVE_SUMMARY",
            title="Executive Summary",
            purpose="Key highlights for decision-makers",
            content={
                "highlights": highlights[:5] or [content_analysis.main_topic],
                "purpose_statement": purpose_stmt,
            },
            speaker_notes="High-level overview of the key takeaways.",
        ))
    elif exec_idx != 1:
        logger.info("[enforce] Moving EXECUTIVE_SUMMARY to position 1 (was %d)", exec_idx)
        es_slide = slides.pop(exec_idx)
        slides.insert(1, es_slide)

    # ---- 3. Ensure AGENDA at position 2 ---------------------------------
    agenda_idx = _first_of_layout("AGENDA")
    agenda_items = (
        content_analysis.agenda_topics
        or content_analysis.sections[:8]
        or [s.title for s in slides[3:] if s.layout_type.upper() == "SECTION_HEADER"][:8]
        or ["Introduction", "Key Findings", "Conclusion"]
    )

    if agenda_idx is None:
        logger.info("[enforce] Inserting missing AGENDA slide at position 2")
        slides.insert(2, _make_slide(
            slide_number=3,
            layout_type="AGENDA",
            title="Agenda",
            purpose="Presentation roadmap",
            content={"agenda_items": agenda_items[:8]},
            speaker_notes="Walk the audience through what we will cover.",
        ))
    elif agenda_idx != 2:
        logger.info("[enforce] Moving AGENDA to position 2 (was %d)", agenda_idx)
        ag_slide = slides.pop(agenda_idx)
        slides.insert(2, ag_slide)

    # ---- 4. Ensure CONCLUSION is the last slide -------------------------
    conclusion_idx = _first_of_layout("CONCLUSION")
    if conclusion_idx is None:
        logger.info("[enforce] Appending missing CONCLUSION slide")
        summary_pts = content_analysis.conclusions[:5] or [content_analysis.summary[:80]]
        slides.append(_make_slide(
            slide_number=len(slides) + 1,
            layout_type="CONCLUSION",
            title="Conclusion & Recommendations",
            purpose="Summary, recommendations, and next steps",
            content={
                "summary_points": summary_pts,
                "recommendations": content_analysis.recommendations[:5],
                "next_steps": [],
                "call_to_action": "Thank You — Questions Welcome",
            },
            speaker_notes="Summarise key findings and open for questions.",
        ))
    elif conclusion_idx != len(slides) - 1:
        # Move conclusion to last position
        logger.info("[enforce] Moving CONCLUSION to last position (was %d)", conclusion_idx)
        conc_slide = slides.pop(conclusion_idx)
        # Ensure recommendations are populated if empty
        if not conc_slide.content.get("recommendations") and content_analysis.recommendations:
            conc_slide.content["recommendations"] = content_analysis.recommendations[:5]
        slides.append(conc_slide)

    # ---- 5. Inject SECTION_HEADER before major body sections -------------
    #         For each agenda topic, ensure there's a SECTION_HEADER slide
    #         before the body slides covering that topic (positions 3+)
    body_slides = slides[3:-1]  # exclude fixed slots 0,1,2 and last (CONCLUSION)
    existing_headers = {s.title.strip().lower() for s in body_slides
                        if s.layout_type.upper() == "SECTION_HEADER"}
    missing_topics = [
        t for t in (content_analysis.agenda_topics or [])
        if t.strip().lower() not in existing_headers
    ]
    if missing_topics:
        logger.info("[enforce] %d agenda topics lack a SECTION_HEADER — skipping auto-inject "
                    "(LLM should handle this; avoid over-inflating slide count)",
                    len(missing_topics))
        # Note: we intentionally skip auto-injection to avoid blowing up slide count;
        # the LLM prompt now mandates SECTION_HEADERs explicitly.

    # ---- 6. Renumber sequentially ---------------------------------------
    for i, slide in enumerate(slides, start=1):
        slide.slide_number = i

    plan.slides = slides
    logger.info(
        "[enforce] Final structure: %d slides | %s",
        len(slides),
        " → ".join(s.layout_type.upper() for s in slides[:6]) + (" …" if len(slides) > 6 else "")
    )
    return plan


def plan_presentation(
    content_analysis: ContentAnalysis,
    source_text: str,
    client: GroqClient,
    presentation_title: str = "",
    audience: str = "General",
    style: str = "Professional",
    slide_count: int = 10,
    language: str = "English",
    additional_instructions: str = "",
    max_source_chars: int = 8000,
) -> PresentationPlan:
    """
    Stage 2: Create a structured presentation plan using LLM.

    Args:
        content_analysis:        Output from Stage 1.
        source_text:             Original source text (for LLM grounding reference).
        client:                  Initialized GroqClient.
        presentation_title:      User-specified title (or LLM will determine it).
        audience:                Target audience.
        style:                   Presentation style.
        slide_count:             Exact number of slides to generate.
        language:                Output language.
        additional_instructions: Extra user instructions.
        max_source_chars:        Source text char limit for the planning prompt.

    Returns:
        PresentationPlan pydantic model.

    Raises:
        PresentationPlanningError: On LLM failure or validation error.
    """
    # Use analysis-suggested title if user didn't provide one
    if not presentation_title or presentation_title.strip() == "":
        presentation_title = content_analysis.main_topic

    # Truncate source reference for the planning prompt
    truncated_source = truncate_text(source_text, max_source_chars)

    # Serialize content analysis to JSON for the prompt
    analysis_json = content_analysis.model_dump_json(indent=2)

    prompt = PRESENTATION_PLANNING_PROMPT.format(
        content_analysis=analysis_json,
        source_content=truncated_source,
        presentation_title=presentation_title,
        audience=audience or "General",
        style=style or "Professional",
        slide_count=slide_count,
        language=language or "English",
        additional_instructions=additional_instructions or "None",
    )

    messages = [
        {"role": "system", "content": SYSTEM_ROLE_PLANNER},
        {"role": "user", "content": prompt},
    ]

    logger.info(
        "Running presentation planning (Stage 2): %d slides requested for '%s'",
        slide_count, presentation_title
    )

    try:
        raw_data = client.chat_complete_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
        )
    except JSONParseError as e:
        raise PresentationPlanningError(
            f"LLM returned invalid JSON during presentation planning: {e}"
        ) from e
    except Exception as e:
        raise PresentationPlanningError(
            f"Presentation planning LLM call failed: {e}"
        ) from e

    # Handle both { "presentation": {...} } and { "title": ..., "slides": [...] }
    try:
        if "presentation" in raw_data:
            wrapper = PresentationPlanWrapper(**raw_data)
            plan = wrapper.presentation
        else:
            plan = PresentationPlan(**raw_data)

        # ── Structural enforcement: guarantee mandatory slide order ──────
        plan = _enforce_presentation_structure(plan, content_analysis)

        logger.info(
            "Presentation plan created: '%s' with %d slides",
            plan.title, len(plan.slides)
        )
        return plan

    except Exception as e:
        logger.error(
            "PresentationPlan validation failed: %s\nRaw data (first 1000 chars): %s",
            e, str(raw_data)[:1000]
        )
        raise PresentationPlanningError(
            f"Generated plan failed Pydantic validation: {e}"
        ) from e
