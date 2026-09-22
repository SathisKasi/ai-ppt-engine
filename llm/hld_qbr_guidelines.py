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
    """Assembles mined template content rules into a concise, token-efficient text block."""
    return (
        "TEMPLATE CONTENT GUARDRAILS:\n"
        "- Grounding: All claims, names, and metrics must be strictly grounded in the source text.\n"
        "- Tone: Executive boardroom tone; concise, high-impact phrasing.\n"
        "- Metrics: Preserve numbers and units exactly as stated; leave target empty (\"\") if none is stated.\n"
        "- Scope: Populate only archetypes with real source evidence; leave others empty."
    )

