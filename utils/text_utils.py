"""
utils/text_utils.py — Text manipulation helpers.

Responsibilities:
- Truncate long source texts to fit LLM context windows.
- Clean and normalize extracted document text.
- Split text into chunks.
- Generate safe filenames from presentation titles.
"""

from __future__ import annotations

import re
import unicodedata


def truncate_text(text: str, max_chars: int, ellipsis: str = "\n\n[... content truncated ...]") -> str:
    """
    Truncate text to max_chars, appending an ellipsis marker if truncated.
    Tries to cut at a paragraph boundary.
    """
    if len(text) <= max_chars:
        return text

    # Try to cut at last paragraph break before limit
    cut_point = text.rfind("\n\n", 0, max_chars)
    if cut_point == -1:
        # Fall back to last newline
        cut_point = text.rfind("\n", 0, max_chars)
    if cut_point == -1:
        # Fall back to last space
        cut_point = text.rfind(" ", 0, max_chars)
    if cut_point == -1:
        cut_point = max_chars

    return text[:cut_point].rstrip() + ellipsis


def clean_text(text: str) -> str:
    """
    Normalize and clean extracted document text:
    - Normalize Unicode to NFC
    - Remove null bytes and non-printable characters
    - Collapse excessive blank lines (max 2 consecutive)
    - Strip leading/trailing whitespace
    """
    # Normalize Unicode
    text = unicodedata.normalize("NFC", text)

    # Remove null bytes
    text = text.replace("\x00", "")

    # Remove non-printable characters (except common whitespace)
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", "", text)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse excessive spaces on a single line
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def sanitize_filename(title: str, max_length: int = 60) -> str:
    """
    Convert a presentation title to a safe filename.
    Example: "AI-Powered Logistics Platform" → "AI_Powered_Logistics_Platform.pptx"
    """
    # Replace spaces and hyphens with underscores
    name = re.sub(r"[\s\-]+", "_", title)

    # Remove characters not allowed in filenames
    name = re.sub(r"[^\w_.]", "", name)

    # Remove leading/trailing underscores/dots
    name = name.strip("_.")

    # Truncate
    if len(name) > max_length:
        name = name[:max_length].rstrip("_.")

    # Ensure not empty
    if not name:
        name = "presentation"

    return f"{name}.pptx"


def bullet_text(text: str, max_words: int = 12) -> str:
    """
    Shorten a bullet point to max_words if needed.
    Preserves meaning by truncating at word boundary.
    """
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


def extract_first_sentence(text: str) -> str:
    """Extract the first sentence from a paragraph."""
    match = re.search(r"([^.!?]+[.!?])", text)
    if match:
        return match.group(1).strip()
    return text.split("\n")[0].strip()


def chunk_text(text: str, chunk_size: int = 3000, overlap: int = 200) -> list[str]:
    """
    Split long text into overlapping chunks for LLM processing.
    Splits at paragraph boundaries where possible.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:])
            break

        # Find last paragraph break before end
        split_point = text.rfind("\n\n", start, end)
        if split_point == -1:
            split_point = text.rfind("\n", start, end)
        if split_point == -1:
            split_point = text.rfind(" ", start, end)
        if split_point == -1:
            split_point = end

        chunks.append(text[start:split_point])
        start = max(split_point - overlap, start + 1)

    return [c.strip() for c in chunks if c.strip()]
