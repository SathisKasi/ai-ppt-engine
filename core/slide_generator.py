"""
core/slide_generator.py — Stage 3: Per-slide content refinement (optional).

This stage refines the LLM-generated content for each slide to make it
more concise and presentation-friendly. It uses the source text as ground
truth to prevent hallucination.

This stage is applied selectively — only for slides where the initial
content needs refinement (e.g., very long bullets, paragraph text in
bullet slots, etc.).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from llm.groq_client import GroqClient
from llm.prompts import SLIDE_CONTENT_REFINEMENT_PROMPT, SYSTEM_ROLE_CONTENT
from llm.schemas import PresentationPlan, SlideDefinition
from utils.logging_utils import get_logger
from utils.text_utils import truncate_text

logger = get_logger(__name__)

# Maximum bullet length (words) before refinement is triggered
MAX_BULLET_WORDS = 15

# Maximum bullets before we suggest trimming
MAX_BULLETS = 8


def _needs_refinement(slide: SlideDefinition) -> bool:
    """
    Heuristic check: does this slide's content need LLM refinement?
    """
    content = slide.content or {}

    # Check bullets for length
    bullets = content.get("bullets", [])
    if bullets:
        for bullet in bullets:
            if len(str(bullet).split()) > MAX_BULLET_WORDS:
                return True
        if len(bullets) > MAX_BULLETS:
            return True

    # Check if content is just a raw paragraph (not structured)
    body = content.get("body_text", "")
    if body and len(body.split()) > 50:
        return True

    return False


def _extract_bullets_from_text(text: str, max_bullets: int = 6) -> List[str]:
    """
    Convert a paragraph of text into bullet points.
    Simple sentence splitting as fallback.
    """
    import re
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    bullets: List[str] = []
    for sent in sentences[:max_bullets]:
        sent = sent.strip().rstrip(".")
        if sent and len(sent) > 5:
            bullets.append(sent)
    return bullets or [text[:100]]


def refine_slide_content(
    slide: SlideDefinition,
    source_text: str,
    client: GroqClient,
    audience: str = "General",
    style: str = "Professional",
    language: str = "English",
) -> SlideDefinition:
    """
    Refine content for a single slide using LLM.

    Returns the slide with updated content if refinement succeeds,
    or the original slide if refinement fails (graceful degradation).
    """
    source_excerpt = truncate_text(source_text, 3000)

    prompt = SLIDE_CONTENT_REFINEMENT_PROMPT.format(
        slide_title=slide.title,
        layout_type=slide.layout_type,
        purpose=slide.purpose,
        current_content=json.dumps(slide.content, indent=2),
        source_excerpt=source_excerpt,
        audience=audience,
        style=style,
        language=language,
    )

    messages = [
        {"role": "system", "content": SYSTEM_ROLE_CONTENT},
        {"role": "user", "content": prompt},
    ]

    try:
        refined_content = client.chat_complete_json(
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
        )
        slide.content = refined_content
        logger.debug("Refined content for slide %d: %s", slide.slide_number, slide.title)
        return slide
    except Exception as e:
        logger.warning(
            "Content refinement failed for slide %d ('%s'): %s — keeping original",
            slide.slide_number, slide.title, e
        )
        return slide


def refine_presentation_content(
    plan: PresentationPlan,
    source_text: str,
    client: GroqClient,
    audience: str = "General",
    style: str = "Professional",
    language: str = "English",
    refine_all: bool = False,
) -> PresentationPlan:
    """
    Optionally refine content for slides that need it.

    Args:
        plan:       The presentation plan from Stage 2.
        source_text: Original source text.
        client:     GroqClient instance.
        refine_all: If True, refine ALL slides (slower but more polished).
                    If False, only refine slides that fail quality heuristics.

    Returns:
        Updated PresentationPlan with refined slide content.
    """
    slides_to_refine = []

    for slide in plan.slides:
        # Skip title slide — content is usually fine
        if slide.layout_type.upper() == "TITLE":
            continue
        if refine_all or _needs_refinement(slide):
            slides_to_refine.append(slide)

    if not slides_to_refine:
        logger.info("No slides require content refinement.")
        return plan

    logger.info("Refining content for %d slides...", len(slides_to_refine))

    for slide in slides_to_refine:
        refine_slide_content(
            slide=slide,
            source_text=source_text,
            client=client,
            audience=audience,
            style=style,
            language=language,
        )

    return plan
