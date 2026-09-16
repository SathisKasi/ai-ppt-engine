"""
utils/file_utils.py — File I/O and temporary file management.

Responsibilities:
- Save uploaded bytes to a temporary file.
- Clean up temporary files safely.
- Validate uploaded file types and sizes.
- Generate output file paths.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from utils.logging_utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {"txt", "pdf", "docx"}


def validate_upload(filename: str, file_bytes: bytes, max_size_bytes: int) -> Optional[str]:
    """
    Validate an uploaded file.

    Returns an error message string if invalid, or None if valid.
    """
    if not filename:
        return "No filename provided."

    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        return (
            f"Unsupported file type '.{ext}'. "
            f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if not file_bytes:
        return "The uploaded file is empty."

    if len(file_bytes) > max_size_bytes:
        size_mb = len(file_bytes) / (1024 * 1024)
        max_mb = max_size_bytes / (1024 * 1024)
        return f"File is too large ({size_mb:.1f} MB). Maximum allowed: {max_mb:.0f} MB."

    return None


# ---------------------------------------------------------------------------
# Temp file management
# ---------------------------------------------------------------------------

class TempFileManager:
    """
    Context manager for temporary files.

    Usage:
        with TempFileManager(file_bytes, suffix=".pdf") as tmp_path:
            extract_text(tmp_path)
    """

    def __init__(self, data: bytes, suffix: str = "") -> None:
        self._data = data
        self._suffix = suffix
        self._path: Optional[Path] = None

    def __enter__(self) -> Path:
        fd, tmp = tempfile.mkstemp(suffix=self._suffix)
        self._path = Path(tmp)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(self._data)
        except Exception:
            os.close(fd)
            raise
        logger.debug("Created temp file: %s (%d bytes)", self._path, len(self._data))
        return self._path

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._path and self._path.exists():
            try:
                self._path.unlink()
                logger.debug("Deleted temp file: %s", self._path)
            except OSError as e:
                logger.warning("Could not delete temp file %s: %s", self._path, e)


# ---------------------------------------------------------------------------
# Output path generation
# ---------------------------------------------------------------------------

def get_output_path(output_dir: Path, title: str) -> Path:
    """
    Generate a unique output file path for a presentation.
    Uses the sanitized title + a short UUID to avoid collisions.
    """
    from utils.text_utils import sanitize_filename
    base = sanitize_filename(title)
    stem = Path(base).stem
    unique_id = uuid.uuid4().hex[:6]
    filename = f"{stem}_{unique_id}.pptx"
    return output_dir / filename


def cleanup_old_outputs(output_dir: Path, keep_last: int = 10) -> None:
    """
    Remove old .pptx files from the output directory, keeping the N most recent.
    Prevents unbounded disk usage in long-running deployments.
    """
    try:
        pptx_files = sorted(
            output_dir.glob("*.pptx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_file in pptx_files[keep_last:]:
            old_file.unlink()
            logger.info("Cleaned up old output: %s", old_file.name)
    except Exception as e:
        logger.warning("Error during output cleanup: %s", e)
