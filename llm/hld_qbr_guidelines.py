"""
llm/hld_qbr_guidelines.py — Machine-readable template guidance mined from the
HLD QBR template's own "FORMATTING HELP" appendix (guardrails, brand colors,
typography, data-viz rules) and its OOXML theme.

None of this is invented — every value is either extracted directly from the
template's theme XML (colors, fonts) or transcribed from the guardrail/brand/
formatting-help slides' own text. These appendix slides are GUIDE_ONLY (never
cloned into generated output — see core/builders/hld_qbr_builder.py) but their
knowledge is injected into the LLM system prompt so generated content still
respects them.
"""
from __future__ import annotations

# Brand colors — extracted from ppt/theme/theme1.xml
BRAND_COLORS = {
    "dk1_black": "000000",
    "lt1_white": "FFFFFF",
    "dk2_gray": "58595B",
    "lt2_gray": "D8D4D7",
    "accent1_navy": "0E2554",
    "accent2_blue": "426DA9",
    "accent3_dark_brown": "330000",
    "accent4_amber": "FFBE00",
    "accent5_teal": "008575",
    "accent6_light_blue": "88A7D1",
}

# Typography — transcribed from the template's "TITLE IS 22 PT VERDANA BOLD UPPERCASE" slide
TYPOGRAPHY = {
    "title": "22pt Verdana Bold, UPPERCASE",
    "subtitle": "18pt Verdana",
    "body_first_level": "18pt Verdana, may use a theme color if it functions as a title",
    "min_font_size": "12pt (only reduce this far if content otherwise won't fit)",
    "theme_fonts": ["Georgia", "Verdana"],
}

# Content guardrails — transcribed verbatim from the template's "GUARDRAILS" slide
CONTENT_GUARDRAILS = [
    "Do not import any slides that are not in the current HC brand guidelines; "
    "insert a new slide within the existing presentation and copy only the content over.",
    "Product slide verbiage cannot be changed; the header can be customized but must remain one line.",
    "Newly created product slides need to be approved by SME, product owners, or Seismic.",
    "All claims must be sourced.",
    "Per legal, customer logos or personal data cannot be used without written consent.",
    "Translation services are not available; content other than English cannot be included.",
    "Updates need to be provided at least 48 hours before the deadline; if the meeting is "
    "postponed, notify the presentation team ASAP with the new date.",
    "The final deck and any change requests must be finalized within two business days after the meeting.",
]

# Brand color usage rules — transcribed from the template's "BRAND APPROVED COLORS" slide
COLOR_USAGE_RULES = [
    "The default slide background is white.",
    "Normal text is the dark brown tone (accent3, #330000); UPS Blue (accent1/accent2) "
    "is the default color for emphasis and bullets, but other theme colors may be used as needed.",
    "Title and subtitle text use the UPS dark brown tone.",
    "Only use the colors already set within this template's theme — no ad-hoc colors.",
]

# Data visualization guidance — transcribed from the template's data-viz sample slides
DATA_VIZ_GUIDANCE = [
    "For process flows, the preferred color is UPS Gray 4; use a secondary color only to "
    "highlight a specific segment.",
    "For graphs, charts, and tables, monochromatic secondary colors give a more impactful look.",
    "Segment/step titles in process flows are initial-cap and left-aligned.",
]


def build_llm_guidelines_prompt() -> str:
    """Assembles all mined template knowledge into a system-prompt-ready text block."""
    lines = [
        "TEMPLATE BRAND & CONTENT GUIDELINES (HLD QBR Template) — MUST BE FOLLOWED:",
        "",
        "Approved brand colors (hex, from the template theme):",
    ]
    for name, hexval in BRAND_COLORS.items():
        lines.append(f"  - {name}: #{hexval}")

    lines.append("")
    lines.append("Typography rules:")
    for key, val in TYPOGRAPHY.items():
        if key == "theme_fonts":
            continue
        lines.append(f"  - {key.replace('_', ' ')}: {val}")
    lines.append(f"  - Approved fonts only: {', '.join(TYPOGRAPHY['theme_fonts'])}")

    lines.append("")
    lines.append("Content guardrails (legal/brand/process — non-negotiable):")
    for rule in CONTENT_GUARDRAILS:
        lines.append(f"  - {rule}")

    lines.append("")
    lines.append("Color usage rules:")
    for rule in COLOR_USAGE_RULES:
        lines.append(f"  - {rule}")

    lines.append("")
    lines.append("Data visualization guidance:")
    for rule in DATA_VIZ_GUIDANCE:
        lines.append(f"  - {rule}")

    lines.append("")
    lines.append(
        "These rules come from the template's own internal 'Formatting Help' reference "
        "slides (guardrails, brand colors, typography, sample tables/charts, icon library). "
        "Those reference slides are for authoring guidance only and must NEVER be copied "
        "or reproduced in the generated output deck."
    )
    return "\n".join(lines)
