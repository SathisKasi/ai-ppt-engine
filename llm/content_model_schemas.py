"""
llm/content_model_schemas.py — Template-independent intermediate Content Model.

Sits between raw source-document text and any presentation planner. Represents
"what information actually exists in the source" as typed, traceable items —
it knows nothing about slides, layouts, or any specific template.
"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

# Open set of content types the extractor may emit — intentionally not a
# strict Enum so new categories don't require a schema migration.
CONTENT_ITEM_TYPES = (
    "fact", "claim", "key_message", "entity", "person", "organization", "date",
    "metric", "process", "step", "problem", "solution", "benefit", "risk",
    "goal", "outcome", "comparison", "quote", "section",
)


class ContentItem(BaseModel):
    """One atomic piece of information extracted from the source document."""

    id: str = Field(..., description="Stable short id, e.g. 'C001'")
    type: str = Field(..., description="One of CONTENT_ITEM_TYPES (or a close synonym)")
    text: str = Field(..., description="The factual statement, in the source's own terms")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="e.g. {'value': 35, 'unit': '%'}")
    source_reference: str = Field(default="", description="Page/section hint, e.g. 'page 3'")


class ContentRelationship(BaseModel):
    """A directed relationship between two content items, e.g. 'solved_by'."""

    from_id: str
    to_id: str
    type: str


class Topic(BaseModel):
    """A higher-level theme the source document discusses, grouping related
    ContentItems together. Additive to, not a replacement for, atomic fact
    extraction — topics give the outline stage a document-structure view,
    while content_items remain the traceable, citable unit of fact."""

    id: str = Field(..., description="Stable short id, e.g. 'T001'")
    name: str = Field(..., description="Concise topic label, in the source's own terms")
    summary: str = Field(default="", description="1-2 sentence description of what this topic covers")
    content_item_ids: List[str] = Field(
        default_factory=list, description="ids of the content_items that belong to this topic"
    )


class ContentModel(BaseModel):
    """The full extracted representation of a source document."""

    content_items: List[ContentItem] = Field(default_factory=list)
    relationships: List[ContentRelationship] = Field(default_factory=list)
    topics: List[Topic] = Field(default_factory=list)

    def compact_json(self) -> str:
        """Minimal id+type+text+source_reference view for prompt injection (no attributes)."""
        import json
        items = [
            {"id": i.id, "type": i.type, "text": i.text, "source_reference": i.source_reference}
            for i in self.content_items
        ]
        rels = [r.model_dump() for r in self.relationships]
        topics = [t.model_dump() for t in self.topics]
        return json.dumps(
            {"content_items": items, "relationships": rels, "topics": topics},
            ensure_ascii=False, separators=(',', ':'),
        )

    def compact_for_outline(self, max_chars: int = 9000) -> str:
        """Compact, outline-focused view: topics first + atomic items (id, type, trimmed text).
        Omits unused relationships, attributes, source references, and whitespace indentation.
        Guarantees syntactically valid JSON within character limits.
        """
        import json
        from utils.text_utils import truncate_text

        topics = [
            {
                "id": t.id,
                "name": t.name,
                "summary": truncate_text(t.summary, 70) if t.summary else "",
                "content_item_ids": t.content_item_ids,
            }
            for t in self.topics
        ]

        # Normal pass: trim text to 75 chars (sufficient for structural matching)
        items = [
            {
                "id": i.id,
                "type": i.type,
                "text": truncate_text(i.text, 75),
            }
            for i in self.content_items
        ]

        payload = {"topics": topics, "content_items": items}
        result = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        if len(result) <= max_chars:
            return result

        # Second pass: trim text to 50 chars if needed
        items_tight = [
            {
                "id": i.id,
                "type": i.type,
                "text": truncate_text(i.text, 50),
            }
            for i in self.content_items
        ]
        payload = {"topics": topics, "content_items": items_tight}
        result = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        if len(result) <= max_chars:
            return result

        # Third pass: prioritize topic-referenced items
        topic_item_ids = {iid for t in self.topics for iid in t.content_item_ids}
        filtered_items = [it for it in items_tight if it["id"] in topic_item_ids]
        if not filtered_items:
            filtered_items = items_tight[:50]
        payload = {"topics": topics, "content_items": filtered_items}
        return json.dumps(payload, separators=(',', ':'), ensure_ascii=False)

    def ids(self) -> set:
        return {i.id for i in self.content_items}

