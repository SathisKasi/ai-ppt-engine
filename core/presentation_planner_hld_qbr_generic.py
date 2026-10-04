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

from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from core.hld_qbr_catalog import (
    STRUCTURAL_ONLY_SLIDE_IDS,
    compact_catalog_for_outline,
    get_entry,
    load_catalog,
)
from llm.content_model_schemas import ContentModel
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

logger = get_logger(__name__)

FILL_BATCH_SIZE = 7


class HLDQBRGenericPlanningError(Exception):
    """Raised only when planning cannot produce ANY usable plan."""


def _slim_entry_for_fill(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Drops shape_id (renderer-only detail) from the catalog entry so the
    content-fill prompt only sees structural constraints. Template sample
    wording is deliberately excluded: it is never source content."""
    slots = []
    for slot in entry["slots"]:
        slim_slot = {
            "slot_id": slot["slot_id"],
            "kind": slot["kind"],
            "max_chars": slot.get("max_chars"),
        }
        if slot.get("table_schema"):
            schema = slot["table_schema"]
            slim_slot["table_schema"] = {
                "column_count": schema["cols"],
                "row_count": schema["rows"],
            }
        if slot.get("chart_schema"):
            schema = slot["chart_schema"]
            slim_slot["chart_schema"] = {
                "chart_type": schema.get("chart_type"),
                "category_count": schema["category_count"],
                "series_count": schema["series_count"],
            }
        slots.append(slim_slot)
    return {
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


def _run_outline_stage(
    client: GroqClient,
    content_model: ContentModel,
    requested_slide_count: Optional[int],
) -> Dict[str, Any]:
    compact_catalog = compact_catalog_for_outline()
    prompt = build_hld_qbr_outline_prompt(
        compact_catalog=compact_catalog,
        content_model_json=content_model.compact_json(),
        always_include_slide_ids=sorted(STRUCTURAL_ONLY_SLIDE_IDS),
        requested_slide_count=requested_slide_count,
    )
    messages = [
        {"role": "system", "content": SYSTEM_ROLE_HLD_QBR_OUTLINE},
        {"role": "user", "content": prompt},
    ]
    raw = client.chat_complete_json(messages=messages, temperature=0.3, max_tokens=2500)
    return parse_outline_response(raw)


def _resolve_picks(
    outline: Dict[str, Any],
    content_model: ContentModel,
    requested_slide_count: Optional[int],
) -> List[Dict[str, Any]]:
    catalog_ids = {e["slide_id"] for e in load_catalog()}
    source_ids = content_model.ids()
    seen: set = set()
    resolved: List[Dict[str, Any]] = []
    for pick in outline["picks"]:
        sid = pick["slide_id"]
        if sid not in catalog_ids or sid in STRUCTURAL_ONLY_SLIDE_IDS or sid in seen:
            continue
        grounded_ids = [content_id for content_id in pick["content_item_ids"] if content_id in source_ids]
        if not grounded_ids:
            continue
        seen.add(sid)
        resolved.append({"slide_id": sid, "content_item_ids": grounded_ids})

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
    for pick in resolved_picks:
        entry = get_entry(pick["slide_id"])
        if entry is None:
            continue
        assigned = [
            items_by_id[i].model_dump() for i in pick["content_item_ids"] if i in items_by_id
        ]
        payload = _slim_entry_for_fill(entry)
        payload["assigned_content_items"] = assigned
        fill_payload.append(payload)

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
            raw = client.chat_complete_json(messages=messages, temperature=0.3, max_tokens=3800)
        except Exception as e:
            logger.warning("Content-fill batch failed (%d slides), skipping batch: %s", len(batch), e)
            continue
        for slide_data in raw.get("slides", []) if isinstance(raw, dict) else []:
            sid = slide_data.get("slide_id")
            if sid:
                filled_by_id[sid] = slide_data

    missing_payload = [
        payload for payload in fill_payload if payload["slide_id"] not in filled_by_id
    ]
    if missing_payload:
        logger.warning("Retrying content fill for %d omitted slide(s).", len(missing_payload))
        prompt = build_hld_qbr_fill_prompt(slides_payload=missing_payload)
        messages = [
            {"role": "system", "content": SYSTEM_ROLE_HLD_QBR_FILL},
            {"role": "user", "content": prompt},
        ]
        try:
            raw = key_manager.get_client().chat_complete_json(
                messages=messages, temperature=0.2, max_tokens=3800
            )
            for slide_data in raw.get("slides", []) if isinstance(raw, dict) else []:
                sid = slide_data.get("slide_id")
                if sid:
                    filled_by_id[sid] = slide_data
        except Exception as e:
            logger.warning("Content-fill retry failed for %d slide(s): %s", len(missing_payload), e)

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
    if not has_visible_content:
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
        logger.warning("Dropping slide %s: schema validation failed: %s", entry["slide_id"], e)
        return None


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
    outline = _run_outline_stage(client, content_model, requested_slide_count)
    resolved_picks = _resolve_picks(outline, content_model, requested_slide_count)

    # A requested slide count is a hard contract. Retry once with the same
    # structural-only prompt before failing rather than emitting sparse slides.
    if requested_slide_count and len(resolved_picks) < requested_slide_count:
        logger.warning(
            "Outline returned %d of %d requested source-backed slides; retrying.",
            len(resolved_picks), requested_slide_count,
        )
        outline = _run_outline_stage(client, content_model, requested_slide_count)
        resolved_picks = _resolve_picks(outline, content_model, requested_slide_count)
    if requested_slide_count and len(resolved_picks) < requested_slide_count:
        raise HLDQBRGenericPlanningError(
            f"The document supports only {len(resolved_picks)} source-backed layout assignments; "
            f"{requested_slide_count} were requested."
        )

    filled_by_id = _run_fill_stage(key_manager, content_model, resolved_picks)

    slides: List[SlideAssignment] = []
    for pick in resolved_picks:
        assignment = _build_slide_assignment(pick, filled_by_id.get(pick["slide_id"]))
        if assignment is not None:
            slides.append(assignment)

    if requested_slide_count and len(slides) < requested_slide_count:
        raise HLDQBRGenericPlanningError(
            f"Only {len(slides)} of {requested_slide_count} requested slides received source-backed content."
        )
    if not slides:
        raise HLDQBRGenericPlanningError("No slides could be planned from the extracted content.")

    plan = GenericHLDQBRPlan(
        presentation_title=outline.get("presentation_title") or content_model.content_items[0].text,
        facility_name=outline.get("facility_name") or "",
        date=outline.get("date") or "",
        slides=slides,
    )
    logger.info("Generic HLD QBR plan: %d content slides assigned", len(slides))
    return plan
