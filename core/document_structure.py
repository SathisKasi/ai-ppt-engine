"""
core/document_structure.py — Semantic heading detection and section tree builder.

Converts raw document content into a hierarchical section tree, then
produces semantically-meaningful chunks for per-section LLM analysis.

DETECTION PRIORITY:
  DOCX  → Word Heading 1/2/3 styles (definitive — no guessing needed)
  TXT   → Markdown # / ## / ### and numbered outlines 1. / 2.1 / 2.1.1
  PDF   → Font-size heuristics + bold + numbering + whitespace signals
  None  → LLM-inferred structure (see auto_structure_from_plain_text)

CONSERVATIVE DETECTION (critical):
  - For DOCX: 1 signal required (style name is definitive)
  - For TXT:  1 signal if Markdown syntax, 2 signals for plain patterns
  - For PDF:  2+ signals required (font size AND short line AND bold/number)
  - Never classify a short sentence as heading without strong evidence

CHUNKING STRATEGY (3-tier):
  1. Heading/sub-heading boundaries (primary)
  2. Sub-heading split if section > max_chunk_chars
  3. Paragraph split as last resort (never mid-sentence)
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DocumentSection:
    """One node in the section tree."""
    heading: str
    level: int                       # 0=root, 1=H1, 2=H2, 3=H3
    content: List[str]               # paragraphs directly under this heading
    subsections: List["DocumentSection"] = field(default_factory=list)
    parent_heading: Optional[str] = None

    # ── helpers ──────────────────────────────────────────────────────────

    def full_text(self) -> str:
        """All text content in this section (not recursing into subsections)."""
        return "\n\n".join(p for p in self.content if p.strip())

    def total_chars(self) -> int:
        """Character count including all descendant sections."""
        own = len(self.full_text())
        return own + sum(s.total_chars() for s in self.subsections)

    def is_empty(self) -> bool:
        return not any(p.strip() for p in self.content) and not self.subsections

    def to_dict(self) -> Dict[str, Any]:
        """Serializable dict for JSON logging."""
        return {
            "heading": self.heading,
            "level": self.level,
            "content_chars": len(self.full_text()),
            "subsections": [s.to_dict() for s in self.subsections],
        }

    def __repr__(self) -> str:
        prefix = "  " * self.level
        return f"{prefix}[H{self.level}] {self.heading!r} ({len(self.content)} paragraphs)"


@dataclass
class SemanticChunk:
    """A self-contained chunk ready for LLM analysis."""
    chunk_id: str                   # e.g. "section_002_001" or "chunk_003"
    heading: str
    level: int
    parent_heading: Optional[str]
    section_path: List[str]         # breadcrumb: ["H1 title", "H2 title"]
    subsections: List[str]          # direct child headings (for context)
    content: str                    # full text content
    char_count: int

    # ── Provenance metadata (set by dynamic chunker; None for structural chunks) ──
    source_elements: List[str] = field(default_factory=list)   # ["element_001", ...]
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    boundary_method: str = "structural"          # "structural" | "ai_semantic" | "paragraph_fallback"
    boundary_confidence: Optional[float] = None  # 0.0–1.0; None for structural
    token_count: Optional[int] = None            # estimated tokens; None if not computed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "heading": self.heading,
            "level": self.level,
            "parent_heading": self.parent_heading,
            "section_path": self.section_path,
            "subsections": self.subsections,
            "char_count": self.char_count,
            "source_elements": self.source_elements,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "boundary_method": self.boundary_method,
            "boundary_confidence": self.boundary_confidence,
            "token_count": self.token_count,
        }



# ---------------------------------------------------------------------------
# Numbering-pattern helpers (shared across DOCX / TXT / PDF)
# ---------------------------------------------------------------------------

# e.g. "1.", "2.", "10."
_NUM_H1 = re.compile(r"^\d+\.\s+[A-Z\u00C0-\u024F].{1,80}$")
# e.g. "2.1", "3.12", "10.3"
_NUM_H2 = re.compile(r"^\d+\.\d+\s+.{1,80}$")
# e.g. "2.1.3"
_NUM_H3 = re.compile(r"^\d+\.\d+\.\d+\s+.{1,80}$")

# Markdown headings
_MD_H1 = re.compile(r"^#\s+(.+)$")
_MD_H2 = re.compile(r"^##\s+(.+)$")
_MD_H3 = re.compile(r"^###\s+(.+)$")

# ALL-CAPS short line (plain text convention)
_ALL_CAPS = re.compile(r"^[A-Z][A-Z0-9 :&\-/]{3,59}$")


def _numbered_level(line: str) -> Optional[int]:
    """Return heading level if line matches a numbered pattern, else None."""
    stripped = line.strip()
    if _NUM_H3.match(stripped):
        return 3
    if _NUM_H2.match(stripped):
        return 2
    if _NUM_H1.match(stripped):
        return 1
    return None


def _is_short_line(line: str, max_words: int = 10) -> bool:
    return len(line.split()) <= max_words and len(line) < 80


# ---------------------------------------------------------------------------
# DOCX structure extraction
# ---------------------------------------------------------------------------

def extract_structure_from_docx(file_path: Path) -> Tuple[DocumentSection, str]:
    """
    Extract section tree from a .docx using Word heading styles.

    Returns:
        (root_section, detection_method)
    """
    from docx import Document

    doc = Document(str(file_path))
    root = DocumentSection("__ROOT__", 0, [], [])

    # Stack: [(section, level)] — root is always at bottom
    stack: List[DocumentSection] = [root]
    current_content: List[str] = []

    def _flush_to_current(paragraphs: List[str]) -> None:
        if stack:
            stack[-1].content.extend(p for p in paragraphs if p.strip())

    heading_count = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style = para.style.name  # e.g. "Heading 1", "Normal", "Body Text"

        if style.startswith("Heading "):
            try:
                level = int(style.split()[-1])
            except ValueError:
                level = 1
            level = min(level, 3)  # cap at H3

            _flush_to_current(current_content)
            current_content = []

            # Pop stack until we find the parent
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()

            parent = stack[-1]
            new_section = DocumentSection(
                heading=text,
                level=level,
                content=[],
                subsections=[],
                parent_heading=parent.heading if parent.level > 0 else None,
            )
            parent.subsections.append(new_section)
            stack.append(new_section)
            heading_count += 1

        else:
            current_content.append(text)

    # Also include tables as plain text
    for table in doc.tables:
        for row in table.rows:
            row_texts = [c.text.strip() for c in row.cells if c.text.strip()]
            if row_texts:
                current_content.append(" | ".join(row_texts))

    _flush_to_current(current_content)

    method = "docx_styles"
    if heading_count == 0:
        logger.info("DOCX has no Heading styles — treating as flat text")
    else:
        logger.info("DOCX: detected %d headings via Word styles", heading_count)

    return root, method


# ---------------------------------------------------------------------------
# TXT structure extraction
# ---------------------------------------------------------------------------

def extract_structure_from_txt(text: str) -> Tuple[DocumentSection, str]:
    """
    Extract section tree from plain text using Markdown and numbered patterns.

    Priority:
      1. Markdown # / ## / ###
      2. Numbered outline 1. / 2.1 / 2.1.1
      3. ALL-CAPS short lines (with surrounding blank lines) — low confidence

    Returns:
        (root_section, detection_method)
    """
    lines = text.splitlines()
    root = DocumentSection("__ROOT__", 0, [], [])
    stack: List[DocumentSection] = [root]
    current_content: List[str] = []
    heading_count = 0
    method = "txt_plain"

    def _push_heading(text_line: str, level: int) -> None:
        nonlocal heading_count, method
        parent = stack[-1]
        while len(stack) > 1 and stack[-1].level >= level:
            stack.pop()
        parent = stack[-1]
        sec = DocumentSection(
            heading=text_line,
            level=level,
            content=[],
            subsections=[],
            parent_heading=parent.heading if parent.level > 0 else None,
        )
        parent.subsections.append(sec)
        stack.append(sec)
        heading_count += 1

    def _flush(paragraphs: List[str]) -> None:
        if stack:
            stack[-1].content.extend(p for p in paragraphs if p.strip())

    # First pass: detect if document has Markdown headings
    has_markdown = any(_MD_H1.match(l) or _MD_H2.match(l) or _MD_H3.match(l)
                       for l in lines)

    prev_blank = True
    para_buf: List[str] = []

    for i, line in enumerate(lines):
        stripped = line.rstrip()

        # Blank line → flush paragraph buffer
        if not stripped:
            if para_buf:
                _flush(para_buf)
                para_buf = []
            prev_blank = True
            continue

        # ── Markdown headings (highest priority) ──────────────────────
        if has_markdown:
            m3 = _MD_H3.match(stripped)
            m2 = _MD_H2.match(stripped)
            m1 = _MD_H1.match(stripped)
            if m3:
                _flush(para_buf); para_buf = []
                _push_heading(m3.group(1).strip(), 3)
                method = "txt_markdown"
                prev_blank = False
                continue
            if m2:
                _flush(para_buf); para_buf = []
                _push_heading(m2.group(1).strip(), 2)
                method = "txt_markdown"
                prev_blank = False
                continue
            if m1:
                _flush(para_buf); para_buf = []
                _push_heading(m1.group(1).strip(), 1)
                method = "txt_markdown"
                prev_blank = False
                continue

        # ── Numbered patterns ─────────────────────────────────────────
        num_level = _numbered_level(stripped)
        if num_level and _is_short_line(stripped):
            _flush(para_buf); para_buf = []
            _push_heading(stripped, num_level)
            method = "txt_numbered"
            prev_blank = False
            continue

        # ── ALL-CAPS lines surrounded by blank lines (conservative) ───
        if (prev_blank and _ALL_CAPS.match(stripped) and _is_short_line(stripped)
                and not has_markdown and i + 1 < len(lines) and not lines[i + 1].strip() == stripped):
            # Check next line is blank or content (not another caps line)
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if not _ALL_CAPS.match(next_line):
                _flush(para_buf); para_buf = []
                _push_heading(stripped.title(), 1)
                method = "txt_allcaps"
                prev_blank = False
                continue

        para_buf.append(stripped)
        prev_blank = False

    _flush(para_buf)

    logger.info("TXT: %d headings detected via %s", heading_count, method)
    return root, method


# ---------------------------------------------------------------------------
# PDF structure extraction
# ---------------------------------------------------------------------------

def extract_structure_from_pdf(file_path: Path) -> Tuple[DocumentSection, str]:
    """
    Extract section tree from PDF using PyMuPDF font-size heuristics.

    Heading signals (need 2+ for classification):
      - Font size significantly larger than body average
      - Bold flag
      - Short line (< 10 words)
      - Numbered pattern
      - Followed by normal-size text
      - Preceded by whitespace

    Returns:
        (root_section, detection_method)
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not available for PDF heading detection")
        return _pdf_fallback_txt(file_path)

    doc = fitz.open(str(file_path))
    blocks: List[Dict] = []

    # ── Collect all text blocks with font metadata ──────────────────────
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        block_list = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        for block in block_list:
            if block.get("type") != 0:  # 0 = text
                continue
            for line in block.get("lines", []):
                line_text = ""
                max_size = 0.0
                is_bold = False
                for span in line.get("spans", []):
                    line_text += span.get("text", "")
                    size = span.get("size", 12)
                    if size > max_size:
                        max_size = size
                    flags = span.get("flags", 0)
                    if flags & 2**4:  # bold flag
                        is_bold = True

                text = line_text.strip()
                if text:
                    blocks.append({
                        "text": text,
                        "size": max_size,
                        "bold": is_bold,
                        "page": page_num,
                    })

    doc.close()

    if not blocks:
        return DocumentSection("__ROOT__", 0, [], []), "pdf_empty"

    # ── Compute body font size (median) ──────────────────────────────────
    sizes = sorted(b["size"] for b in blocks)
    median_size = sizes[len(sizes) // 2]
    heading_threshold = median_size * 1.18  # >18% bigger than body

    # ── Classify each block ──────────────────────────────────────────────
    root = DocumentSection("__ROOT__", 0, [], [])
    stack: List[DocumentSection] = [root]
    current_content: List[str] = []
    heading_count = 0

    def _flush(paragraphs: List[str]) -> None:
        if stack:
            stack[-1].content.extend(p for p in paragraphs if p.strip())

    def _push_h(text_line: str, level: int) -> None:
        nonlocal heading_count
        while len(stack) > 1 and stack[-1].level >= level:
            stack.pop()
        parent = stack[-1]
        sec = DocumentSection(
            heading=text_line,
            level=level,
            content=[],
            subsections=[],
            parent_heading=parent.heading if parent.level > 0 else None,
        )
        parent.subsections.append(sec)
        stack.append(sec)
        heading_count += 1

    for blk in blocks:
        text = blk["text"]
        size = blk["size"]
        bold = blk["bold"]
        short = _is_short_line(text)

        # Score heading signals
        signals = 0
        if size >= heading_threshold:
            signals += 1
        if bold:
            signals += 1
        if short:
            signals += 1

        num_level = _numbered_level(text)
        if num_level:
            signals += 1

        if signals >= 2 and short:
            _flush(current_content)
            current_content = []

            if num_level:
                level = num_level
            elif size >= heading_threshold * 1.2:
                level = 1
            elif size >= heading_threshold:
                level = 2 if not bold else 2
            else:
                level = 2

            _push_h(text, level)
        else:
            current_content.append(text)

    _flush(current_content)

    method = "pdf_heuristic"
    logger.info("PDF: %d headings detected via %s", heading_count, method)
    return root, method


def _pdf_fallback_txt(file_path: Path) -> Tuple[DocumentSection, str]:
    """Fallback: extract PDF as plain text and apply TXT detection."""
    try:
        import fitz
        doc = fitz.open(str(file_path))
        text = "\n\n".join(page.get_text() for page in doc)
        doc.close()
    except Exception:
        try:
            import pdfplumber
            with pdfplumber.open(str(file_path)) as pdf:
                text = "\n\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            return DocumentSection("__ROOT__", 0, [], []), "pdf_failed"

    root, method = extract_structure_from_txt(text)
    return root, f"pdf_via_{method}"


# ---------------------------------------------------------------------------
# LLM-inferred auto structure (zero headings fallback)
# ---------------------------------------------------------------------------

def auto_structure_from_plain_text(
    text: str,
    client,  # GroqClient — typed as Any to avoid circular import
    document_title: str = "Document",
) -> Tuple[DocumentSection, str]:
    """
    When no headings are detected, ask the LLM to infer the section structure
    from the content itself, then split the text accordingly.

    Returns:
        (root_section, "llm_inferred")
    """
    from llm.prompts import AUTO_STRUCTURE_PROMPT, SYSTEM_ROLE_STRUCTURE_INFERRER
    from llm.groq_client import JSONParseError

    logger.info("No headings detected — using LLM to infer document structure")

    # Truncate for the structure-inference prompt
    sample = text[:10000] if len(text) > 10000 else text

    prompt = AUTO_STRUCTURE_PROMPT.format(content=sample)
    messages = [
        {"role": "system", "content": SYSTEM_ROLE_STRUCTURE_INFERRER},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = client.chat_complete_json(messages=messages, temperature=0.2, max_tokens=2048)
    except (JSONParseError, Exception) as e:
        logger.warning("LLM structure inference failed: %s — treating as single section", e)
        root = DocumentSection(document_title, 0, [], [])
        root.content = [text]
        return root, "single_chunk"

    root = DocumentSection("__ROOT__", 0, [], [])
    inferred_title = raw.get("inferred_title", document_title)
    sections_data = raw.get("sections", [])

    if not sections_data:
        root.content = [text]
        return root, "single_chunk"

    # Split the text into sections using start_markers
    _split_text_by_markers(root, text, sections_data, inferred_title)

    logger.info("LLM inferred %d top-level sections", len(root.subsections))
    return root, "llm_inferred"


def _split_text_by_markers(
    root: DocumentSection,
    text: str,
    sections_data: List[Dict],
    inferred_title: str,
) -> None:
    """
    Split `text` into DocumentSection nodes using start_markers from LLM output.
    Markers are fuzzy-matched against the text.
    """
    # Build list of (position, section_dict) pairs
    positions: List[Tuple[int, Dict]] = []

    for section in sections_data:
        marker = section.get("start_marker", "").strip()
        if not marker:
            continue
        # Fuzzy match: try exact, then first 6 words
        pos = text.find(marker)
        if pos == -1:
            short_marker = " ".join(marker.split()[:6])
            pos = text.find(short_marker)
        if pos != -1:
            positions.append((pos, section))

    positions.sort(key=lambda x: x[0])

    if not positions:
        # Couldn't match any markers — put everything in one section
        root.content = [text]
        return

    # Slice text between markers
    for i, (start_pos, sec_data) in enumerate(positions):
        end_pos = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        chunk_text = text[start_pos:end_pos].strip()

        section_node = DocumentSection(
            heading=sec_data.get("heading", f"Section {i + 1}"),
            level=sec_data.get("level", 1),
            content=[chunk_text],
            subsections=[],
            parent_heading=None,
        )

        # Process subsections if provided
        for sub_data in sec_data.get("subsections", []):
            sub_marker = sub_data.get("start_marker", "").strip()
            if sub_marker and sub_marker in chunk_text:
                sub_pos = chunk_text.find(sub_marker)
                sub_node = DocumentSection(
                    heading=sub_data.get("heading", "Subsection"),
                    level=sub_data.get("level", 2),
                    content=[chunk_text[sub_pos:].strip()],
                    subsections=[],
                    parent_heading=section_node.heading,
                )
                section_node.subsections.append(sub_node)

        root.subsections.append(section_node)

    # Any text before the first marker becomes root content
    if positions:
        preamble = text[:positions[0][0]].strip()
        if preamble:
            root.content.append(preamble)


# ---------------------------------------------------------------------------
# Semantic chunking algorithm
# ---------------------------------------------------------------------------

def build_semantic_chunks(
    root: DocumentSection,
    max_chunk_chars: int = 8000,
    min_section_chars: int = 300,
) -> List[SemanticChunk]:
    """
    Convert a DocumentSection tree into a flat list of SemanticChunks.

    Algorithm (3-tier):
      1. If section (with all subsections) fits in max_chunk_chars → 1 chunk
      2. If section has subsections that independently fit → chunk per subsection
      3. If single section still too large → paragraph-based split (last resort)
    """
    chunks: List[SemanticChunk] = []
    counters: Dict[str, int] = {"top": 0}

    def _make_id(parent_id: Optional[str], local_index: int) -> str:
        local = f"{local_index:03d}"
        if parent_id:
            return f"{parent_id}_{local}"
        return f"section_{local}"

    def _section_text(sec: DocumentSection, include_subsections: bool = True) -> str:
        parts = []
        if sec.heading and sec.level > 0:
            parts.append(sec.heading)
        parts.extend(p for p in sec.content if p.strip())
        if include_subsections:
            for sub in sec.subsections:
                parts.append(_section_text(sub, include_subsections=True))
        return "\n\n".join(parts)

    def _process_section(
        sec: DocumentSection,
        path: List[str],
        parent_id: Optional[str],
        local_index: int,
    ) -> None:
        chunk_id = _make_id(parent_id, local_index)
        section_path = path + ([sec.heading] if sec.level > 0 else [])
        parent_heading = path[-1] if path else None

        total_text = _section_text(sec, include_subsections=True)
        total_chars = len(total_text)

        # ── Case 1: Section (including all subsections) fits in one chunk ──
        if total_chars <= max_chunk_chars or not sec.subsections:
            if total_chars < min_section_chars and not sec.subsections:
                # Too small — will be merged by caller; skip for now
                # (Actually, we still create it; consolidation handles merging)
                pass
            chunks.append(SemanticChunk(
                chunk_id=chunk_id,
                heading=sec.heading if sec.level > 0 else "Document Overview",
                level=sec.level,
                parent_heading=parent_heading,
                section_path=section_path,
                subsections=[s.heading for s in sec.subsections],
                content=total_text,
                char_count=total_chars,
            ))
            return

        # ── Case 2: Section has subsections — chunk per subsection ─────────
        # First, chunk the H1's own intro content (before any H2s)
        intro_text = _section_text(sec, include_subsections=False)
        if intro_text.strip() and len(intro_text) > min_section_chars:
            intro_id = _make_id(parent_id, local_index)
            chunks.append(SemanticChunk(
                chunk_id=intro_id + "_intro",
                heading=sec.heading if sec.level > 0 else "Document Overview",
                level=sec.level,
                parent_heading=parent_heading,
                section_path=section_path,
                subsections=[s.heading for s in sec.subsections],
                content=intro_text,
                char_count=len(intro_text),
            ))

        # Then each subsection
        for sub_i, sub in enumerate(sec.subsections):
            _process_section(sub, section_path, chunk_id, sub_i + 1)

    # Process all top-level sections
    for i, section in enumerate(root.subsections):
        _process_section(section, [], None, i + 1)

    # If root itself has content and no subsections chunked it
    root_text = "\n\n".join(p for p in root.content if p.strip())
    if root_text and not chunks:
        # Entire document is flat; paragraph-split it
        chunks.extend(_paragraph_split(
            heading="Document",
            text=root_text,
            max_chars=max_chunk_chars,
            level=1,
        ))

    # Merge tiny adjacent chunks at the same level
    chunks = _merge_tiny_chunks(chunks, min_section_chars)

    logger.info("Built %d semantic chunks from document structure", len(chunks))
    return chunks


def _paragraph_split(
    heading: str,
    text: str,
    max_chars: int,
    level: int = 1,
    parent_heading: Optional[str] = None,
    base_id: str = "section",
) -> List[SemanticChunk]:
    """Split a large text into paragraph-boundary chunks (last-resort fallback)."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks = []
    buf: List[str] = []
    buf_len = 0
    part = 1

    for para in paragraphs:
        if buf_len + len(para) > max_chars and buf:
            chunks.append(SemanticChunk(
                chunk_id=f"{base_id}_part{part:02d}",
                heading=f"{heading} (Part {part})",
                level=level,
                parent_heading=parent_heading,
                section_path=[heading],
                subsections=[],
                content="\n\n".join(buf),
                char_count=buf_len,
            ))
            buf = []
            buf_len = 0
            part += 1
        buf.append(para)
        buf_len += len(para)

    if buf:
        chunks.append(SemanticChunk(
            chunk_id=f"{base_id}_part{part:02d}" if part > 1 else base_id,
            heading=heading if part == 1 else f"{heading} (Part {part})",
            level=level,
            parent_heading=parent_heading,
            section_path=[heading],
            subsections=[],
            content="\n\n".join(buf),
            char_count=buf_len,
        ))

    return chunks


def _merge_tiny_chunks(chunks: List[SemanticChunk], min_chars: int) -> List[SemanticChunk]:
    """
    Merge consecutive tiny chunks at the same level.
    A chunk is 'tiny' if its char_count < min_chars.
    """
    if not chunks:
        return chunks

    merged: List[SemanticChunk] = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        if chunk.char_count < min_chars and i + 1 < len(chunks):
            next_chunk = chunks[i + 1]
            # Merge into next if same parent
            if chunk.parent_heading == next_chunk.parent_heading:
                combined_content = f"**{chunk.heading}**\n\n{chunk.content}\n\n{next_chunk.content}"
                merged_chunk = SemanticChunk(
                    chunk_id=chunk.chunk_id,
                    heading=chunk.heading,
                    level=chunk.level,
                    parent_heading=chunk.parent_heading,
                    section_path=chunk.section_path,
                    subsections=list(dict.fromkeys(chunk.subsections + next_chunk.subsections)),
                    content=combined_content,
                    char_count=len(combined_content),
                )
                chunks[i + 1] = merged_chunk
                i += 1
                continue
        merged.append(chunk)
        i += 1
    return merged


# ---------------------------------------------------------------------------
# Pretty-print helpers for Streamlit debug view
# ---------------------------------------------------------------------------

def render_structure_text(root: DocumentSection, max_depth: int = 3) -> str:
    """Return a tree-formatted string of the section hierarchy."""
    lines: List[str] = []

    def _walk(sec: DocumentSection, depth: int = 0) -> None:
        if depth > max_depth:
            return
        if sec.level == 0:
            for sub in sec.subsections:
                _walk(sub, depth)
            return
        prefix = "  " * (sec.level - 1)
        connector = "▼" if sec.subsections else "•"
        lines.append(f"{prefix}{connector} {sec.heading}")
        for sub in sec.subsections:
            sub_prefix = "  " * sub.level
            lines.append(f"{sub_prefix}├── {sub.heading}")

    _walk(root)
    return "\n".join(lines)


def count_sections(root: DocumentSection) -> Tuple[int, int]:
    """Return (h1_count, h2_plus_count)."""
    h1 = 0
    h2plus = 0

    def _walk(sec: DocumentSection) -> None:
        nonlocal h1, h2plus
        if sec.level == 1:
            h1 += 1
        elif sec.level >= 2:
            h2plus += 1
        for sub in sec.subsections:
            _walk(sub)

    _walk(root)
    return h1, h2plus
