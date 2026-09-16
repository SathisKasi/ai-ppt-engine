"""
templates/create_template.py — Programmatic template generator.

This script creates a professional dark-themed PowerPoint template
with all 11 required slide layouts embedded as named slide masters.

Run once (automatically called by layout_manager.py if template is missing):
    python templates/create_template.py

The generated file is saved to: templates/presentation_template.pptx

All shapes created here are native python-pptx objects, fully editable
in Microsoft PowerPoint.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path when running as standalone script
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt, Emu
from pptx.util import Inches as In


# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
BG_DARK = RGBColor(0x1A, 0x1A, 0x2E)       # Deep navy background
BG_CARD = RGBColor(0x16, 0x21, 0x3E)        # Card/section background
ACCENT_BLUE = RGBColor(0x0F, 0x34, 0x60)    # Mid blue accent
ACCENT_PURPLE = RGBColor(0x53, 0x34, 0x83)  # Purple highlight
ACCENT_RED = RGBColor(0xE9, 0x45, 0x60)     # Vibrant accent red
TEXT_WHITE = RGBColor(0xFF, 0xFF, 0xFF)      # Pure white
TEXT_LIGHT = RGBColor(0xE0, 0xE0, 0xE0)     # Off-white
TEXT_MUTED = RGBColor(0xA0, 0xA0, 0xB0)     # Muted grey

# Slide dimensions (16:9 widescreen)
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def rgb_to_fill(shape, r, g, b):
    """Apply solid fill color to a shape."""
    from pptx.dml.color import RGBColor as RGB
    fill = shape.fill
    fill.solid()
    fill.fore_color.rgb = RGB(r, g, b)


def add_background(slide, color: RGBColor = BG_DARK):
    """Fill slide background with a solid color."""
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_text_box(
    slide,
    text: str,
    left: float, top: float,
    width: float, height: float,
    font_size: int = 18,
    bold: bool = False,
    color: RGBColor = TEXT_WHITE,
    align=PP_ALIGN.LEFT,
    font_name: str = "Calibri",
) -> object:
    """Add a styled text box to a slide."""
    from pptx.util import Inches, Pt
    txBox = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font_name
    return txBox


def add_rect(
    slide,
    left: float, top: float,
    width: float, height: float,
    fill_color: RGBColor = ACCENT_BLUE,
    line_color: RGBColor = None,
) -> object:
    """Add a filled rectangle."""
    from pptx.util import Inches
    from pptx.dml.color import RGBColor as RGB
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
    return shape


def create_title_layout(prs: Presentation) -> None:
    """Slide 1: Title slide."""
    slide_layout = prs.slide_layouts[6]  # Blank layout
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, BG_DARK)

    # Large accent bar at bottom
    add_rect(slide, 0, 6.2, 13.333, 0.1, ACCENT_RED)

    # Decorative top accent
    add_rect(slide, 0, 0, 13.333, 0.08, ACCENT_PURPLE)

    # Side accent line
    add_rect(slide, 0, 0, 0.05, 7.5, ACCENT_PURPLE)

    # Title
    add_text_box(
        slide, "Presentation Title",
        left=1.0, top=2.0, width=11.0, height=1.5,
        font_size=44, bold=True, color=TEXT_WHITE, align=PP_ALIGN.CENTER
    )

    # Subtitle
    add_text_box(
        slide, "Subtitle • Author • Date",
        left=1.0, top=3.8, width=11.0, height=0.8,
        font_size=22, bold=False, color=TEXT_LIGHT, align=PP_ALIGN.CENTER
    )

    # Bottom label
    add_text_box(
        slide, "CONFIDENTIAL",
        left=0.3, top=6.8, width=3.0, height=0.4,
        font_size=10, bold=False, color=TEXT_MUTED, align=PP_ALIGN.LEFT
    )


def create_title_content_layout(prs: Presentation) -> None:
    """Slide 2: Title + bullet content."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, BG_DARK)

    # Header bar
    add_rect(slide, 0, 0, 13.333, 1.4, ACCENT_BLUE)

    # Left accent stripe on header
    add_rect(slide, 0, 0, 0.08, 1.4, ACCENT_RED)

    # Slide title in header
    add_text_box(
        slide, "Slide Title",
        left=0.3, top=0.1, width=12.5, height=1.1,
        font_size=28, bold=True, color=TEXT_WHITE
    )

    # Content area background
    add_rect(slide, 0.3, 1.6, 12.7, 5.5, BG_CARD)

    # Bullet content placeholder
    add_text_box(
        slide, "• Key point one\n• Key point two\n• Key point three\n• Key point four",
        left=0.6, top=1.8, width=12.2, height=5.0,
        font_size=18, bold=False, color=TEXT_LIGHT
    )

    # Slide number
    add_text_box(
        slide, "2",
        left=12.8, top=7.1, width=0.4, height=0.3,
        font_size=10, bold=False, color=TEXT_MUTED, align=PP_ALIGN.RIGHT
    )


def create_two_column_layout(prs: Presentation) -> None:
    """Slide 3: Two-column layout."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, BG_DARK)

    # Header
    add_rect(slide, 0, 0, 13.333, 1.4, ACCENT_BLUE)
    add_rect(slide, 0, 0, 0.08, 1.4, ACCENT_RED)
    add_text_box(slide, "Slide Title", left=0.3, top=0.1, width=12.5, height=1.1,
                 font_size=28, bold=True, color=TEXT_WHITE)

    # Left column
    add_rect(slide, 0.3, 1.6, 6.1, 5.5, BG_CARD)
    add_text_box(slide, "Left Heading", left=0.4, top=1.7, width=5.8, height=0.6,
                 font_size=16, bold=True, color=ACCENT_RED)
    add_text_box(slide, "• Point one\n• Point two\n• Point three",
                 left=0.4, top=2.4, width=5.8, height=4.4,
                 font_size=16, bold=False, color=TEXT_LIGHT)

    # Divider
    add_rect(slide, 6.6, 1.6, 0.05, 5.5, ACCENT_PURPLE)

    # Right column
    add_rect(slide, 6.9, 1.6, 6.1, 5.5, BG_CARD)
    add_text_box(slide, "Right Heading", left=7.0, top=1.7, width=5.8, height=0.6,
                 font_size=16, bold=True, color=ACCENT_PURPLE)
    add_text_box(slide, "• Point one\n• Point two\n• Point three",
                 left=7.0, top=2.4, width=5.8, height=4.4,
                 font_size=16, bold=False, color=TEXT_LIGHT)


def create_section_header_layout(prs: Presentation) -> None:
    """Slide 4: Section header / chapter divider."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, ACCENT_BLUE)

    add_rect(slide, 0, 0, 0.08, 7.5, ACCENT_RED)
    add_rect(slide, 0, 3.5, 13.333, 0.06, ACCENT_RED)

    add_text_box(
        slide, "Section Title",
        left=1.0, top=1.8, width=11.0, height=1.4,
        font_size=40, bold=True, color=TEXT_WHITE, align=PP_ALIGN.CENTER
    )
    add_text_box(
        slide, "Section description or subtitle",
        left=1.5, top=3.7, width=10.0, height=0.8,
        font_size=18, bold=False, color=TEXT_LIGHT, align=PP_ALIGN.CENTER
    )


def create_image_text_layout(prs: Presentation) -> None:
    """Slide 5: Image + text layout."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, BG_DARK)

    add_rect(slide, 0, 0, 13.333, 1.4, ACCENT_BLUE)
    add_rect(slide, 0, 0, 0.08, 1.4, ACCENT_RED)
    add_text_box(slide, "Slide Title", left=0.3, top=0.1, width=12.5, height=1.1,
                 font_size=28, bold=True, color=TEXT_WHITE)

    # Image placeholder (left side)
    img_box = add_rect(slide, 0.3, 1.6, 6.0, 5.5, BG_CARD)
    add_text_box(slide, "[ Image / Diagram ]",
                 left=0.5, top=3.5, width=5.6, height=1.0,
                 font_size=16, bold=False, color=TEXT_MUTED, align=PP_ALIGN.CENTER)

    # Text area (right side)
    add_rect(slide, 6.6, 1.6, 6.4, 5.5, BG_CARD)
    add_text_box(slide, "Description text\n\n• Key detail one\n• Key detail two\n• Key detail three",
                 left=6.8, top=1.8, width=6.0, height=5.0,
                 font_size=16, bold=False, color=TEXT_LIGHT)


def create_comparison_layout(prs: Presentation) -> None:
    """Slide 6: Comparison layout."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, BG_DARK)

    add_rect(slide, 0, 0, 13.333, 1.4, ACCENT_BLUE)
    add_rect(slide, 0, 0, 0.08, 1.4, ACCENT_RED)
    add_text_box(slide, "Comparison Title", left=0.3, top=0.1, width=12.5, height=1.1,
                 font_size=28, bold=True, color=TEXT_WHITE)

    # Left option header
    add_rect(slide, 0.3, 1.6, 6.0, 0.7, ACCENT_RED)
    add_text_box(slide, "Option A", left=0.4, top=1.65, width=5.8, height=0.5,
                 font_size=18, bold=True, color=TEXT_WHITE)
    add_rect(slide, 0.3, 2.35, 6.0, 4.75, BG_CARD)
    add_text_box(slide, "• Advantage one\n• Advantage two\n• Advantage three\n• Advantage four",
                 left=0.5, top=2.5, width=5.7, height=4.4,
                 font_size=16, bold=False, color=TEXT_LIGHT)

    # VS label
    add_text_box(slide, "VS", left=6.4, top=3.5, width=0.5, height=0.5,
                 font_size=20, bold=True, color=ACCENT_PURPLE, align=PP_ALIGN.CENTER)

    # Right option header
    add_rect(slide, 7.0, 1.6, 6.0, 0.7, ACCENT_PURPLE)
    add_text_box(slide, "Option B", left=7.1, top=1.65, width=5.8, height=0.5,
                 font_size=18, bold=True, color=TEXT_WHITE)
    add_rect(slide, 7.0, 2.35, 6.0, 4.75, BG_CARD)
    add_text_box(slide, "• Advantage one\n• Advantage two\n• Advantage three\n• Advantage four",
                 left=7.1, top=2.5, width=5.7, height=4.4,
                 font_size=16, bold=False, color=TEXT_LIGHT)


def create_timeline_layout(prs: Presentation) -> None:
    """Slide 7: Timeline layout."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, BG_DARK)

    add_rect(slide, 0, 0, 13.333, 1.4, ACCENT_BLUE)
    add_rect(slide, 0, 0, 0.08, 1.4, ACCENT_RED)
    add_text_box(slide, "Timeline", left=0.3, top=0.1, width=12.5, height=1.1,
                 font_size=28, bold=True, color=TEXT_WHITE)

    # Horizontal timeline line
    add_rect(slide, 0.5, 3.9, 12.3, 0.06, ACCENT_RED)

    # Timeline nodes (4 items)
    positions = [1.0, 4.0, 7.0, 10.0]
    labels = ["2024", "2025", "2026", "2027"]
    events = ["Phase One", "Phase Two", "Phase Three", "Phase Four"]

    for i, (x, lbl, evt) in enumerate(zip(positions, labels, events)):
        # Node dot
        dot = slide.shapes.add_shape(9, Inches(x + 0.85), Inches(3.65), Inches(0.3), Inches(0.3))
        dot.fill.solid()
        dot.fill.fore_color.rgb = ACCENT_RED
        dot.line.fill.background()

        # Date label
        add_text_box(slide, lbl, left=x + 0.5, top=4.1, width=1.3, height=0.4,
                     font_size=14, bold=True, color=ACCENT_RED, align=PP_ALIGN.CENTER)

        # Card above / below alternating
        if i % 2 == 0:
            add_rect(slide, x + 0.2, 2.0, 2.2, 1.5, BG_CARD)
            add_text_box(slide, evt, left=x + 0.3, top=2.1, width=2.0, height=1.2,
                         font_size=13, bold=False, color=TEXT_LIGHT, align=PP_ALIGN.CENTER)
        else:
            add_rect(slide, x + 0.2, 4.7, 2.2, 1.5, BG_CARD)
            add_text_box(slide, evt, left=x + 0.3, top=4.8, width=2.0, height=1.2,
                         font_size=13, bold=False, color=TEXT_LIGHT, align=PP_ALIGN.CENTER)


def create_process_layout(prs: Presentation) -> None:
    """Slide 8: Process / workflow layout."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, BG_DARK)

    add_rect(slide, 0, 0, 13.333, 1.4, ACCENT_BLUE)
    add_rect(slide, 0, 0, 0.08, 1.4, ACCENT_RED)
    add_text_box(slide, "Process / Workflow", left=0.3, top=0.1, width=12.5, height=1.1,
                 font_size=28, bold=True, color=TEXT_WHITE)

    steps = [("1", "Step One"), ("2", "Step Two"), ("3", "Step Three"), ("4", "Step Four")]
    colors = [ACCENT_RED, ACCENT_PURPLE, ACCENT_BLUE, RGBColor(0x00, 0x88, 0xCC)]

    for i, ((num, title), color) in enumerate(zip(steps, colors)):
        x = 0.4 + i * 3.2

        # Step box
        add_rect(slide, x, 2.0, 2.8, 4.5, BG_CARD)

        # Step number badge
        badge = slide.shapes.add_shape(9, Inches(x + 1.0), Inches(1.85), Inches(0.8), Inches(0.8))
        badge.fill.solid()
        badge.fill.fore_color.rgb = color
        badge.line.fill.background()
        add_text_box(slide, num, left=x + 1.0, top=1.9, width=0.8, height=0.6,
                     font_size=18, bold=True, color=TEXT_WHITE, align=PP_ALIGN.CENTER)

        # Step title
        add_text_box(slide, title, left=x + 0.1, top=2.9, width=2.6, height=0.6,
                     font_size=16, bold=True, color=color, align=PP_ALIGN.CENTER)

        # Step description
        add_text_box(slide, "Description of this step and its key activities",
                     left=x + 0.1, top=3.6, width=2.6, height=2.6,
                     font_size=13, bold=False, color=TEXT_LIGHT, align=PP_ALIGN.CENTER)

        # Arrow between steps
        if i < len(steps) - 1:
            add_text_box(slide, "→", left=x + 2.85, top=3.8, width=0.5, height=0.6,
                         font_size=24, bold=True, color=ACCENT_RED, align=PP_ALIGN.CENTER)


def create_architecture_layout(prs: Presentation) -> None:
    """Slide 9: Architecture / layers layout."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, BG_DARK)

    add_rect(slide, 0, 0, 13.333, 1.4, ACCENT_BLUE)
    add_rect(slide, 0, 0, 0.08, 1.4, ACCENT_RED)
    add_text_box(slide, "System Architecture", left=0.3, top=0.1, width=12.5, height=1.1,
                 font_size=28, bold=True, color=TEXT_WHITE)

    layers = [
        ("Presentation Layer", "User Interface & APIs", ACCENT_RED),
        ("Business Logic Layer", "Core Services & Orchestration", ACCENT_PURPLE),
        ("Data Layer", "Storage, Cache & Messaging", ACCENT_BLUE),
        ("Infrastructure Layer", "Cloud, Security & Monitoring", RGBColor(0x00, 0x77, 0xAA)),
    ]

    for i, (layer_name, desc, color) in enumerate(layers):
        y = 1.6 + i * 1.3
        add_rect(slide, 0.4, y, 12.5, 1.1, color)
        add_text_box(slide, layer_name, left=0.5, top=y + 0.05, width=4.0, height=0.5,
                     font_size=16, bold=True, color=TEXT_WHITE)
        add_text_box(slide, desc, left=4.8, top=y + 0.05, width=7.8, height=0.5,
                     font_size=14, bold=False, color=TEXT_LIGHT)

        if i < len(layers) - 1:
            add_text_box(slide, "↕", left=6.4, top=y + 1.1, width=0.5, height=0.2,
                         font_size=12, bold=False, color=TEXT_MUTED, align=PP_ALIGN.CENTER)


def create_statistics_layout(prs: Presentation) -> None:
    """Slide 10: Statistics / KPIs layout."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, BG_DARK)

    add_rect(slide, 0, 0, 13.333, 1.4, ACCENT_BLUE)
    add_rect(slide, 0, 0, 0.08, 1.4, ACCENT_RED)
    add_text_box(slide, "Key Metrics & Statistics", left=0.3, top=0.1, width=12.5, height=1.1,
                 font_size=28, bold=True, color=TEXT_WHITE)

    stats = [
        ("40%", "Reduction in\nprocessing time", ACCENT_RED),
        ("2x", "Increase in\nthroughput", ACCENT_PURPLE),
        ("$2M", "Annual cost\nsavings", RGBColor(0x00, 0x99, 0x66)),
        ("99.9%", "System\nuptime", RGBColor(0x00, 0x88, 0xCC)),
    ]

    for i, (value, label, color) in enumerate(stats):
        x = 0.4 + i * 3.2
        add_rect(slide, x, 1.8, 2.9, 4.8, BG_CARD)
        add_rect(slide, x, 1.8, 2.9, 0.08, color)  # Top accent line
        add_text_box(slide, value, left=x + 0.1, top=2.5, width=2.7, height=1.4,
                     font_size=48, bold=True, color=color, align=PP_ALIGN.CENTER)
        add_text_box(slide, label, left=x + 0.1, top=4.1, width=2.7, height=1.4,
                     font_size=15, bold=False, color=TEXT_LIGHT, align=PP_ALIGN.CENTER)

    # Context paragraph at bottom
    add_text_box(
        slide, "Based on comparative analysis of before/after implementation data",
        left=0.4, top=6.8, width=12.5, height=0.4,
        font_size=11, bold=False, color=TEXT_MUTED, align=PP_ALIGN.CENTER
    )


def create_conclusion_layout(prs: Presentation) -> None:
    """Slide 11: Conclusion / summary layout."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    add_background(slide, BG_DARK)

    # Full-width gradient-style header
    add_rect(slide, 0, 0, 13.333, 2.0, ACCENT_BLUE)
    add_rect(slide, 0, 0, 0.08, 2.0, ACCENT_RED)
    add_text_box(slide, "Key Takeaways & Next Steps", left=0.3, top=0.3, width=12.5, height=1.4,
                 font_size=30, bold=True, color=TEXT_WHITE)

    # Summary points
    add_rect(slide, 0.3, 2.2, 7.8, 4.9, BG_CARD)
    add_text_box(slide, "SUMMARY", left=0.4, top=2.3, width=3.0, height=0.4,
                 font_size=12, bold=True, color=ACCENT_RED)
    add_text_box(
        slide, "• Key takeaway one\n• Key takeaway two\n• Key takeaway three\n• Key takeaway four",
        left=0.4, top=2.8, width=7.5, height=4.0,
        font_size=17, bold=False, color=TEXT_LIGHT
    )

    # Call to action / next steps
    add_rect(slide, 8.4, 2.2, 4.6, 4.9, ACCENT_PURPLE)
    add_text_box(slide, "NEXT STEPS", left=8.5, top=2.3, width=4.3, height=0.4,
                 font_size=12, bold=True, color=TEXT_WHITE)
    add_text_box(
        slide, "1. Action item one\n2. Action item two\n3. Action item three",
        left=8.5, top=2.8, width=4.3, height=3.5,
        font_size=16, bold=False, color=TEXT_WHITE
    )

    # Bottom CTA
    add_rect(slide, 3.0, 7.0, 7.3, 0.35, ACCENT_RED)
    add_text_box(slide, "Thank You — Questions Welcome",
                 left=3.0, top=7.0, width=7.3, height=0.35,
                 font_size=13, bold=True, color=TEXT_WHITE, align=PP_ALIGN.CENTER)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def create_template(output_path: Path) -> None:
    """Generate the full presentation template and save it."""
    print(f"Creating template: {output_path}")

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # Create all 11 layout slides in order matching layout_metadata.json
    creators = [
        create_title_layout,           # index 0 → TITLE
        create_title_content_layout,   # index 1 → TITLE_AND_CONTENT
        create_two_column_layout,      # index 2 → TWO_COLUMN
        create_section_header_layout,  # index 3 → SECTION_HEADER
        create_image_text_layout,      # index 4 → IMAGE_TEXT
        create_comparison_layout,      # index 5 → COMPARISON
        create_timeline_layout,        # index 6 → TIMELINE
        create_process_layout,         # index 7 → PROCESS
        create_architecture_layout,    # index 8 → ARCHITECTURE
        create_statistics_layout,      # index 9 → STATISTICS
        create_conclusion_layout,      # index 10 → CONCLUSION
    ]

    for fn in creators:
        fn(prs)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))
    print(f"Template saved: {output_path} ({len(prs.slides)} layout slides)")


if __name__ == "__main__":
    from pathlib import Path
    template_path = Path(__file__).parent / "presentation_template.pptx"
    create_template(template_path)
