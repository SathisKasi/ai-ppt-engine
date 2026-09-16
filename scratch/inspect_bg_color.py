from pptx import Presentation

prs = Presentation('AITransformationWeeklyUpdate4SEP2026.pptx')
for idx in [2, 3]:
    s = prs.slides[idx]
    print(f"Slide {idx+1}:")
    print(f"  slide.background: {s.background}")
    if s.background:
        print(f"    fill.type: {s.background.fill.type}")
        try:
            print(f"    fill.fore_color.rgb: {s.background.fill.fore_color.rgb}")
        except Exception as e:
            print(f"    fore_color error: {e}")
    # Also check slide_layout background
    sl = s.slide_layout
    print(f"  layout.background: {sl.background}")
    if sl.background:
        print(f"    layout fill.type: {sl.background.fill.type}")
        try:
            print(f"    layout fill.fore_color.rgb: {sl.background.fill.fore_color.rgb}")
        except Exception as e:
            print(f"    layout fore_color error: {e}")
    # Also check master background
    sm = sl.slide_master
    print(f"  master.background: {sm.background}")
    if sm.background:
        print(f"    master fill.type: {sm.background.fill.type}")
        try:
            print(f"    master fill.fore_color.rgb: {sm.background.fill.fore_color.rgb}")
        except Exception as e:
            print(f"    master fore_color error: {e}")
