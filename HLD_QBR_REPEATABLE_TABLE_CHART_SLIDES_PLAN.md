# HLD QBR: Repeatable Table/Chart Slides Plan

## Request
If the source document contains multiple distinct tables/numeric datasets, the
planner should be allowed to use the same table/chart-capable template slide
more than once (one instance per dataset), instead of being capped at one use
per slide type. The **total** number of generated slides must still equal the
user-requested count — relaxing the once-only rule never inflates the deck.

## Why the restriction existed
`core/presentation_planner_hld_qbr_generic.py`'s `_resolve_picks()` deduped
every outline pick by `slide_id` (`seen` set), so each of the 35 catalog slide
types could only ever appear once in a deck, even when the source had several
tabular datasets competing for the one table slide.

## Design
1. **Catalog**: `core/hld_qbr_catalog.py`'s `compact_catalog_for_outline()` now
   adds `"repeatable": true` to any slide entry where `has_table` or
   `has_chart` is true, so the outline LLM call can see explicitly which
   slide_ids may repeat (previously it only had `"table"`/`"chart"` capability
   keys with no explicit repeat permission).
2. **Prompt**: `llm/prompts_hld_qbr_generic.py`'s outline system role and
   instructions now state the rule: every slide_id is single-use **except**
   one flagged `"repeatable": true`, which may be picked again (one pick per
   extra distinct dataset) — the **total pick count must still equal the
   requested slide count exactly**.
3. **Resolver**: `core/presentation_planner_hld_qbr_generic.py`'s
   `_resolve_picks()` now only blocks a duplicate `slide_id` when the catalog
   entry is NOT table/chart-capable. For repeatable entries, duplicates are
   kept. Each pick gets a unique `fill_key` (`slide_id` for the first use,
   `slide_id__2`, `slide_id__3`, ... for repeats) so later stages never
   confuse two instances of the same slide_id.
4. **Fill stage collision fix**: `_run_fill_stage()` previously keyed its
   internal `filled_by_id` dict (and the slot-alias reverse map) by the raw
   `slide_id` — with repeats this would make the second instance's filled
   content silently overwrite the first's, producing two identical slides.
   Fixed by keying everything by the new `fill_key` instead, and overriding
   the `"slide_id"` field sent to the fill LLM call with the `fill_key`
   (the LLM just echoes a short token back, same pattern already used for
   slot-id aliasing).
5. **Final assembly**: `plan_hld_qbr_presentation_generic()`'s slide-assembly
   loop now looks up filled content via `pick["fill_key"]` instead of
   `pick["slide_id"]`.
6. **Rendering/governance**: verified `core/builders/hld_qbr_generic_builder.py`
   and `core/governance.py` never key anything by `slide_id` in a way that
   assumes uniqueness (both iterate `plan.slides` as a plain list) — no
   changes needed there. `SlideAssignment`/`GenericHLDQBRPlan` schemas also
   have no uniqueness constraint on `slide_id`.

## Scope / what did NOT change
- Non-table/non-chart slide types (plain text, repeat-group cards) remain
  strictly single-use per deck.
- The requested slide count is still a hard cap — `resolved[:requested_slide_count]`
  is unchanged, so relaxing the repeat rule can only change *which* slides
  fill the N slots, never the total N.
- `exec_summary`/cover/agenda/closing special-casing in the builder is
  untouched.

## Verification performed
- `_resolve_picks()` sanity-checked directly (ad-hoc, not a committed test):
  two picks for a chart-capable slide_id and two for a table-capable slide_id
  both survived; two picks for a plain (non-repeatable) slide_id correctly
  deduped to one; total capped at the requested count.
- `scratch/hld_qbr/test_generic_pipeline_mock_e2e.py` was run and still fails
  — confirmed **pre-existing**, unrelated to this change: it asserts exactly
  2 mock LLM calls (1 outline + 1 batched fill), but `FILL_BATCH_SIZE` was
  already set to `1` (one slide per fill call) before this change, so the
  call-count and forced-slide-count assumptions in that test were already
  stale. Not modified as part of this plan (out of scope; flagged here for
  awareness).

## Follow-ups not done (flagged, not blocking)
- No new automated test was added for the repeat-slide path itself (only an
  ad-hoc manual check). If this becomes a regular feature, the existing e2e
  test should be refreshed (it needs fixing anyway for the `FILL_BATCH_SIZE`
  mismatch) to also cover a duplicated chart/table pick.
