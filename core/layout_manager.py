"""
core/layout_manager.py — Layout registry and template management.

Responsibilities:
- Load layout_metadata.json to understand all available layouts.
- Auto-generate the presentation_template.pptx if it doesn't exist.
- Provide the correct slide index for a given layout_type.
- Provide metadata (placeholder names, descriptions) for each layout.
- Implement safe fallback when an unknown layout is requested.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logging_utils import get_logger

logger = get_logger(__name__)


class LayoutManagerError(Exception):
    """Raised on unrecoverable layout/template errors."""


class LayoutManager:
    """
    Central registry for PowerPoint layout types and template management.

    Usage:
        manager = LayoutManager(template_path, metadata_path)
        idx = manager.get_layout_index("STATISTICS")   # → 9
        meta = manager.get_layout_metadata("STATISTICS")
    """

    def __init__(self, template_path: Path, metadata_path: Path) -> None:
        self.template_path = template_path
        self.metadata_path = metadata_path
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._layout_name_to_id: Dict[str, str] = {}

        self._load_metadata()
        self._ensure_template()

    # ------------------------------------------------------------------
    # Metadata loading
    # ------------------------------------------------------------------

    def _load_metadata(self) -> None:
        """Load layout_metadata.json and build lookup tables."""
        if not self.metadata_path.exists():
            raise LayoutManagerError(
                f"Layout metadata file not found: {self.metadata_path}"
            )

        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            raise LayoutManagerError(
                f"Failed to load layout metadata: {e}"
            ) from e

        for layout in data.get("layouts", []):
            layout_id = layout.get("layout_id", "").upper()
            if layout_id:
                self._metadata[layout_id] = layout
                # Also map by layout_name for reverse lookup
                name = layout.get("layout_name", "")
                if name:
                    self._layout_name_to_id[name.upper()] = layout_id

        logger.info("Loaded %d layout definitions", len(self._metadata))

    # ------------------------------------------------------------------
    # Template management
    # ------------------------------------------------------------------

    def _ensure_template(self) -> None:
        """Auto-generate the template if it doesn't exist."""
        if self.template_path.exists():
            logger.debug("Template found: %s", self.template_path)
            return

        logger.info(
            "Template not found at %s — generating automatically...",
            self.template_path,
        )
        try:
            # Import and run the template creator
            import sys
            templates_dir = self.template_path.parent
            if str(templates_dir) not in sys.path:
                sys.path.insert(0, str(templates_dir))

            from templates.create_template import create_template
            create_template(self.template_path)
            logger.info("Template generated successfully: %s", self.template_path)
        except Exception as e:
            raise LayoutManagerError(
                f"Failed to auto-generate template: {e}. "
                "Run: python templates/create_template.py"
            ) from e

    def load_template_presentation(self):
        """Return a loaded python-pptx Presentation from the template file."""
        from pptx import Presentation
        if not self.template_path.exists():
            self._ensure_template()
        return Presentation(str(self.template_path))

    # ------------------------------------------------------------------
    # Layout resolution
    # ------------------------------------------------------------------

    @property
    def available_layouts(self) -> List[str]:
        """List of all available layout IDs."""
        return sorted(self._metadata.keys())

    def is_valid_layout(self, layout_type: str) -> bool:
        """Return True if the layout_type is registered."""
        return layout_type.upper().strip() in self._metadata

    def get_layout_index(self, layout_type: str, fallback: str = "TITLE_AND_CONTENT") -> int:
        """
        Return the slide index (0-based) for a given layout_type.
        Falls back to TITLE_AND_CONTENT if the layout is not found.
        """
        lt = layout_type.upper().strip()
        if lt not in self._metadata:
            logger.warning(
                "Unknown layout '%s' — falling back to '%s'", layout_type, fallback
            )
            lt = fallback.upper()

        meta = self._metadata.get(lt, {})
        return int(meta.get("slide_layout_index", 1))

    def get_layout_metadata(self, layout_type: str) -> Dict[str, Any]:
        """
        Return the full metadata dict for a layout type.
        Returns TITLE_AND_CONTENT metadata as fallback.
        """
        lt = layout_type.upper().strip()
        if lt in self._metadata:
            return self._metadata[lt]
        logger.warning("Layout metadata not found for '%s', using fallback", layout_type)
        return self._metadata.get("TITLE_AND_CONTENT", {})

    def get_placeholder_mapping(self, layout_type: str) -> Dict[str, str]:
        """Return the placeholder name → role mapping for a layout."""
        meta = self.get_layout_metadata(layout_type)
        return meta.get("placeholders", {})

    def normalise_layout_type(
        self, layout_type: str, fallback: str = "TITLE_AND_CONTENT"
    ) -> str:
        """
        Normalise an LLM-provided layout type string.
        Handles common variations and aliases.
        """
        lt = layout_type.upper().strip()

        # Direct match
        if lt in self._metadata:
            return lt

        # Common aliases
        aliases: Dict[str, str] = {
            "TITLE_SLIDE": "TITLE",
            "COVER": "TITLE",
            "OPENING": "TITLE",
            "BULLETS": "TITLE_AND_CONTENT",
            "BULLET_POINTS": "TITLE_AND_CONTENT",
            "CONTENT": "TITLE_AND_CONTENT",
            "GENERAL": "TITLE_AND_CONTENT",
            "DEFAULT": "TITLE_AND_CONTENT",
            "SPLIT": "TWO_COLUMN",
            "COLUMNS": "TWO_COLUMN",
            "HEADER": "SECTION_HEADER",
            "DIVIDER": "SECTION_HEADER",
            "CHAPTER": "SECTION_HEADER",
            "STEPS": "PROCESS",
            "WORKFLOW": "PROCESS",
            "FLOWCHART": "PROCESS",
            "ROADMAP": "TIMELINE",
            "MILESTONES": "TIMELINE",
            "DATES": "TIMELINE",
            "METRICS": "STATISTICS",
            "KPIS": "STATISTICS",
            "NUMBERS": "STATISTICS",
            "DATA": "STATISTICS",
            "SYSTEM": "ARCHITECTURE",
            "TECH_STACK": "ARCHITECTURE",
            "LAYERS": "ARCHITECTURE",
            "VERSUS": "COMPARISON",
            "COMPARE": "COMPARISON",
            "PRO_CON": "COMPARISON",
            "SUMMARY": "CONCLUSION",
            "CLOSING": "CONCLUSION",
            "TAKEAWAYS": "CONCLUSION",
            "IMAGE": "IMAGE_TEXT",
            "VISUAL": "IMAGE_TEXT",
        }

        if lt in aliases:
            resolved = aliases[lt]
            logger.debug("Layout alias '%s' → '%s'", layout_type, resolved)
            return resolved

        logger.warning(
            "Could not resolve layout '%s', using fallback '%s'", layout_type, fallback
        )
        return fallback
