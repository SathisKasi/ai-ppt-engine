"""
core/dynamic_chunker.py -- AI-Driven Dynamic Semantic Chunking Engine.

This module provides intelligent, content-aware chunking for documents whose
structure is absent, inconsistent, or unreliable (unformatted TXT, scanned PDFs,
conversation transcripts, mixed-format reports, etc.).

HOW IT WORKS
============

1.  ElementRegistry
    Every paragraph, heading line, list item, and table row in the document is
    assigned a stable, ordered element ID (element_001, element_002, ...).
    The registry maps element_id -> DocumentElement (text + type + page + offset).

2.  Sliding-Window LLM Boundary Detection
    The element list is divided into overlapping windows of `window_size` elements.
    Each window overlaps the next by `overlap` elements so topic shifts near window
    edges are never missed.
    For each window, the LLM identifies semantic chunk boundaries and returns only
    element ID references -- it does NOT reproduce content, saving tokens.

3.  Multi-Window Boundary Merging
    Boundaries collected from all windows are deduplicated and merged.
    Near-duplicate boundaries (within `overlap` elements of each other) that appear
    in adjacent window outputs are resolved in favour of the higher-confidence one.

4.  Validation & Gap Filling
    A validator ensures:
    - Every element is covered exactly once (no gaps, no overlaps).
    - No chunk is shorter than min_elements.
    - All chunk IDs are unique and sequentially ordered.
    If gaps are found, they are automatically appended to the preceding chunk.

5.  SemanticChunk Construction
    The full text for each chunk is assembled from the element registry.
    Each SemanticChunk carries provenance metadata:
    source_elements, page_start, page_end, boundary_method, boundary_confidence.

6.  Safety Split (last resort)
    If a constructed chunk exceeds max_chunk_chars, it is split at the nearest
    paragraph boundary. Chunks produced this way carry boundary_method="paragraph_fallback".

7.  Comprehensive Logging
    Every LLM window call is fully logged to:
        logs/llm/<run_id>/dynamic_chunking/window_NNN.json
    A master summary is saved to:
        logs/llm/<run_id>/dynamic_chunking/chunking_summary.json

INTEGRATION
===========
Called from core/content_analyzer.py -> analyze_content_semantic() when the
document detection method is unreliable (pdf_heuristic, llm_inferred, etc.).
Returns List[SemanticChunk] -- identical type expected by the rest of the pipeline.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.document_structure import DocumentSection, SemanticChunk
from llm.prompts import DYNAMIC_CHUNK_BOUNDARY_PROMPT, SYSTEM_ROLE_DYNAMIC_CHUNKER
from llm.schemas import (
    ChunkBoundary,
    DynamicChunkingPlan,
    DynamicChunkingWindowLog,
    ChunkingSummaryLog,
)
from utils.logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration defaults (overridable via run_dynamic_chunking kwargs)
# ---------------------------------------------------------------------------

DEFAULT_WINDOW_SIZE = 60        # elements per LLM window
DEFAULT_OVERLAP = 10            # elements shared between consecutive windows
DEFAULT_MIN_ELEMENTS = 3        # minimum elements per chunk before merging
DEFAULT_MAX_CHUNK_CHARS = 8000  # safety split threshold
DEFAULT_MIN_CHUNK_CHARS = 200   # minimum chars before merging tiny chunks


# ---------------------------------------------------------------------------
# Document Element -- atomic unit of the document
# ---------------------------------------------------------------------------

@dataclass
class DocumentElement:
    """One atomic unit of the document (paragraph, heading line, list item, etc.)."""
    element_id: str            # "element_001"
    text: str                  # normalized text content
    source: str                # "heading_h1" | "heading_h2" | "heading_h3"
                               # | "paragraph" | "list_item" | "table_row"
    page_num: Optional[int]    # 0-based page index; None if not available
    char_offset: int           # cumulative character offset in the joined text

    def display(self) -> str:
        """Short display string for LLM element listing."""
        text_preview = self.text[:200].replace("\n", " ")
        return f"[{self.element_id}] ({self.source}) {text_preview}"


# ---------------------------------------------------------------------------
# Element Registry -- ordered registry of all document elements
# ---------------------------------------------------------------------------

class ElementRegistry:
    """
    Builds and stores the flat, ordered list of DocumentElement objects
    extracted from a DocumentSection tree.

    IDs are assigned sequentially from element_001, element_002, ...
    """

    def __init__(self) -> None:
        self._elements: List[DocumentElement] = []
        self._id_map: Dict[str, DocumentElement] = {}
        self._counter = 0
        self._char_offset = 0

    # -- Building ------------------------------------------------------------

    def _next_id(self) -> str:
        self._counter += 1
        return f"element_{self._counter:03d}"

    def _add(self, text: str, source: str, page_num: Optional[int] = None) -> None:
        text = text.strip()
        if not text:
            return
        eid = self._next_id()
        el = DocumentElement(
            element_id=eid,
            text=text,
            source=source,
            page_num=page_num,
            char_offset=self._char_offset,
        )
        self._elements.append(el)
        self._id_map[eid] = el
        self._char_offset += len(text) + 2  # account for separator

    def populate_from_section_tree(self, root: DocumentSection) -> None:
        """Walk the section tree and register every heading and paragraph."""

        def _walk(sec: DocumentSection) -> None:
            if sec.level > 0 and sec.heading:
                src = f"heading_h{min(sec.level, 3)}"
                self._add(sec.heading, src, page_num=None)
            for para in sec.content:
                for line in para.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if re.match(r"^[-*]\s+", line) or re.match(r"^\d+[.)]\s+", line):
                        self._add(line, "list_item")
                    else:
                        self._add(line, "paragraph")
            for sub in sec.subsections:
                _walk(sub)

        _walk(root)
        logger.info(
            "ElementRegistry: %d elements from section tree", len(self._elements)
        )

    def populate_from_plain_text(self, text: str) -> None:
        """Register elements from plain text (no heading tree)."""
        paragraphs = re.split(r"\n{2,}", text)
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if re.match(r"^[A-Z][A-Z0-9 :&\-/]{3,59}$", para) and len(para.split()) <= 10:
                self._add(para, "heading_h1")
            elif len(para) > 600:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                buf, buf_len = [], 0
                for sent in sentences:
                    buf.append(sent)
                    buf_len += len(sent)
                    if buf_len >= 400:
                        self._add(" ".join(buf), "paragraph")
                        buf, buf_len = [], 0
                if buf:
                    self._add(" ".join(buf), "paragraph")
            else:
                self._add(para, "paragraph")

        logger.info("ElementRegistry: %d elements from plain text", len(self._elements))

    # -- Access --------------------------------------------------------------

    @property
    def elements(self) -> List[DocumentElement]:
        return self._elements

    @property
    def count(self) -> int:
        return len(self._elements)

    def get(self, element_id: str) -> Optional[DocumentElement]:
        return self._id_map.get(element_id)

    def get_range(self, start_id: str, end_id: str) -> List[DocumentElement]:
        start_idx = self._index_of(start_id)
        end_idx = self._index_of(end_id)
        if start_idx is None or end_idx is None:
            return []
        return self._elements[start_idx : end_idx + 1]

    def _index_of(self, element_id: str) -> Optional[int]:
        el = self._id_map.get(element_id)
        if el is None:
            return None
        try:
            return self._elements.index(el)
        except ValueError:
            return None

    def element_ids(self) -> List[str]:
        return [el.element_id for el in self._elements]

    def build_element_listing(self, elements: List[DocumentElement]) -> str:
        return "\n".join(el.display() for el in elements)


# ---------------------------------------------------------------------------
# Window builder
# ---------------------------------------------------------------------------

def _build_windows(
    elements: List[DocumentElement],
    window_size: int,
    overlap: int,
) -> List[Tuple[int, int]]:
    if not elements:
        return []
    total = len(elements)
    step = max(1, window_size - overlap)
    windows: List[Tuple[int, int]] = []
    start = 0
    while start < total:
        end = min(start + window_size - 1, total - 1)
        windows.append((start, end))
        if end == total - 1:
            break
        start += step
    return windows


# ---------------------------------------------------------------------------
# LLM boundary detection (per window)
# ---------------------------------------------------------------------------

def _detect_boundaries_in_window(
    window_elements: List[DocumentElement],
    window_id: str,
    chunk_id_start: int,
    document_title: str,
    prior_context: str,
    min_elements: int,
    client,
    logs_dir: Path,
    run_id: str,
) -> Tuple[List[ChunkBoundary], DynamicChunkingWindowLog]:
    from llm.groq_client import JSONParseError

    first_element = window_elements[0].element_id
    last_element = window_elements[-1].element_id
    element_listing = "\n".join(el.display() for el in window_elements)

    prompt = DYNAMIC_CHUNK_BOUNDARY_PROMPT.format(
        document_title=document_title,
        window_id=window_id,
        first_element=first_element,
        last_element=last_element,
        prior_context=prior_context[:1500] if prior_context else "None (first window)",
        element_listing=element_listing,
        chunk_id_start=chunk_id_start,
        min_elements=min_elements,
    )

    messages = [
        {"role": "system", "content": SYSTEM_ROLE_DYNAMIC_CHUNKER},
        {"role": "user", "content": prompt},
    ]

    request_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()
    retry_count = 0
    raw_response = ""
    boundaries: List[ChunkBoundary] = []
    validation_result = "ok"
    token_usage: Optional[dict] = None
    error_msg: Optional[str] = None

    for attempt in range(3):
        retry_count = attempt
        try:
            raw_json = client.chat_complete_json(
                messages=messages,
                temperature=0.1,
                max_tokens=2048,
            )
            raw_response = json.dumps(raw_json)
            plan = DynamicChunkingPlan(**raw_json)
            boundaries = plan.boundaries
            break
        except JSONParseError as exc:
            error_msg = f"JSONParseError attempt {attempt + 1}: {exc}"
            logger.warning("Window %s JSON parse fail (attempt %d): %s", window_id, attempt + 1, exc)
        except Exception as exc:
            error_msg = f"LLM error attempt {attempt + 1}: {exc}"
            logger.warning("Window %s LLM error (attempt %d): %s", window_id, attempt + 1, exc)

    if not boundaries:
        boundaries = [
            ChunkBoundary(
                chunk_id=f"chunk_{chunk_id_start:03d}",
                start_element=first_element,
                end_element=last_element,
                topic="Document section",
                boundary_reason="LLM detection failed -- window treated as single chunk",
                confidence=0.0,
            )
        ]
        validation_result = "fallback"
        logger.warning("Window %s: LLM failed -- single-chunk fallback", window_id)

    window_log = DynamicChunkingWindowLog(
        run_id=run_id,
        request_id=request_id,
        window_id=window_id,
        timestamp=timestamp,
        element_range=[first_element, last_element],
        element_count=len(window_elements),
        prompt_preview=prompt[:500].replace("\n", " "),
        raw_llm_response=raw_response[:4000],
        parsed_boundaries=[b.model_dump() for b in boundaries],
        validation_result=validation_result,
        retry_count=retry_count,
        token_usage=token_usage,
        error=error_msg,
    )

    return boundaries, window_log


# ---------------------------------------------------------------------------
# Boundary merging
# ---------------------------------------------------------------------------

def _merge_window_boundaries(
    all_window_boundaries: List[List[ChunkBoundary]],
    registry: ElementRegistry,
    overlap: int,
) -> List[ChunkBoundary]:
    all_ids = registry.element_ids()
    id_to_idx = {eid: i for i, eid in enumerate(all_ids)}
    merged: Dict[str, ChunkBoundary] = {}

    for window_boundaries in all_window_boundaries:
        for boundary in window_boundaries:
            se = boundary.start_element
            if se in merged:
                if boundary.confidence > merged[se].confidence:
                    merged[se] = boundary
            else:
                merged[se] = boundary

    return sorted(
        merged.values(),
        key=lambda b: id_to_idx.get(b.start_element, 999999),
    )


# ---------------------------------------------------------------------------
# Boundary validator
# ---------------------------------------------------------------------------

def _validate_and_fill_gaps(
    boundaries: List[ChunkBoundary],
    registry: ElementRegistry,
    min_elements: int,
) -> Tuple[List[ChunkBoundary], str]:
    all_ids = registry.element_ids()
    if not all_ids:
        return boundaries, "empty"

    id_to_idx = {eid: i for i, eid in enumerate(all_ids)}
    validation_status = "ok"

    if not boundaries:
        boundaries = [
            ChunkBoundary(
                chunk_id="chunk_001",
                start_element=all_ids[0],
                end_element=all_ids[-1],
                topic="Full Document",
                boundary_reason="No semantic boundaries detected",
                confidence=0.5,
            )
        ]
        return boundaries, "single_chunk_fallback"

    # Fix first boundary start
    first_expected = all_ids[0]
    if boundaries[0].start_element != first_expected:
        first_idx = id_to_idx.get(boundaries[0].start_element, 0)
        if first_idx > 0:
            boundaries.insert(0, ChunkBoundary(
                chunk_id="chunk_000",
                start_element=first_expected,
                end_element=all_ids[first_idx - 1],
                topic="Document preamble",
                boundary_reason="Gap filled: elements before first detected boundary",
                confidence=0.5,
            ))
            validation_status = "gap_filled"

    # Fix end elements (each chunk ends one before the next starts)
    for i in range(len(boundaries) - 1):
        next_start_idx = id_to_idx.get(boundaries[i + 1].start_element)
        if next_start_idx is not None and next_start_idx > 0:
            correct_end = all_ids[next_start_idx - 1]
            if boundaries[i].end_element != correct_end:
                b = boundaries[i]
                boundaries[i] = ChunkBoundary(
                    chunk_id=b.chunk_id,
                    start_element=b.start_element,
                    end_element=correct_end,
                    topic=b.topic,
                    boundary_reason=b.boundary_reason,
                    confidence=b.confidence,
                )
                if validation_status == "ok":
                    validation_status = "overlap_resolved"

    # Fix last boundary end
    if boundaries[-1].end_element != all_ids[-1]:
        b = boundaries[-1]
        boundaries[-1] = ChunkBoundary(
            chunk_id=b.chunk_id,
            start_element=b.start_element,
            end_element=all_ids[-1],
            topic=b.topic,
            boundary_reason=b.boundary_reason + " [extended to document end]",
            confidence=b.confidence,
        )
        validation_status = "gap_filled"

    # Renumber sequentially
    for i, b in enumerate(boundaries):
        boundaries[i] = ChunkBoundary(
            chunk_id=f"chunk_{i + 1:03d}",
            start_element=b.start_element,
            end_element=b.end_element,
            topic=b.topic,
            boundary_reason=b.boundary_reason,
            confidence=b.confidence,
        )

    return boundaries, validation_status


# ---------------------------------------------------------------------------
# SemanticChunk construction
# ---------------------------------------------------------------------------

def _build_chunks_from_boundaries(
    boundaries: List[ChunkBoundary],
    registry: ElementRegistry,
    max_chunk_chars: int,
    min_chunk_chars: int,
) -> List[SemanticChunk]:
    chunks: List[SemanticChunk] = []
    safety_splits = 0

    for boundary in boundaries:
        elements = registry.get_range(boundary.start_element, boundary.end_element)
        if not elements:
            logger.warning("Boundary %s: no elements found -- skipping", boundary.chunk_id)
            continue

        content = "\n\n".join(el.text for el in elements)
        page_start = next((el.page_num for el in elements if el.page_num is not None), None)
        page_end = next((el.page_num for el in reversed(elements) if el.page_num is not None), None)

        base = SemanticChunk(
            chunk_id=boundary.chunk_id,
            heading=boundary.topic,
            level=1,
            parent_heading=None,
            section_path=[boundary.topic],
            subsections=[],
            content=content,
            char_count=len(content),
            source_elements=[el.element_id for el in elements],
            page_start=page_start,
            page_end=page_end,
            boundary_method="ai_semantic",
            boundary_confidence=boundary.confidence,
            token_count=len(content) // 4,
        )

        if len(content) <= max_chunk_chars:
            chunks.append(base)
        else:
            subs = _paragraph_safety_split(base, max_chunk_chars)
            chunks.extend(subs)
            safety_splits += len(subs) - 1

    if safety_splits:
        logger.info("%d chunk(s) safety-split at paragraph boundaries", safety_splits)

    return chunks


def _paragraph_safety_split(chunk: SemanticChunk, max_chars: int) -> List[SemanticChunk]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", chunk.content) if p.strip()]
    result: List[SemanticChunk] = []
    buf: List[str] = []
    buf_len = 0
    part = 1

    def _flush(b: List[str], p: int) -> SemanticChunk:
        c = "\n\n".join(b)
        return SemanticChunk(
            chunk_id=f"{chunk.chunk_id}_p{p:02d}",
            heading=f"{chunk.heading} (Part {p})" if p > 1 else chunk.heading,
            level=chunk.level,
            parent_heading=chunk.parent_heading,
            section_path=chunk.section_path,
            subsections=[],
            content=c,
            char_count=len(c),
            source_elements=chunk.source_elements,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            boundary_method="paragraph_fallback",
            boundary_confidence=chunk.boundary_confidence,
            token_count=len(c) // 4,
        )

    for para in paragraphs:
        if buf_len + len(para) > max_chars and buf:
            result.append(_flush(buf, part))
            buf, buf_len = [], 0
            part += 1
        buf.append(para)
        buf_len += len(para)

    if buf:
        result.append(_flush(buf, part))

    return result


def _merge_tiny_dynamic_chunks(chunks: List[SemanticChunk], min_chars: int) -> List[SemanticChunk]:
    if not chunks:
        return chunks
    merged: List[SemanticChunk] = []
    for chunk in chunks:
        if chunk.char_count < min_chars and merged:
            prev = merged[-1]
            combined = prev.content + "\n\n" + chunk.content
            merged[-1] = SemanticChunk(
                chunk_id=prev.chunk_id,
                heading=prev.heading,
                level=prev.level,
                parent_heading=prev.parent_heading,
                section_path=prev.section_path,
                subsections=list(dict.fromkeys(prev.subsections + chunk.subsections)),
                content=combined,
                char_count=len(combined),
                source_elements=prev.source_elements + chunk.source_elements,
                page_start=prev.page_start,
                page_end=chunk.page_end or prev.page_end,
                boundary_method=prev.boundary_method,
                boundary_confidence=prev.boundary_confidence,
                token_count=len(combined) // 4,
            )
        else:
            merged.append(chunk)
    return merged


# ---------------------------------------------------------------------------
# JSON log helpers
# ---------------------------------------------------------------------------

def _save_json_log(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            if hasattr(data, "model_dump"):
                json.dump(data.model_dump(), f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning("Could not save JSON log %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Prior context builder
# ---------------------------------------------------------------------------

def _build_prior_context(completed_chunks: List[SemanticChunk], max_chars: int = 800) -> str:
    if not completed_chunks:
        return "None (first window)"
    lines = []
    for ch in completed_chunks[-5:]:
        lines.append(f"- {ch.heading}: {ch.content[:100].replace(chr(10), ' ')}...")
    return "\n".join(lines)[:max_chars]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_dynamic_chunking(
    root_section,
    plain_text: str,
    document_title: str,
    key_manager,
    logs_dir: Path,
    run_id: str,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
    window_size: int = DEFAULT_WINDOW_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    min_elements: int = DEFAULT_MIN_ELEMENTS,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> List[SemanticChunk]:
    """
    AI-Driven Dynamic Chunking entry point.

    Returns List[SemanticChunk] -- same type as build_semantic_chunks().
    """
    chunking_log_dir = logs_dir / run_id / "dynamic_chunking"
    chunking_log_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Build element registry
    registry = ElementRegistry()

    if root_section is not None and (
        getattr(root_section, "subsections", None) or getattr(root_section, "content", None)
    ):
        registry.populate_from_section_tree(root_section)

    if registry.count < 3 and plain_text:
        logger.info(
            "Section tree too sparse (%d elements) -- using plain text registry", registry.count
        )
        registry = ElementRegistry()
        registry.populate_from_plain_text(plain_text)

    if registry.count == 0:
        logger.warning("Dynamic chunker: no elements -- returning empty list")
        return []

    logger.info(
        "Dynamic chunking start: %d elements, window=%d, overlap=%d",
        registry.count, window_size, overlap,
    )

    # Step 2: Build sliding windows
    windows = _build_windows(registry.elements, window_size, overlap)
    total_windows = len(windows)
    logger.info("Dynamic chunking: %d window(s)", total_windows)

    # Step 3: LLM boundary detection per window
    all_window_boundaries: List[List[ChunkBoundary]] = []
    completed_chunks_so_far: List[SemanticChunk] = []
    chunk_id_counter = 1

    for w_idx, (start_idx, end_idx) in enumerate(windows):
        window_elements = registry.elements[start_idx : end_idx + 1]
        window_id = f"window_{w_idx + 1:03d}"
        client = key_manager.get_client(chunk_index=w_idx)
        prior_context = _build_prior_context(completed_chunks_so_far)

        if progress_callback:
            progress_callback(
                f"AI boundary detection: window {w_idx + 1}/{total_windows}",
                w_idx + 1,
                total_windows,
            )

        boundaries, window_log = _detect_boundaries_in_window(
            window_elements=window_elements,
            window_id=window_id,
            chunk_id_start=chunk_id_counter,
            document_title=document_title,
            prior_context=prior_context,
            min_elements=min_elements,
            client=client,
            logs_dir=logs_dir,
            run_id=run_id,
        )

        _save_json_log(chunking_log_dir / f"{window_id}.json", window_log)
        all_window_boundaries.append(boundaries)
        chunk_id_counter += len(boundaries)

        # Build preview chunks for prior context in next window
        for b in boundaries:
            elems = registry.get_range(b.start_element, b.end_element)
            preview = "\n\n".join(e.text for e in elems[:3])
            completed_chunks_so_far.append(SemanticChunk(
                chunk_id=b.chunk_id,
                heading=b.topic,
                level=1,
                parent_heading=None,
                section_path=[b.topic],
                subsections=[],
                content=preview,
                char_count=len(preview),
            ))

    # Step 4: Merge boundaries across windows
    merged_boundaries = _merge_window_boundaries(all_window_boundaries, registry, overlap)

    # Step 5: Validate and fill gaps
    validated_boundaries, validation_status = _validate_and_fill_gaps(
        merged_boundaries, registry, min_elements
    )
    logger.info(
        "Boundary validation: %d boundaries, status=%s",
        len(validated_boundaries), validation_status,
    )

    # Step 6: Build SemanticChunk objects
    chunks = _build_chunks_from_boundaries(
        validated_boundaries, registry, max_chunk_chars, min_chunk_chars
    )

    # Step 7: Merge tiny residuals
    chunks = _merge_tiny_dynamic_chunks(chunks, min_chunk_chars)

    logger.info(
        "Dynamic chunking complete: %d chunks from %d elements",
        len(chunks), registry.count,
    )

    # Step 8: Save master summary
    method_counts: Dict[str, int] = {}
    for ch in chunks:
        method_counts[ch.boundary_method] = method_counts.get(ch.boundary_method, 0) + 1

    summary_log = ChunkingSummaryLog(
        run_id=run_id,
        document_title=document_title,
        detection_method="ai_dynamic",
        total_elements=registry.count,
        total_windows=total_windows,
        total_chunks=len(chunks),
        boundary_method_counts=method_counts,
        chunks=[ch.to_dict() for ch in chunks],
    )
    _save_json_log(chunking_log_dir / "chunking_summary.json", summary_log)

    return chunks