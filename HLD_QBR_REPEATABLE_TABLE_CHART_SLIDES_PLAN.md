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

---

## Addendum (2026-10-05): topic-first selection + "no matching slide" edge-case handling

Two follow-up questions were raised and are now implemented:

### 1. Topic selection must happen BEFORE slide-structure matching
Previously the outline prompt told the AI to "choose slide_ids" first and
"cover distinct topics" only as a secondary instruction — risking the AI
picking an attractive/available slide structure and then hunting for content
to fill it, rather than deciding which topics matter most given a limited
slide budget.
Fixed in `llm/prompts_hld_qbr_generic.py` (`SYSTEM_ROLE_HLD_QBR_OUTLINE` +
`HLD_QBR_OUTLINE_PROMPT`): the instructions now explicitly say to rank
topics by importance FIRST (more supporting content items, concrete
metrics, risks/problems/decisions/outcomes, or topics the source
emphasizes), select the top N, and only THEN pick each selected topic's
best-fit slide structure. Also added: if no ideal structure remains
available for an important topic, fall back to the closest available
plain-text slide instead of dropping the topic entirely.

### 2. "AI can't find a matching slide" — gap-fill instead of hard-fail
`core/presentation_planner_hld_qbr_generic.py`'s
`plan_hld_qbr_presentation_generic()` previously: ran the outline once,
retried once with the identical prompt (discarding the first attempt's
picks entirely), then hard-failed if still short.
Now: picks **accumulate** across attempts (a retry can only add, never lose,
already-grounded slides), and a third, narrower **gap-fill** call asks only
for the still-missing count, explicitly excluding already-used slide_ids
(via new `exclude_slide_ids` param on `_run_outline_stage` /
`build_hld_qbr_outline_prompt`) so the AI covers new topics instead of
re-proposing ones that didn't work the first time. The same gap-fill pass
is also applied after the content-fill stage, for slides that got picked
but came back empty from fill. Only after both gap-fill passes does the
pipeline still hard-fail (unchanged final behavior — a requested slide
count remains a hard contract, per earlier design decision; soft-degrade
was discussed but not implemented, pending explicit product decision).
Title/facility/date are now taken only from the FIRST (full) outline
response (`outline_meta`), since gap-fill calls are deliberately narrow and
would otherwise return an empty/irrelevant title.
Added transparency: `plan_hld_qbr_presentation_generic()` now logs how many
of the extracted content items ended up used vs. unused in the final plan.

**Bug found and fixed during testing**: allowing table/chart slide_ids to
repeat (prior change) combined with the new accumulate-across-retries
design created a real risk — a retry re-proposing the *exact same* content
for an already-used repeatable slide_id would have been miscounted as a
genuinely new dataset (since repeats are otherwise allowed), silently
inflating the resolved count with a near-duplicate slide instead of
correctly recognizing it as a duplicate. Fixed in `_resolve_picks()`: a
repeatable slide_id is now only treated as a new instance if its
`content_item_ids` differ from every previously-accepted instance for that
same slide_id (content-signature dedup, via `seen_content_by_sid`).

**Verification**: new `scratch/hld_qbr/test_gap_fill_mock.py` — mock
outline returns only 3/5 picks on both the initial and same-prompt-retry
attempts, a gap-fill call (excluding the 3 used slide_ids) supplies the
remaining 2; asserts exactly 3 outline calls were made, exactly 5 slides in
the final plan, and the title came from the first attempt. Also re-verified
by hand: a retry citing identical content for a repeatable slide_id is now
correctly rejected as a duplicate, while genuinely distinct content for the
same repeatable slide_id is still accepted (no regression on the earlier
repeatable-slides feature).

