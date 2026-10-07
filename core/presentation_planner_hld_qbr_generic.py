"""
core/presentation_planner_hld_qbr_generic.py — Generic, catalog-driven HLD
QBR planner.

Replaces the old two-stage, fixed-archetype planner
(core/presentation_planner_hld_qbr.py) with a pipeline that matches content
to slides by STRUCTURE, not by a pre-enumerated list of named topics:

  1. (done upstream, in app.py) core.content_model_extractor.
     extract_content_model_full() — the FULL document, chunked, no
     predefined categories.
  2. Outline assignment (this module): compact layout_capability_catalog.json
     + the full ContentModel + requested slide count -> which catalog
     slide_ids to use and which content_item ids feed each one.
  3. Content fill (this module, batched): for the picked slides, the real
     slot/table/chart/repeat-group schema + only their assigned content
     items -> actual slide text/tables/charts.
  4. Validation: every slide gets governance-checked (max_chars, no empty
     mandatory slide); failures are dropped rather than blocking the deck.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from core.hld_qbr_catalog import (
    STRUCTURAL_ONLY_SLIDE_IDS,
    compact_catalog_for_outline,
    get_entry,
    load_catalog,
)
from llm.content_model_schemas import ContentModel, Topic
from llm.groq_client import GroqClient
from llm.hld_qbr_generic_schemas import GenericHLDQBRPlan, SlideAssignment
from llm.prompts_hld_qbr_generic import (
    SYSTEM_ROLE_HLD_QBR_FILL,
    SYSTEM_ROLE_HLD_QBR_OUTLINE,
    build_hld_qbr_fill_prompt,
    build_hld_qbr_outline_prompt,
    parse_outline_response,
)
from utils.logging_utils import get_logger
from utils.text_utils import truncate_text

logger = get_logger(__name__)

FILL_BATCH_SIZE = 1  # One slide per LLM call: avoids token competition and ensures all slots are filled


class HLDQBRGenericPlanningError(Exception):
    """Raised only when planning cannot produce ANY usable plan."""


def _build_slot_alias_map(entry: Dict[str, Any]) -> Dict[str, str]:
    """Maps each text-bearing catalog slot_id to a short sequential token
    (slot_1, slot_2, ...). Table and chart slots are excluded here because
    they are filled via table_rows/chart_series rather than slot_values."""
    text_slots = [s for s in entry["slots"] if s["kind"] not in ("table", "chart")]
    return {slot["slot_id"]: f"slot_{i + 1}" for i, slot in enumerate(text_slots)}


def _slim_entry_for_fill(entry: Dict[str, Any], alias_map: Dict[str, str]) -> Dict[str, Any]:
    """Drops shape_id (renderer-only detail) from the catalog entry so the
    content-fill prompt only sees structural constraints. Text slots are
    aliased to slot_1, slot_2... while table and chart schemas are attached
    directly at the slide level."""
    slots = []
    text_slots = [s for s in entry["slots"] if s["kind"] not in ("table", "chart")]
    for slot in text_slots:
        if slot["slot_id"] not in alias_map:
            continue
        slots.append({
            "slot_id": alias_map[slot["slot_id"]],
            "kind": slot["kind"],
            "max_chars": slot.get("max_chars"),
        })

    payload = {
        "slide_id": entry["slide_id"],
        "has_table": entry["has_table"],
        "has_chart": entry["has_chart"],
        "slots": slots,
        "repeat_groups": [
            {
                "group_slot_id": rg["group_slot_id"],
                "max_items": rg["item_count"],
                "item_slots": [
                    {
                        "slot_id": item_slot["slot_id"],
                        "max_chars": item_slot.get("max_chars"),
                    }
                    for item_slot in rg["item_slots"]
                ],
            }
            for rg in entry["repeat_groups"]
        ],
    }

    table_slot = next((s for s in entry["slots"] if s.get("table_schema")), None)
    if table_slot and table_slot.get("table_schema"):
        schema = table_slot["table_schema"]
        payload["table_schema"] = {
            "column_count": schema.get("cols", 4),
            "max_rows": schema.get("rows", 6),
        }

    chart_slot = next((s for s in entry["slots"] if s.get("chart_schema")), None)
    if chart_slot and chart_slot.get("chart_schema"):
        schema = chart_slot["chart_schema"]
        payload["chart_schema"] = {
            "chart_type": schema.get("chart_type"),
            "category_count": schema.get("category_count", 4),
            "series_count": schema.get("series_count", 2),
        }

    return payload


def _run_outline_stage(
    client: GroqClient,
    content_model: ContentModel,
    requested_slide_count: Optional[int],
    exclude_slide_ids: Optional[List[str]] = None,
    unassigned_content_item_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    compact_catalog = compact_catalog_for_outline(exclude_slide_ids=exclude_slide_ids)

    # When unassigned_content_item_ids is provided (e.g. gap-fill pass), prioritize unassigned items
    # to dramatically reduce prompt tokens and avoid token bloat.
    if unassigned_content_item_ids:
        unassigned_set = set(unassigned_content_item_ids)
        slim_items = [i for i in content_model.content_items if i.id in unassigned_set]
        if slim_items:
            slim_topics = [
                Topic(
                    id=t.id if hasattr(t, "id") else t.get("id"),
                    name=t.name if hasattr(t, "name") else t.get("name"),
                    summary=getattr(t, "summary", "") if hasattr(t, "summary") else (t.get("summary") or ""),
                    content_item_ids=[cid for cid in (t.content_item_ids if hasattr(t, "content_item_ids") else t.get("content_item_ids", [])) if cid in unassigned_set],
                )
                for t in content_model.topics
            ]
            slim_topics = [t for t in slim_topics if t.content_item_ids]
            cm_for_outline = ContentModel(content_items=slim_items, topics=slim_topics)
            content_model_json = cm_for_outline.compact_for_outline(max_chars=6000)
        else:
            content_model_json = content_model.compact_for_outline(max_chars=9000)
    else:
        content_model_json = content_model.compact_for_outline(max_chars=9000)

    prompt = build_hld_qbr_outline_prompt(
        compact_catalog=compact_catalog,
        content_model_json=content_model_json,
        always_include_slide_ids=sorted(STRUCTURAL_ONLY_SLIDE_IDS),
        requested_slide_count=requested_slide_count,
        exclude_slide_ids=exclude_slide_ids,
    )
    messages = [
        {"role": "system", "content": SYSTEM_ROLE_HLD_QBR_OUTLINE},
        {"role": "user", "content": prompt},
    ]
    raw = client.chat_complete_json(messages=messages, temperature=0.3, max_tokens=1000)
    return parse_outline_response(raw)


def _resolve_picks(
    outline: Dict[str, Any],
    content_model: ContentModel,
    requested_slide_count: Optional[int],
) -> List[Dict[str, Any]]:
    """Resolves raw outline picks into grounded, deck-ready picks.
    Every slide_id is single-use EXCEPT table/chart-capable ones (catalog
    "has_table"/"has_chart"), which may repeat — one slide per distinct
    tabular/numeric dataset in the source. Each pick gets a unique
    "fill_key" (slide_id, or slide_id__2/__3... for repeats) so the content
    -fill stage never conflates two instances of the same slide_id.
    Picks accumulate across outline/retry/gap-fill attempts (see
    plan_hld_qbr_presentation_generic), so a repeatable slide_id citing the
    EXACT SAME content_item_ids as an already-accepted pick is treated as a
    duplicate (e.g. a same-prompt retry re-proposing the same table) rather
    than a genuinely new dataset, even though repeats are otherwise allowed."""
    catalog_ids = {e["slide_id"] for e in load_catalog()}
    source_ids = content_model.ids()
    seen: set = set()
    seen_content_by_sid: Dict[str, set] = {}
    occurrence_count: Dict[str, int] = {}
    resolved: List[Dict[str, Any]] = []
    for pick in outline["picks"]:
        sid = pick["slide_id"]
        if sid not in catalog_ids or sid in STRUCTURAL_ONLY_SLIDE_IDS:
            continue
        entry = get_entry(sid)
        repeatable = bool(entry and (entry.get("has_table") or entry.get("has_chart")))
        if sid in seen and not repeatable:
            continue
        grounded_ids = [content_id for content_id in pick["content_item_ids"] if content_id in source_ids]
        if not grounded_ids:
            continue
        content_signature = frozenset(grounded_ids)
        if repeatable and content_signature in seen_content_by_sid.get(sid, set()):
            continue
        seen.add(sid)
        seen_content_by_sid.setdefault(sid, set()).add(content_signature)
        occurrence_count[sid] = occurrence_count.get(sid, 0) + 1
        fill_key = sid if occurrence_count[sid] == 1 else f"{sid}__{occurrence_count[sid]}"
        resolved.append({"slide_id": sid, "content_item_ids": grounded_ids, "fill_key": fill_key})

    if requested_slide_count:
        resolved = resolved[:requested_slide_count]

    return resolved


def _run_fill_stage(
    key_manager,
    content_model: ContentModel,
    resolved_picks: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    items_by_id = {item.id: item for item in content_model.content_items}
    fill_payload = []
    reverse_alias_by_fill_key: Dict[str, Dict[str, str]] = {}
    for pick in resolved_picks:
        entry = get_entry(pick["slide_id"])
        if entry is None:
            continue
        assigned = []
        for i in pick["content_item_ids"]:
            if i in items_by_id:
                it = items_by_id[i]
                item_dict = {"id": it.id, "type": it.type, "text": it.text}
                if getattr(it, "attributes", None):
                    item_dict["attributes"] = it.attributes
                assigned.append(item_dict)
        alias_map = _build_slot_alias_map(entry)
        fill_key = pick["fill_key"]
        reverse_alias_by_fill_key[fill_key] = {v: k for k, v in alias_map.items()}
        payload = _slim_entry_for_fill(entry, alias_map)
        # Overridden with the unique fill_key (not the raw catalog slide_id) so a
        # repeated table/chart slide_id's two fill calls never collide in filled_by_id.
        payload["slide_id"] = fill_key
        payload["assigned_content_items"] = assigned
        fill_payload.append(payload)

    def _store_filled(slide_data: Dict[str, Any]) -> None:
        fill_key = slide_data.get("slide_id")
        if not fill_key:
            return
        reverse_map = reverse_alias_by_fill_key.get(fill_key, {})
        slot_values = slide_data.get("slot_values")
        if isinstance(slot_values, dict):
            slide_data["slot_values"] = {
                reverse_map.get(alias, alias): str(value).strip()
                for alias, value in slot_values.items()
                if value is not None and str(value).strip()
            }
        filled_by_id[fill_key] = slide_data


    filled_by_id: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(fill_payload), FILL_BATCH_SIZE):
        batch = fill_payload[start:start + FILL_BATCH_SIZE]
        prompt = build_hld_qbr_fill_prompt(slides_payload=batch)
        messages = [
            {"role": "system", "content": SYSTEM_ROLE_HLD_QBR_FILL},
            {"role": "user", "content": prompt},
        ]
        client = key_manager.get_client()
        try:
            raw = client.chat_complete_json(messages=messages, temperature=0.3, max_tokens=2400)
        except Exception as e:
            logger.warning("Content-fill batch failed (%d slides), skipping batch: %s", len(batch), e)
            continue
        for slide_data in raw.get("slides", []) if isinstance(raw, dict) else []:
            _store_filled(slide_data)

    missing_payload = [
        payload for payload in fill_payload if payload["slide_id"] not in filled_by_id
    ]
    if missing_payload:
        logger.warning("Retrying content fill for %d omitted slide(s).", len(missing_payload))
        for start in range(0, len(missing_payload), FILL_BATCH_SIZE):
            batch = missing_payload[start:start + FILL_BATCH_SIZE]
            prompt = build_hld_qbr_fill_prompt(slides_payload=batch)
            messages = [
                {"role": "system", "content": SYSTEM_ROLE_HLD_QBR_FILL},
                {"role": "user", "content": prompt},
            ]
            try:
                raw = key_manager.get_client().chat_complete_json(
                    messages=messages, temperature=0.2, max_tokens=2400
                )
                for slide_data in raw.get("slides", []) if isinstance(raw, dict) else []:
                    _store_filled(slide_data)
            except Exception as e:
                logger.warning("Content-fill retry failed for %d slide(s): %s", len(batch), e)

    return filled_by_id



def _build_slide_assignment(pick: Dict[str, Any], filled: Optional[Dict[str, Any]]) -> Optional[SlideAssignment]:
    entry = get_entry(pick["slide_id"])
    if entry is None or not filled:
        return None
    has_visible_content = any([
        filled.get("title"),
        filled.get("slot_values"),
        filled.get("repeat_items"),
        filled.get("table_headers"),
        filled.get("table_rows"),
        filled.get("chart_categories"),
        filled.get("chart_series"),
    ])
    # Defensively normalize chart inputs if LLM returned single dict or comma-separated string
    if isinstance(filled.get("chart_series"), dict):
        filled["chart_series"] = [filled["chart_series"]]
    if isinstance(filled.get("chart_categories"), str):
        raw_c = filled["chart_categories"]
        filled["chart_categories"] = [c.strip() for c in raw_c.split(",") if c.strip()] if "," in raw_c else [raw_c.strip()]

    if not has_visible_content:
        return None
    if entry.get("has_chart") and not (filled.get("chart_categories") and filled.get("chart_series")):
        logger.warning(
            "Slide %s is a chart layout but received no chart data; rejecting so gap-fill can recover with an appropriate layout.",
            entry["slide_id"],
        )
        return None
    if entry.get("has_table") and not filled.get("table_rows"):
        logger.warning(
            "Slide %s is a table layout but received no table rows; rejecting so gap-fill can recover with an appropriate layout.",
            entry["slide_id"],
        )
        return None
    try:
        return SlideAssignment(
            slide_id=entry["slide_id"],
            source_slide_index=entry["source_slide_index"],
            title=filled.get("title"),
            slot_values=filled.get("slot_values") or {},
            repeat_items=filled.get("repeat_items") or [],
            table_headers=filled.get("table_headers") or None,
            table_rows=filled.get("table_rows") or None,
            chart_categories=filled.get("chart_categories") or None,
            chart_series=filled.get("chart_series") or None,
            content_item_ids=pick.get("content_item_ids", []),
        )
    except ValidationError as e:
        logger.warning(
            "SlideAssignment validation warning on %s: %s; attempting rescue as text-only slide assignment...",
            entry["slide_id"],
            e,
        )
        try:
            return SlideAssignment(
                slide_id=entry["slide_id"],
                source_slide_index=entry["source_slide_index"],
                title=filled.get("title") or "Overview",
                slot_values={k: str(v) for k, v in (filled.get("slot_values") or {}).items() if v is not None and str(v).strip()},
                repeat_items=filled.get("repeat_items") or [],
                table_headers=None,
                table_rows=None,
                chart_categories=None,
                chart_series=None,
                content_item_ids=pick.get("content_item_ids", []),
            )
        except Exception as e2:
            logger.error("Failed to rescue slide %s: %s", entry["slide_id"], e2)
            return None
def _synthesize_agenda_topics(
    raw_topics: Optional[List[str]],
    content_model: ContentModel,
    slides: List[SlideAssignment],
) -> List[str]:
    """Derives a clean, executive set of 4-6 agenda topics.

    Prevents overflowing the slide canvas and footer when slide counts grow (e.g. 10, 15, 20, 25 slides).
    - If LLM outline provided valid 3-6 topics, cleans and uses them.
    - If deck is small (<= 6 content slides), unique slide titles are used directly.
    - If deck is large (> 6 slides), derives 4-6 thematic pillars from ContentModel topics or
      clusters slide titles, strictly capped at 6 items.
    """
    # 1. Check if LLM supplied good thematic agenda topics
    if raw_topics:
        cleaned: List[str] = []
        seen = set()
        for t in raw_topics:
            s = re.sub(r"^\d+[\.\)]\s*", "", str(t).strip())
            if s and s.lower() not in seen:
                seen.add(s.lower())
                cleaned.append(s)
        if 3 <= len(cleaned) <= 6:
            return cleaned
        elif len(cleaned) > 6:
            return cleaned[:6]

    # Collect unique slide titles
    slide_titles: List[str] = []
    seen_titles = set()
    for s in slides:
        st = (s.title or "").strip()
        if st and st.lower() not in seen_titles:
            seen_titles.add(st.lower())
            slide_titles.append(st)

    # 2. Small decks (<= 6 slides): use slide titles directly
    if len(slide_titles) <= 6:
        return slide_titles

    # 3. Medium/Large decks (> 6 slides): synthesize 4-6 thematic pillars
    # Source A: ContentModel high-level topics
    if content_model and content_model.topics:
        cm_topics: List[str] = []
        cm_seen = set()
        for t in content_model.topics:
            tname = (t.name or "").strip()
            if tname and tname.lower() not in cm_seen:
                cm_seen.add(tname.lower())
                cm_topics.append(tname)
        if 3 <= len(cm_topics) <= 6:
            return cm_topics
        elif len(cm_topics) > 6:
            return cm_topics[:6]

    # Source B: Evenly sampled anchors across the deck for large decks
    n = len(slide_titles)
    indices = [0, n // 4, n // 2, (3 * n) // 4, n - 1]
    sampled: List[str] = []
    sampled_seen = set()
    for idx in indices:
        t = slide_titles[idx]
        if t.lower() not in sampled_seen:
            sampled_seen.add(t.lower())
            sampled.append(t)
    return sampled[:6]


def plan_hld_qbr_presentation_generic(
    client: GroqClient,
    key_manager,
    content_model: ContentModel,
    requested_slide_count: Optional[int] = None,
    presentation_title_hint: str = "",
    facility_name_hint: str = "",
) -> GenericHLDQBRPlan:
    """Full pipeline: outline assignment -> content fill -> typed plan.
    A requested slide count is enforced; incomplete source-grounded plans
    raise instead of emitting blank or silently short decks."""
    if not content_model.content_items:
        raise HLDQBRGenericPlanningError(
            "No content could be extracted from the source document, so no slide can be "
            "source-grounded. This is usually an extraction-stage failure (LLM/API error, "
            "rate limit, or no readable text in the document) rather than the document's "
            "content not fitting the template — check the application logs for a "
            "'Content model extraction failed' or LLM call warning."
        )

    outline = _run_outline_stage(client, content_model, requested_slide_count)
    all_raw_picks: List[Dict[str, Any]] = list(outline.get("picks") or [])
    resolved_picks = _resolve_picks({"picks": all_raw_picks}, content_model, requested_slide_count)
    # Title/facility/date come from the FIRST (full) outline attempt only -- later
    # gap-fill attempts are deliberately narrow (asked for only the missing slides)
    # and would otherwise overwrite these with an empty/irrelevant response.
    outline_meta = outline

    # A requested slide count is a hard contract. Picks accumulate across attempts
    # (never discarded), so each retry can only add slides, never lose ones already
    # found. Attempt 1 retries the SAME full prompt (model variance may do better).
    # Attempt 2 is a narrower "gap-fill" call: only the still-missing count, explicitly
    # excluding already-used slide_ids, so the AI covers NEW topics instead of
    # re-proposing ones that already got picked (and may have been structurally
    # awkward, which is exactly why they weren't grounded the first time).
    gap_fill_attempt = 0
    MAX_GAP_FILL_ATTEMPTS = 2
    while (
        requested_slide_count
        and len(resolved_picks) < requested_slide_count
        and gap_fill_attempt < MAX_GAP_FILL_ATTEMPTS
    ):
        gap_fill_attempt += 1
        gap = requested_slide_count - len(resolved_picks)
        if gap_fill_attempt == 1:
            logger.warning(
                "Outline returned %d raw pick(s) -> %d source-grounded of %d requested; retrying full outline.",
                len(all_raw_picks), len(resolved_picks), requested_slide_count,
            )
            retry_outline = _run_outline_stage(client, content_model, requested_slide_count)
        else:
            used_slide_ids = [p["slide_id"] for p in resolved_picks]
            used_content_ids = {cid for p in resolved_picks for cid in p["content_item_ids"]}
            remaining_cids = [cid for cid in content_model.ids() if cid not in used_content_ids]
            logger.warning(
                "Still %d short of %d requested after retry; running a narrower gap-fill call "
                "for the remaining %d slide(s), excluding %d already-used slide_id(s).",
                gap, requested_slide_count, gap, len(used_slide_ids),
            )
            retry_outline = _run_outline_stage(
                client, content_model, gap,
                exclude_slide_ids=used_slide_ids,
                unassigned_content_item_ids=remaining_cids,
            )
        all_raw_picks.extend(retry_outline.get("picks") or [])
        resolved_picks = _resolve_picks({"picks": all_raw_picks}, content_model, requested_slide_count)
        if not outline_meta.get("presentation_title"):
            outline_meta = retry_outline

    if requested_slide_count and len(resolved_picks) < requested_slide_count:
        used_content_ids = {cid for p in resolved_picks for cid in p["content_item_ids"]}
        remaining_cids = [cid for cid in content_model.ids() if cid not in used_content_ids]
        used_sids = {p["slide_id"] for p in resolved_picks}
        fallback_candidates = [
            e["slide_id"] for e in load_catalog()
            if not e.get("has_chart") and not e.get("has_table") and e["slide_id"] not in STRUCTURAL_ONLY_SLIDE_IDS and e["slide_id"] not in used_sids
        ]
        while len(resolved_picks) < requested_slide_count and remaining_cids and fallback_candidates:
            fallback_sid = fallback_candidates.pop(0)
            batch = remaining_cids[:3]
            remaining_cids = remaining_cids[3:]
            logger.info("Outline fallback: allocating unassigned items %s to flexible layout %s", batch, fallback_sid)
            all_raw_picks.append({"slide_id": fallback_sid, "content_item_ids": batch})
            resolved_picks = _resolve_picks({"picks": all_raw_picks}, content_model, requested_slide_count)

    if not resolved_picks:
        raise HLDQBRGenericPlanningError("No slides could be planned from the extracted content.")

    if requested_slide_count and len(resolved_picks) < requested_slide_count:
        logger.warning(
            "Source document has only enough content for %d slides (requested %d); proceeding with available grounded slides.",
            len(resolved_picks), requested_slide_count,
        )

    filled_by_id = _run_fill_stage(key_manager, content_model, resolved_picks)

    slides: List[SlideAssignment] = []
    successful_picks: List[Dict[str, Any]] = []
    for pick in resolved_picks:
        assignment = _build_slide_assignment(pick, filled_by_id.get(pick["fill_key"]))
        if assignment is not None:
            slides.append(assignment)
            successful_picks.append(pick)

    # A pick can survive the outline stage but still come back empty from content-fill
    # (e.g. the LLM couldn't write real content for it). Run a converging multi-attempt
    # gap-fill loop, excluding unproductive layouts and retrying until the requested count is met.
    post_fill_attempt = 0
    MAX_POST_FILL_ATTEMPTS = 3
    chart_fill_failed = any(
        (get_entry(p["slide_id"]) or {}).get("has_chart") and p["fill_key"] not in {sp["fill_key"] for sp in successful_picks}
        for p in resolved_picks
    )

    while (
        requested_slide_count
        and len(slides) < requested_slide_count
        and post_fill_attempt < MAX_POST_FILL_ATTEMPTS
    ):
        post_fill_attempt += 1
        gap = requested_slide_count - len(slides)
        used_slide_ids = [p["slide_id"] for p in successful_picks]
        # Also exclude failed non-repeatable picks so we don't repeat the exact same unproductive match
        used_slide_ids += [
            p["slide_id"] for p in resolved_picks
            if p["fill_key"] not in {sp["fill_key"] for sp in successful_picks}
        ]
        # If chart layouts failed content fill, the document lacks multi-category chart data:
        # exclude ALL chart layouts so the AI picks from the 14 available text and card layouts.
        if chart_fill_failed:
            used_slide_ids += [e["slide_id"] for e in load_catalog() if e.get("has_chart")]

        used_content_ids = {cid for s in slides for cid in s.content_item_ids}
        remaining_cids = [cid for cid in content_model.ids() if cid not in used_content_ids]
        used_slide_ids = list(set(used_slide_ids))
        logger.warning(
            "Content-fill produced %d of %d requested slides; running gap-fill pass %d for the "
            "remaining %d slide(s) (excluding %d slide_ids).",
            len(slides), requested_slide_count, post_fill_attempt, gap, len(used_slide_ids),
        )
        gap_outline = _run_outline_stage(
            client, content_model, gap,
            exclude_slide_ids=used_slide_ids,
            unassigned_content_item_ids=remaining_cids,
        )
        gap_raw_picks = list(gap_outline.get("picks") or [])
        all_raw_picks.extend(gap_raw_picks)
        gap_resolved = _resolve_picks({"picks": successful_picks + gap_raw_picks}, content_model, requested_slide_count)
        new_picks = [p for p in gap_resolved if p["fill_key"] not in {pk["fill_key"] for pk in successful_picks}]
        if new_picks:
            gap_filled_by_id = _run_fill_stage(key_manager, content_model, new_picks)
            for pick in new_picks:
                assignment = _build_slide_assignment(pick, gap_filled_by_id.get(pick["fill_key"]))
                if assignment is not None:
                    slides.append(assignment)
                    successful_picks.append(pick)
            resolved_picks = successful_picks

    if requested_slide_count and len(slides) < requested_slide_count:
        used_content_ids = {cid for s in slides for cid in s.content_item_ids}
        remaining_content_ids = [cid for cid in content_model.ids() if cid not in used_content_ids]
        used_sids = {s.slide_id for s in slides}
        fallback_candidates = [
            e["slide_id"] for e in load_catalog()
            if not e.get("has_chart") and not e.get("has_table") and e["slide_id"] not in STRUCTURAL_ONLY_SLIDE_IDS and e["slide_id"] not in used_sids
        ]

        while len(slides) < requested_slide_count and remaining_content_ids and fallback_candidates:
            fallback_sid = fallback_candidates.pop(0)
            batch_cids = remaining_content_ids[:3]
            remaining_content_ids = remaining_content_ids[3:]
            fallback_pick = {
                "slide_id": fallback_sid,
                "content_item_ids": batch_cids,
                "fill_key": fallback_sid,
            }
            logger.info("Attempting emergency fallback slide %s with unassigned items %s", fallback_sid, batch_cids)
            fallback_filled = _run_fill_stage(key_manager, content_model, [fallback_pick])
            assignment = _build_slide_assignment(fallback_pick, fallback_filled.get(fallback_sid))
            if assignment is not None:
                slides.append(assignment)
                successful_picks.append(fallback_pick)

    # Deliver graceful presentation instead of crashing if document content is genuinely exhausted
    if requested_slide_count and len(slides) < requested_slide_count:
        logger.warning(
            "Source document has insufficient content for %d requested slides; delivering %d complete, fully-grounded slides.",
            requested_slide_count, len(slides),
        )

    if not slides:
        raise HLDQBRGenericPlanningError("No slides could be planned from the extracted content.")

    raw_agenda_topics = outline_meta.get("agenda_topics") or []
    agenda_topics = _synthesize_agenda_topics(raw_agenda_topics, content_model, slides)

    plan = GenericHLDQBRPlan(
        presentation_title=outline_meta.get("presentation_title") or content_model.content_items[0].text,
        facility_name=outline_meta.get("facility_name") or "",
        date=outline_meta.get("date") or "",
        agenda_topics=agenda_topics,
        slides=slides,
    )
    used_content_ids = {cid for s in slides for cid in s.content_item_ids}
    total_content_ids = set(content_model.ids())
    unused_count = len(total_content_ids - used_content_ids)
    logger.info(
        "Generic HLD QBR plan: %d content slides assigned, %d/%d extracted content item(s) used (%d not included)",
        len(slides), len(used_content_ids), len(total_content_ids), unused_count,
    )
    return plan

