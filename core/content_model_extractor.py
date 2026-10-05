"""
core/content_model_extractor.py — Stage 1: template-independent content extraction.

Produces a ContentModel (typed, traceable content items + relationships) from raw
source text. Knows nothing about any presentation template — reusable across all
template pipelines.
"""
from __future__ import annotations

from typing import List

from pydantic import ValidationError

from llm.content_model_schemas import ContentItem, ContentModel, Topic
from llm.groq_client import GroqClient, JSONParseError
from llm.prompts_content_model import (
    SYSTEM_ROLE_CONTENT_EXTRACTOR,
    SYSTEM_ROLE_CONTENT_REDUCER,
    build_content_model_extraction_prompt,
    build_content_model_reduce_prompt,
)
from utils.logging_utils import get_logger
from utils.text_utils import chunk_text, truncate_text

logger = get_logger(__name__)

# Items per reduce call — keeps each batch's prompt/completion comfortably
# under a restrictive Groq org's tokens-per-minute cap (same reasoning as
# FILL_BATCH_SIZE in core/presentation_planner_hld_qbr_generic.py) without
# ever truncating a batch's content out of consideration for deduplication.
REDUCE_BATCH_SIZE = 20


def extract_content_model(
    client: GroqClient,
    source_text: str,
    max_source_chars: int = 4500,
    max_tokens: int = 4096,
) -> ContentModel:
    """Best-effort extraction: on any LLM/parse failure, returns an empty ContentModel
    rather than raising, so the presentation planner can always fall back to reading
    the raw source text directly instead of being blocked by this optional stage.
    """
    truncated_source = truncate_text(source_text, max_source_chars)
    prompt = build_content_model_extraction_prompt(source_content=truncated_source)
    messages = [
        {"role": "system", "content": SYSTEM_ROLE_CONTENT_EXTRACTOR},
        {"role": "user", "content": prompt},
    ]

    try:
        # A chunk's full atomic-fact + topic extraction can easily exceed a
        # small completion budget on dense source text — a response cut off
        # mid-JSON always fails to parse, and the retry loop re-sends a
        # GROWING correction prompt at this SAME max_tokens, so a too-small
        # budget here fails identically on every retry rather than recovering.
        raw_data = client.chat_complete_json(messages=messages, temperature=0.2, max_tokens=max_tokens)
        model = ContentModel.model_validate(raw_data)
    except (JSONParseError, ValidationError) as e:
        logger.warning("Content model extraction failed, continuing without it: %s", e)
        return ContentModel()
    except Exception as e:
        logger.warning("Content model extraction LLM call failed, continuing without it: %s", e)
        return ContentModel()

    logger.info(
        "Content model extracted: %d items, %d relationships, %d topics.",
        len(model.content_items), len(model.relationships), len(model.topics),
    )
    return model


# ---------------------------------------------------------------------------
# Map-reduce extraction — extracts from the WHOLE document (chunked, no single
# truncation cutoff) instead of one call over a truncated excerpt. This is the
# "no predefined categories, extract everything" stage: each chunk is analyzed
# independently with the exact same open-ended extract_content_model() above,
# then merged and deduped.
# ---------------------------------------------------------------------------

def _renumber_and_merge(models: List[ContentModel]) -> ContentModel:
    """Concatenates per-chunk ContentModels into one, renumbering ids
    sequentially (C001, C002, ... and T001, T002, ...) and remapping
    relationship endpoints and topic content_item_ids."""
    merged_items: List[ContentItem] = []
    merged_relationships = []
    merged_topics: List[Topic] = []
    next_num = 1
    next_topic_num = 1

    for model in models:
        id_map = {}
        for item in model.content_items:
            new_id = f"C{next_num:03d}"
            next_num += 1
            id_map[item.id] = new_id
            merged_items.append(item.model_copy(update={"id": new_id}))
        for rel in model.relationships:
            if rel.from_id in id_map and rel.to_id in id_map:
                merged_relationships.append(
                    rel.model_copy(update={"from_id": id_map[rel.from_id], "to_id": id_map[rel.to_id]})
                )
        for topic in model.topics:
            new_topic_id = f"T{next_topic_num:03d}"
            next_topic_num += 1
            remapped_item_ids = [id_map[i] for i in topic.content_item_ids if i in id_map]
            merged_topics.append(topic.model_copy(update={"id": new_topic_id, "content_item_ids": remapped_item_ids}))

    return ContentModel(content_items=merged_items, relationships=merged_relationships, topics=merged_topics)


def _split_content_model_for_reduce(model: ContentModel, batch_size: int) -> List[ContentModel]:
    """Splits a large ContentModel into independently-reducible batches by
    content_item id range. Each batch keeps only the relationships/topics
    fully contained within it (an item pair/topic spanning two batches is
    dropped from that batch's view) — the same cross-batch limitation the
    fill stage's batching already accepts. ids are already globally unique
    (assigned once in _renumber_and_merge), so batches never collide and
    don't need re-renumbering after reduce."""
    items = model.content_items
    if len(items) <= batch_size:
        return [model]
    batches = []
    for start in range(0, len(items), batch_size):
        batch_items = items[start:start + batch_size]
        batch_ids = {i.id for i in batch_items}
        batch_rels = [r for r in model.relationships if r.from_id in batch_ids and r.to_id in batch_ids]
        batch_topics = []
        for topic in model.topics:
            kept_ids = [i for i in topic.content_item_ids if i in batch_ids]
            if kept_ids:
                batch_topics.append(topic.model_copy(update={"content_item_ids": kept_ids}))
        batches.append(ContentModel(content_items=batch_items, relationships=batch_rels, topics=batch_topics))
    return batches


def _reduce_one_batch(client: GroqClient, batch: ContentModel) -> ContentModel:
    """One LLM call to dedupe/merge items within a single batch. Falls back
    to the un-deduped batch on any failure — a duplicate item is a minor
    downstream inefficiency, never worth blocking the pipeline."""
    # Defensive backstop only: a REDUCE_BATCH_SIZE-sized batch's JSON is
    # normally well under this, but very long item texts could still push
    # one batch over a restrictive Groq org's tokens-per-minute cap.
    batch_json = truncate_text(batch.compact_json(), max_chars=10000)
    prompt = build_content_model_reduce_prompt(merged_content_model_json=batch_json)
    messages = [
        {"role": "system", "content": SYSTEM_ROLE_CONTENT_REDUCER},
        {"role": "user", "content": prompt},
    ]
    try:
        raw_data = client.chat_complete_json(messages=messages, temperature=0.1, max_tokens=4096)
        return ContentModel.model_validate(raw_data)
    except (JSONParseError, ValidationError) as e:
        logger.warning("Content model reduce batch failed, keeping un-deduped batch: %s", e)
        return batch
    except Exception as e:
        logger.warning("Content model reduce batch LLM call failed, keeping un-deduped batch: %s", e)
        return batch


def _reduce_content_model(key_manager, merged: ContentModel) -> ContentModel:
    """Dedupes a (possibly large) merged ContentModel via one or more
    bounded reduce calls — splitting into batches instead of truncating
    means every item still gets a chance at deduplication, just across
    multiple calls rather than risking one oversized request."""
    batches = _split_content_model_for_reduce(merged, REDUCE_BATCH_SIZE)

    reduced_items: List[ContentItem] = []
    reduced_relationships = []
    reduced_topics: List[Topic] = []
    for i, batch in enumerate(batches):
        client = key_manager.get_client(chunk_index=i)
        reduced_batch = _reduce_one_batch(client, batch)
        reduced_items.extend(reduced_batch.content_items)
        reduced_relationships.extend(reduced_batch.relationships)
        reduced_topics.extend(reduced_batch.topics)

    reduced = ContentModel(content_items=reduced_items, relationships=reduced_relationships, topics=reduced_topics)
    logger.info(
        "Content model reduced (%d batch(es)): %d -> %d items, %d -> %d topics.",
        len(batches), len(merged.content_items), len(reduced.content_items),
        len(merged.topics), len(reduced.topics),
    )
    return reduced


def extract_content_model_full(
    key_manager,
    source_text: str,
    chunk_size: int = 6000,
    overlap: int = 300,
) -> ContentModel:
    """Map-reduce variant of extract_content_model() that covers the WHOLE
    source_text instead of a single truncated excerpt. Splits into overlapping
    chunks (utils.text_utils.chunk_text), extracts each chunk independently
    (round-robin API keys, same as core/chunk_analyzer.py's pattern), then
    merges and dedupes. Falls back gracefully — a failed chunk just yields
    fewer content items, it never raises.
    """
    chunks = chunk_text(source_text, chunk_size=chunk_size, overlap=overlap)
    logger.info("Content model map-reduce: %d chunk(s) from %d chars", len(chunks), len(source_text))

    per_chunk_models: List[ContentModel] = []
    for i, chunk in enumerate(chunks):
        client = key_manager.get_client(chunk_index=i)
        model = extract_content_model(client, chunk, max_source_chars=len(chunk) + 500)
        per_chunk_models.append(model)

    merged = _renumber_and_merge(per_chunk_models)

    if len(chunks) <= 1:
        return merged

    return _reduce_content_model(key_manager, merged)
