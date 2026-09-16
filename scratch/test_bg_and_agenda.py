import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

prs = Presentation('AITransformationWeeklyUpdate4SEP2026.pptx')

# Test 1: Clone slide and check background fill
s3 = prs.slides[2]
new_s = prs.slides.add_slide(s3.slide_layout)
new_s.background.fill.solid()
new_s.background.fill.fore_color.rgb = RGBColor(0xF7, 0xF4, 0xEF)
print("New slide background fill type:", new_s.background.fill.type, new_s.background.fill.fore_color.rgb)

# Test 2: Agenda on Slide 2
s2 = prs.slides[1]
# Remove Group 8
for sh in list(s2.shapes):
    if sh.name == 'Group 8':
        sp = sh._element
        sp.getparent().remove(sp)

agenda_titles = [
    ("Executive Summary & Strategic Pillars", "Scope | Priorities | Governance"),
    ("Current vs Target Architecture", "Legacy Monolith vs Cloud Native"),
    ("Execution Roadmap & Migration Phases", "Phased 6-Month Plan"),
    ("Governance, Actions & Leadership Asks", "Immediate Decisions & Owners"),
]

for idx, (title, sub) in enumerate(agenda_titles, start=1):
    item_top = Inches(1.8) + (idx - 1) * Inches(1.05)
    # Circle badge
    badge = s2.shapes.add_shape(MSO_SHAPE.OVAL, Inches(5.8), item_top, Inches(0.38), Inches(0.38))
    badge.fill.solid()
    badge.fill.fore_color.rgb = RGBColor(0x35, 0x1C, 0x15)
    badge.line.color.rgb = RGBColor(0xFF, 0xB5, 0x00)
    badge.line.width = Pt(1.5)
    tf = badge.text_frame
    p = tf.paragraphs[0]
    p.text = str(idx)
    r = p.runs[0]
    r.font.name = "Aptos"
    r.font.size = Pt(13)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    # Label box
    tb = s2.shapes.add_textbox(Inches(6.35), item_top - Inches(0.04), Inches(6.0), Inches(0.85))
    tf2 = tb.text_frame
    tf2.word_wrap = True
    p2 = tf2.paragraphs[0]
    p2.text = title
    r2 = p2.runs[0]
    r2.font.name = "Aptos"
    r2.font.size = Pt(16)
    r2.font.bold = True
    r2.font.color.rgb = RGBColor(0x35, 0x1C, 0x15)

    if sub:
        p3 = tf2.add_paragraph()
        p3.space_before = Pt(3)
        r3 = p3.add_run()
        r3.text = sub
        r3.font.name = "Aptos"
        r3.font.size = Pt(10.5)
        r3.font.color.rgb = RGBColor(0x79, 0x6B, 0x61)

print(f"Slide 2 shapes after dynamic agenda: {len(s2.shapes)}")
print("Test completed successfully!")
