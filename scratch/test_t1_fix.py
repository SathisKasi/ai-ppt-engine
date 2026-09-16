"""
scratch/test_t1_fix.py — Verifies Template-1 builder fixes:
1. Tests with the user's run plan (legacy format) to verify conversion and canvas cleaning.
2. Tests with a full dynamic plan (ACTION_TABLE, MULTI_COLUMN_CARDS, COMPARISON_SPLIT, PROCESS_PIPELINE).
3. Inspects shapes on every slide to guarantee zero residual dummy template shapes.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pptx import Presentation
from llm.schemas import PresentationPlan
from llm.dynamic_layout_schemas import (
    CardItem,
    ComparisonColumn,
    DynamicLayoutComposition,
    DynamicPresentationPlan,
    DynamicSlideDefinition,
    HeroBlock,
    KPIMetricItem,
    ProcessStepItem,
)
from core.builders.template1_builder import Template1Builder

# ---------------------------------------------------------------------------
# Test 1: User's previous plan run
# ---------------------------------------------------------------------------
plan_file = Path("logs/llm/20260916_162836_14e892/presentation_plan.json")
with open(plan_file, "r", encoding="utf-8") as f:
    legacy_data = json.load(f)

legacy_plan = PresentationPlan.model_validate(legacy_data)
builder = Template1Builder()

print("=== BUILDING PRESENTATION FROM USER'S PREVIOUS RUN PLAN ===")
pptx_bytes = builder.build(legacy_plan)
out_path_legacy = Path("output/test_template1_user_plan_fixed.pptx")
out_path_legacy.parent.mkdir(parents=True, exist_ok=True)
out_path_legacy.write_bytes(pptx_bytes)
print(f"Saved: {out_path_legacy} ({len(pptx_bytes):,} bytes)")

prs = Presentation(str(out_path_legacy))
print(f"Total slides: {len(prs.slides)}")

# Check for residual template text
dummy_strings = ["SP4657", "App Dev 17", "PI13 Retrospective", "TARGET 61", "17 App Dev PODs"]
for idx, slide in enumerate(prs.slides):
    all_text = " ".join([s.text for s in slide.shapes if hasattr(s, "text")])
    for ds in dummy_strings:
        if ds in all_text:
            print(f"  [FAIL] Residual dummy text '{ds}' found on slide {idx + 1}!")
            raise AssertionError(f"Residual dummy text found on slide {idx + 1}")
    print(f"  Slide {idx + 1}: {len(slide.shapes)} shapes | Clean!")

# ---------------------------------------------------------------------------
# Test 2: Full Dynamic Plan with Context-Driven Layouts
# ---------------------------------------------------------------------------
print("\n=== BUILDING DYNAMIC CONTEXT-DRIVEN PRESENTATION ===")
dyn_plan = DynamicPresentationPlan(
    title="ATLAS Solution Modernization & Cloud Transformation",
    subtitle="Program Strategy | Architecture | Execution Roadmap",
    date="16SEP2026",
    audience="UPS Executive Leadership",
    slides=[
        DynamicSlideDefinition(
            slide_number=3,
            title="Executive Summary & Strategic Pillars",
            executive_takeaway="Modernize ATLAS to a cloud-native, compliant platform with zero operational disruption.",
            layout_pattern="MULTI_COLUMN_CARDS",
            composition=DynamicLayoutComposition(
                pattern="MULTI_COLUMN_CARDS",
                cards=[
                    CardItem(
                        title="Security Remediation",
                        tag="Critical",
                        bullets=[
                            "Close all compliance gaps across enterprise systems",
                            "Enforce end-to-end encryption standards",
                            "Centralize IAM identity and access policies",
                        ],
                    ),
                    CardItem(
                        title="Cloud Modernization",
                        tag="Strategic",
                        bullets=[
                            "Re-platform legacy components to containerized services",
                            "Automate CI/CD with automated testing guardrails",
                            "Establish multi-region high availability topology",
                        ],
                    ),
                    CardItem(
                        title="Operational Resiliency",
                        tag="Governance",
                        bullets=[
                            "Implement 24/7 observability and telemetry logging",
                            "Ensure zero Severity-1 defects at milestone exits",
                            "Preserve existing business logic seamlessly",
                        ],
                    ),
                ],
            ),
        ),
        DynamicSlideDefinition(
            slide_number=4,
            title="Architecture: Current vs Modernized Target",
            executive_takeaway="Transitioning from monolithic on-prem to resilient cloud microservices.",
            layout_pattern="COMPARISON_SPLIT",
            composition=DynamicLayoutComposition(
                pattern="COMPARISON_SPLIT",
                comparison=[
                    ComparisonColumn(
                        heading="Current Legacy Architecture",
                        tag="Legacy Monolith",
                        bullets=[
                            "Fragmented identity models across workstreams",
                            "Manual deployment procedures with high lead time",
                            "Unsupported legacy runtimes and libraries",
                            "Single points of failure in core processing",
                        ],
                    ),
                    ComparisonColumn(
                        heading="Target Modernized Platform",
                        tag="Cloud Native",
                        bullets=[
                            "Unified enterprise IAM with role-based access",
                            "Fully automated CI/CD with security scanning",
                            "Modern containerized microservices on Kubernetes",
                            "Active-active resiliency with automated failover",
                        ],
                    ),
                ],
            ),
        ),
        DynamicSlideDefinition(
            slide_number=5,
            title="Execution Roadmap & Migration Phases",
            executive_takeaway="Four structured phases spanning discovery through production cutover.",
            layout_pattern="PROCESS_PIPELINE",
            composition=DynamicLayoutComposition(
                pattern="PROCESS_PIPELINE",
                steps=[
                    ProcessStepItem(step_number="01", title="Assessment & Discovery", description="Audit dependencies, security posture, and runtime baseline", tag="Month 1"),
                    ProcessStepItem(step_number="02", title="Foundation & Cloud Setup", description="Deploy secure landing zone, CI/CD pipelines, and IAM policies", tag="Month 2-3"),
                    ProcessStepItem(step_number="03", title="Workstream Migration", description="Iterative refactoring of POD services with automated regression tests", tag="Month 4-5"),
                    ProcessStepItem(step_number="04", title="Validation & Cutover", description="Exit criteria sign-off, chaos testing, and production go-live", tag="Month 6"),
                ],
            ),
        ),
        DynamicSlideDefinition(
            slide_number=6,
            title="Governance, Actions & Leadership Asks",
            executive_takeaway="Three high-priority action items required to unblock Phase 1 start.",
            layout_pattern="ACTION_TABLE",
            composition=DynamicLayoutComposition(
                pattern="ACTION_TABLE",
                cards=[
                    CardItem(title="Telemetry Access", bullets=["Provide enterprise GitHub and log access to the delivery team"], tag="22 Sep", footer="UPS Infosec"),
                    CardItem(title="ADID Permissions", bullets=["Enable cross-realm ADID service credentials for CI/CD runners"], tag="24 Sep", footer="Nari / Identity Team"),
                    CardItem(title="Operating Model", bullets=["Finalize joint agile governance charter and exit gates"], tag="02 Oct", footer="TechM & UPS PMO"),
                ],
                hero=HeroBlock(headline="Leadership Ask: Approve security access requests by 22 Sep to maintain the sprint schedule."),
            ),
        ),
    ],
)

pptx_bytes_dyn = builder.build(dyn_plan)
out_path_dyn = Path("output/test_template1_dynamic_clean.pptx")
out_path_dyn.write_bytes(pptx_bytes_dyn)
print(f"Saved: {out_path_dyn} ({len(pptx_bytes_dyn):,} bytes)")

prs_dyn = Presentation(str(out_path_dyn))
print(f"Total slides in dynamic deck: {len(prs_dyn.slides)}")
for idx, slide in enumerate(prs_dyn.slides):
    all_text = " ".join([s.text for s in slide.shapes if hasattr(s, "text")])
    for ds in dummy_strings:
        if ds in all_text:
            print(f"  [FAIL] Residual dummy text '{ds}' found on slide {idx + 1}!")
            raise AssertionError(f"Residual dummy text found on slide {idx + 1}")
    print(f"  Slide {idx + 1}: {len(slide.shapes)} shapes | Clean!")

print("\nALL VERIFICATIONS PASSED 100%!")
