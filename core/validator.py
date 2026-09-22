"""
core/validator.py — Quality validation for presentation plans and generated .pptx files.

Validates:
- Slide count vs requested
- All slides have titles
- Selected layouts exist in registry
- No unfilled placeholder text
- Basic file integrity
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from llm.schemas import PresentationPlan, ValidationResult
from utils.logging_utils import get_logger

if TYPE_CHECKING:
    from core.layout_manager import LayoutManager

logger = get_logger(__name__)

# Text patterns that indicate unfilled placeholders
UNFILLED_PATTERNS = [
    "click to add",
    "click to edit",
    "add text here",
    "enter text",
    "[placeholder]",
    "lorem ipsum",
    "sample text",
    "your text here",
    "{{",
    "}}",
]


def validate_plan(
    plan: PresentationPlan,
    layout_manager: "LayoutManager",
    requested_slides: Optional[int] = None,
) -> ValidationResult:
    """
    Validate a PresentationPlan for quality and completeness.

    Args:
        plan:             The presentation plan to validate.
        layout_manager:   Layout manager for checking layout existence.
        requested_slides: Expected number of slides (None = auto, skip count check).

    Returns:
        ValidationResult with any errors and warnings.
    """
    result = ValidationResult()

    # 1. Slide count
    actual_count = len(plan.slides)

    if actual_count == 0:
        result.add_error("Presentation plan has no slides.")
        return result  # No point continuing

    if requested_slides is not None:
        expected_total = requested_slides + 4
        if actual_count < requested_slides:
            result.add_warning(
                f"Requested {requested_slides} content slides but plan contains only {actual_count} total slides. "
                "The LLM may have consolidated content."
            )
        elif actual_count > expected_total + 3:
            result.add_warning(
                f"Requested {requested_slides} content slides (+ 4 mandatory structural slides) but plan contains {actual_count} slides. "
                "Extra slides will be included."
            )

    # 2. First slide should be TITLE
    first_layout = plan.slides[0].layout_type.upper()
    if first_layout != "TITLE":
        result.add_warning(
            f"First slide uses '{first_layout}' layout instead of 'TITLE'. "
            "Consider using TITLE for the opening slide."
        )

    seen_numbers: set[int] = set()

    for slide in plan.slides:
        slide_label = f"Slide {slide.slide_number}"

        # 3. Duplicate slide numbers
        if slide.slide_number in seen_numbers:
            result.add_error(f"{slide_label}: Duplicate slide number.")
        seen_numbers.add(slide.slide_number)

        # 4. Title present (skip SECTION_HEADER which may use section_title)
        if not slide.title or slide.title.strip() == "":
            result.add_error(f"{slide_label}: Missing title.")

        # 5. Layout exists
        lt = slide.layout_type.upper()
        if not layout_manager.is_valid_layout(lt):
            # Check if it can be resolved via alias
            resolved = layout_manager.normalise_layout_type(lt)
            if resolved == "TITLE_AND_CONTENT" and lt not in ("TITLE_AND_CONTENT", "CONTENT"):
                result.add_warning(
                    f"{slide_label}: Unknown layout '{lt}' — will use '{resolved}' fallback."
                )

        # 6. Content not completely empty
        if not slide.content:
            result.add_warning(f"{slide_label}: Content appears to be empty.")
        else:
            # Check for unfilled placeholder text
            content_str = str(slide.content).lower()
            for pattern in UNFILLED_PATTERNS:
                if pattern in content_str:
                    result.add_warning(
                        f"{slide_label}: Content may contain unfilled placeholder text ('{pattern}')."
                    )
                    break

    logger.info(
        "Plan validation complete: %d errors, %d warnings",
        len(result.errors),
        len(result.warnings),
    )

    return result


def validate_pptx_file(file_path: Path) -> ValidationResult:
    """
    Validate a generated .pptx file.

    Checks:
    - File exists and is non-empty
    - File can be opened as a valid .pptx
    - Contains at least one slide
    """
    result = ValidationResult()

    if not file_path.exists():
        result.add_error(f"Output file not found: {file_path}")
        return result

    if file_path.stat().st_size == 0:
        result.add_error("Output file is empty (0 bytes).")
        return result

    try:
        from pptx import Presentation
        prs = Presentation(str(file_path))
        slide_count = len(prs.slides)

        if slide_count == 0:
            result.add_error("Generated presentation has no slides.")
        else:
            logger.info("PPTX validation: %d slides, %.1f KB",
                        slide_count, file_path.stat().st_size / 1024)

    except Exception as e:
        result.add_error(f"Generated file is not a valid .pptx: {e}")

    return result


def validate_pptx_bytes(pptx_bytes: bytes) -> ValidationResult:
    """Validate a .pptx provided as bytes (e.g., in-memory before saving)."""
    import io
    result = ValidationResult()

    if not pptx_bytes:
        result.add_error("Generated presentation bytes are empty.")
        return result

    try:
        from pptx import Presentation
        buf = io.BytesIO(pptx_bytes)
        prs = Presentation(buf)
        slide_count = len(prs.slides)

        if slide_count == 0:
            result.add_error("Generated presentation has no slides.")
        else:
            logger.info(
                "In-memory PPTX validation: %d slides, %d bytes",
                slide_count, len(pptx_bytes)
            )

    except Exception as e:
        result.add_error(f"Generated file is not a valid .pptx: {e}")

    return result
