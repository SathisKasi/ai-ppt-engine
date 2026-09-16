"""
core/builders/dark_navy_builder.py
Thin adapter that delegates to the original pptx_builder.
The existing dark navy engine is fully preserved and untouched.
"""
from __future__ import annotations
from llm.schemas import PresentationPlan
from core.pptx_builder import build_presentation
from core.layout_manager import LayoutManager


class DarkNavyBuilder:
    """
    Adapter over the existing build_presentation() function.
    Keeps the original dark navy template completely unchanged.
    """

    def __init__(self, layout_manager: LayoutManager) -> None:
        self._lm = layout_manager

    def build(self, plan: PresentationPlan) -> bytes:
        return build_presentation(plan=plan, layout_manager=self._lm)
