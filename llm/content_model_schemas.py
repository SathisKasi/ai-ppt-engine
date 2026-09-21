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


class ContentModel(BaseModel):
    """The full extracted representation of a source document."""

    content_items: List[ContentItem] = Field(default_factory=list)
    relationships: List[ContentRelationship] = Field(default_factory=list)

    def compact_json(self) -> str:
        """Minimal id+type+text+source_reference view for prompt injection (no attributes)."""
        import json
        items = [
            {"id": i.id, "type": i.type, "text": i.text, "source_reference": i.source_reference}
            for i in self.content_items
        ]
        rels = [r.model_dump() for r in self.relationships]
        return json.dumps({"content_items": items, "relationships": rels}, ensure_ascii=False, indent=2)

    def ids(self) -> set:
        return {i.id for i in self.content_items}
