"""
core/template_registry.py
Central registry mapping template IDs to builder classes.
Add new templates here without touching any other file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from utils.logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Registry definition
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, Dict[str, Any]] = {
    "dark_navy": {
        "id":          "dark_navy",
        "name":        "Dark Navy (Default)",
        "description": "Sleek dark navy & purple professional theme",
        "icon":        "🌑",
    },
    # "techm": {
    #     "id":          "techm",
    #     "name":        "TechM Corporate",
    #     "description": "Tech Mahindra corporate branding template",
    #     "icon":        "🏢",
    # },
    "white_blue": {
        "id":          "white_blue",
        "name":        "White & Blue Professional",
        "description": "Clean white + blue corporate design",
        "icon":        "☁️",
    },
    "techm_v3": {
        "id":          "techm_v3",
        "name":        "TechM Dynamic V3 (Freeform Layouts)",
        "description": "Tech Mahindra 3-slide master: dynamic LLM layouts & content enrichment",
        "icon":        "✨",
    },
    "template1": {
        "id":          "template1",
        "name":        "Template-1: AI Transformation Weekly",
        "description": "Warm earth-tone palette (espresso/amber/sand) — 5-slide master with ACTION_TABLE & dynamic LLM layouts",
        "icon":        "🟤",
    },
}


def list_templates() -> List[Dict[str, str]]:
    """Return list of template metadata dicts (id, name, description, icon)."""
    return list(_REGISTRY.values())


def get_builder(template_id: str, layout_manager=None):
    """
    Instantiate and return the appropriate builder for the given template_id.

    Args:
        template_id:    One of 'dark_navy', 'techm', 'white_blue', 'techm_v3'
        layout_manager: Required only for dark_navy (existing LayoutManager instance)

    Returns:
        Builder instance with a .build(plan) -> bytes method
    """
    tid = template_id.lower().strip()

    if tid == "template1":
        from core.builders.template1_builder import Template1Builder
        return Template1Builder(template_path=config.TEMPLATE1_FILE)

    if tid == "techm_v3":
        from core.builders.techm_v3_builder import TechMV3Builder
        return TechMV3Builder(template_path=config.TECHM_V3_TEMPLATE_FILE)

    if tid == "techm":
        from core.builders.techm_builder import TechMBuilder
        return TechMBuilder(template_path=config.TECHM_TEMPLATE_FILE)

    if tid == "white_blue":
        from core.builders.white_blue_builder import WhiteBlueBuilder
        return WhiteBlueBuilder()

    if tid == "dark_navy" or tid not in _REGISTRY:
        if tid not in _REGISTRY:
            logger.warning("Unknown template_id '%s', falling back to dark_navy", template_id)
        from core.builders.dark_navy_builder import DarkNavyBuilder
        if layout_manager is None:
            from core.layout_manager import LayoutManager
            layout_manager = LayoutManager(
                template_path=config.TEMPLATE_FILE,
                metadata_path=config.LAYOUT_METADATA_FILE,
            )
        return DarkNavyBuilder(layout_manager)

    # Should never reach here due to fallback above
    from core.builders.dark_navy_builder import DarkNavyBuilder
    return DarkNavyBuilder(layout_manager)
