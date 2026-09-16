"""
core/chunk_analyzer.py — Per-chunk LLM analysis with in-memory cache.

KEY DESIGN:
  - AnalysisCache stores all ChunkAnalysis results + rolling context summary
  - Each chunk analysis receives the accumulated context of previous sections
  - Different API keys used per chunk via KeyManager (round-robin)
  - Every LLM response is saved to logs/llm/<run_id>/section_XXX.json
  - document_structure.json is saved before any LLM call begins

ROLLING CONTEXT:
  After each chunk is analyzed, a brief summary is appended to an
  in-memory context string. This context is passed to every subsequent
  chunk analysis so the LLM understands document flow:

    "Section 1 (Introduction): Overview of supply chain management basics.
     Section 2 (Key Components): Covers procurement, manufacturing, inventory.
     Section 3 (Procurement): Detailed analysis of supplier management..."
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from llm.schemas import ChunkAnalysis, ContentAnalysis, DocumentStructureLog, DocumentSectionLog
from core.document_structure import DocumentSection, SemanticChunk, count_sections
from llm.prompts import CHUNK_ANALYSIS_PROMPT, SYSTEM_ROLE_CHUNK_ANALYST
from llm.key_manager import KeyManager
from utils.logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# In-memory analysis cache
# ---------------------------------------------------------------------------

class AnalysisCache:
    """
    Thread-safe in-memory store for:
      - Per-chunk ChunkAnalysis results (keyed by chunk_id)
      - Rolling context summary (passed to each subsequent LLM call)
      - The original section tree (for consolidation reference)
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._analyses: Dict[str, ChunkAnalysis] = {}
        self._context_lines: List[str] = []  # one line per analyzed section
        self._lock = threading.Lock()

    # ── Storage ─────────────────────────────────────────────────────────

    def store(self, chunk_id: str, analysis: ChunkAnalysis) -> None:
        with self._lock:
            self._analyses[chunk_id] = analysis
            # Append a brief context line for this section
            path_str = " → ".join(analysis.section_path) if analysis.section_path else analysis.heading
            summary_short = analysis.summary[:120] + "..." if len(analysis.summary) > 120 else analysis.summary
            self._context_lines.append(f"[{path_str}]: {summary_short}")
            logger.debug("Cache stored: %s (%d total)", chunk_id, len(self._analyses))

    def get(self, chunk_id: str) -> Optional[ChunkAnalysis]:
        with self._lock:
            return self._analyses.get(chunk_id)

    def get_all(self) -> List[ChunkAnalysis]:
        with self._lock:
            return list(self._analyses.values())

    # ── Context ──────────────────────────────────────────────────────────

    def get_context_summary(self) -> str:
        """Return accumulated context to pass to next LLM call."""
        with self._lock:
            if not self._context_lines:
                return "No sections analyzed yet."
            return "\n".join(self._context_lines)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._analyses)


# ---------------------------------------------------------------------------
# JSON log helpers
# ---------------------------------------------------------------------------

def _save_json(path: Path, data: Any) -> None:
    """Save data as pretty-printed JSON. Silent on failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            if hasattr(data, "model_dump"):
                json.dump(data.model_dump(), f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Could not save JSON log %s: %s", path, e)


def save_document_structure_log(
    root: DocumentSection,
    chunks: List[SemanticChunk],
    detection_method: str,
    document_title: str,
    logs_dir: Path,
    run_id: str,
) -> None:
    """Save document_structure.json before any LLM calls."""

    def _section_to_log(sec: DocumentSection) -> DocumentSectionLog:
        return DocumentSectionLog(
            heading=sec.heading if sec.level > 0 else "(root)",
            level=sec.level,
            subsections=[_section_to_log(s) for s in sec.subsections],
        )

    h1, h2plus = count_sections(root)
    log = DocumentStructureLog(
        document_title=document_title,
        detection_method=detection_method,
        total_sections=h1 + h2plus,
        total_chunks=len(chunks),
        sections=[_section_to_log(s) for s in root.subsections],
    )
    out_path = logs_dir / run_id / "document_structure.json"
    _save_json(out_path, log)
    logger.info("Saved document_structure.json (%d sections, %d chunks)", h1 + h2plus, len(chunks))


# ---------------------------------------------------------------------------
# Per-chunk LLM analysis
# ---------------------------------------------------------------------------

def _build_chunk_prompt(
    chunk: SemanticChunk,
    document_title: str,
    accumulated_context: str,
) -> str:
    """Fill in the CHUNK_ANALYSIS_PROMPT template for one chunk."""
    parent_heading_json = (
        json.dumps(chunk.parent_heading) if chunk.parent_heading else "null"
    )
    section_path_json = json.dumps(chunk.section_path)

    path_display = "\n".join(
        f"{'  ' * i}→ {part}" for i, part in enumerate(chunk.section_path)
    ) if chunk.section_path else "(top-level)"

    parent_info = (
        f"PARENT SECTION: {chunk.parent_heading}"
        if chunk.parent_heading
        else ""
    )

    # Truncate very long content to stay within context window
    content = chunk.content
    if len(content) > 7000:
        content = content[:7000] + "\n\n[... content truncated for length ...]"

    return CHUNK_ANALYSIS_PROMPT.format(
        document_title=document_title,
        section_path=path_display,
        heading=chunk.heading,
        level=chunk.level,
        parent_info=parent_info,
        accumulated_context=accumulated_context[:2000] if accumulated_context else "None",
        content=content,
        chunk_id=chunk.chunk_id,
        parent_heading_json=parent_heading_json,
        section_path_json=section_path_json,
    )


def _parse_chunk_response(raw: Dict, chunk: SemanticChunk) -> ChunkAnalysis:
    """Parse LLM JSON response into ChunkAnalysis, with fallbacks."""
    try:
        return ChunkAnalysis(**raw)
    except Exception as e:
        logger.warning("ChunkAnalysis validation failed for %s: %s — using fallback", chunk.chunk_id, e)
        return ChunkAnalysis(
            chunk_id=chunk.chunk_id,
            heading=chunk.heading,
            level=chunk.level,
            parent_heading=chunk.parent_heading,
            section_path=chunk.section_path,
            summary=raw.get("summary", f"Analysis of {chunk.heading}"),
            key_points=raw.get("key_points", []),
            facts=raw.get("facts", []),
            statistics=raw.get("statistics", []),
            processes=raw.get("processes", []),
            comparisons=raw.get("comparisons", []),
            dates=raw.get("dates", []),
            examples=raw.get("examples", []),
            relationships=raw.get("relationships", []),
            potential_visuals=raw.get("potential_visuals", []),
            content_types=raw.get("content_types", ["TITLE_AND_CONTENT"]),
            importance=raw.get("importance", "medium"),
        )


def analyze_chunk(
    chunk: SemanticChunk,
    client,  # GroqClient
    document_title: str,
    accumulated_context: str,
    logs_dir: Path,
    run_id: str,
) -> ChunkAnalysis:
    """
    Run LLM analysis on a single semantic chunk.
    Saves the result to logs/llm/<run_id>/section_XXX.json.
    """
    from llm.groq_client import JSONParseError

    prompt = _build_chunk_prompt(chunk, document_title, accumulated_context)
    messages = [
        {"role": "system", "content": SYSTEM_ROLE_CHUNK_ANALYST},
        {"role": "user", "content": prompt},
    ]

    logger.info("Analyzing chunk: %s [%s]", chunk.chunk_id, chunk.heading[:50])

    try:
        raw = client.chat_complete_json(
            messages=messages,
            temperature=0.2,
            max_tokens=2048,
        )
        analysis = _parse_chunk_response(raw, chunk)
    except JSONParseError as e:
        logger.warning("JSON parse failed for %s: %s — using minimal analysis", chunk.chunk_id, e)
        analysis = ChunkAnalysis(
            chunk_id=chunk.chunk_id,
            heading=chunk.heading,
            level=chunk.level,
            parent_heading=chunk.parent_heading,
            section_path=chunk.section_path,
            summary=f"Section: {chunk.heading}",
            key_points=[chunk.content[:200]] if chunk.content else [],
            content_types=["TITLE_AND_CONTENT"],
            importance="medium",
        )
    except Exception as e:
        logger.error("LLM call failed for chunk %s: %s", chunk.chunk_id, e)
        raise

    # Save to JSON log
    log_path = logs_dir / run_id / f"{chunk.chunk_id}.json"
    _save_json(log_path, analysis)

    return analysis


# ---------------------------------------------------------------------------
# Batch analysis of all chunks
# ---------------------------------------------------------------------------

def analyze_all_chunks(
    chunks: List[SemanticChunk],
    key_manager: KeyManager,
    document_title: str,
    logs_dir: Path,
    run_id: str,
    max_tokens_per_chunk: int = 2048,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> tuple[List[ChunkAnalysis], AnalysisCache]:
    """
    Analyze all semantic chunks sequentially, passing rolling context.

    Args:
        chunks:           Ordered list of SemanticChunk to analyze.
        key_manager:      Provides the client for each chunk (round-robin key).
        document_title:   Document title for prompt context.
        logs_dir:         Root logs directory.
        run_id:           Unique run identifier.
        max_tokens_per_chunk: Per-request token budget.
        progress_callback: Called with (heading, current_index, total) after each chunk.

    Returns:
        (ordered_analyses, cache)
    """
    cache = AnalysisCache(run_id)
    analyses: List[ChunkAnalysis] = []

    total = len(chunks)
    logger.info("Starting batch analysis: %d chunks, %d API keys", total, key_manager.key_count)

    for i, chunk in enumerate(chunks):
        # Get accumulated context from previous sections
        accumulated_context = cache.get_context_summary()

        # Assign API key round-robin by chunk index
        client = key_manager.get_client(chunk_index=i, max_tokens=max_tokens_per_chunk)

        try:
            analysis = analyze_chunk(
                chunk=chunk,
                client=client,
                document_title=document_title,
                accumulated_context=accumulated_context,
                logs_dir=logs_dir,
                run_id=run_id,
            )
        except Exception as e:
            logger.error("Chunk %s failed: %s — inserting empty analysis", chunk.chunk_id, e)
            analysis = ChunkAnalysis(
                chunk_id=chunk.chunk_id,
                heading=chunk.heading,
                level=chunk.level,
                parent_heading=chunk.parent_heading,
                section_path=chunk.section_path,
                summary=f"[Analysis failed: {e}]",
                content_types=["TITLE_AND_CONTENT"],
                importance="low",
            )

        cache.store(chunk.chunk_id, analysis)
        analyses.append(analysis)

        if progress_callback:
            progress_callback(chunk.heading, i + 1, total)

    logger.info("Batch analysis complete: %d/%d chunks", len(analyses), total)
    return analyses, cache
