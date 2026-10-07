"""
config.py — Application-wide configuration and constants.

All settings are read from environment variables (via python-dotenv).
Never hardcode sensitive values here.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project paths & PyInstaller frozen execution support
# ---------------------------------------------------------------------------
import sys

IS_FROZEN = getattr(sys, "frozen", False)
if IS_FROZEN:
    # Directory containing the executable (for user files: .env, output/, logs/)
    APP_DIR = Path(sys.executable).resolve().parent
    # Directory containing internal bundled assets (_internal or temp _MEIPASS)
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
    if not BUNDLE_DIR.is_dir():
        BUNDLE_DIR = BUNDLE_DIR.parent
else:
    APP_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = APP_DIR

PROJECT_ROOT = APP_DIR

def resolve_asset_path(relative_path: str | Path) -> Path:
    """Resolve an asset path: checks APP_DIR first, then falls back to BUNDLE_DIR."""
    rel = Path(relative_path)
    user_path = APP_DIR / rel
    if user_path.exists():
        return user_path
    bundle_path = BUNDLE_DIR / rel
    if bundle_path.exists():
        return bundle_path
    return user_path

# Load .env (first from APP_DIR, fallback to BUNDLE_DIR)
_env_path = APP_DIR / ".env"
if not _env_path.exists() and (BUNDLE_DIR / ".env").exists():
    _env_path = BUNDLE_DIR / ".env"
load_dotenv(_env_path, override=True)

TEMPLATES_DIR = resolve_asset_path("templates")
OUTPUT_DIR = APP_DIR / os.getenv("OUTPUT_DIR", "output")
TEMPLATE_FILE = resolve_asset_path("templates/presentation_template.pptx")
LAYOUT_METADATA_FILE = resolve_asset_path("templates/layout_metadata.json")

# Additional template files
TECHM_TEMPLATE_FILE = resolve_asset_path("templates/techm_template.pptx")
WHITE_BLUE_TEMPLATE_FILE = resolve_asset_path("templates/white_blue_template.pptx")
TECHM_V3_TEMPLATE_FILE = resolve_asset_path("TechM_RefPPT-V3.pptx")
TEMPLATE1_FILE = resolve_asset_path("AITransformationWeeklyUpdate4SEP2026.pptx")
HLD_QBR_TEMPLATE_FILE = resolve_asset_path("templates/hld_qbr_template.pptx")
HLD_QBR_CATALOG_FILE = resolve_asset_path("templates/hld_qbr_assets/inventory/layout_capability_catalog.json")

# LLM analysis logs directory
LOGS_DIR: Path = APP_DIR / "logs" / "llm"

# Ensure directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# LLM provider selection
# ---------------------------------------------------------------------------
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq").strip().lower()  # "groq" | "watsonx"

# ---------------------------------------------------------------------------
# Groq / LLM settings
# ---------------------------------------------------------------------------
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_MAX_TOKENS_PLAN: int = int(os.getenv("GROQ_MAX_TOKENS_PLAN", "4096"))
GROQ_MAX_TOKENS_SLIDE: int = int(os.getenv("GROQ_MAX_TOKENS_SLIDE", "2048"))
GROQ_TEMPERATURE: float = float(os.getenv("GROQ_TEMPERATURE", "0.3"))
LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))

# Multiple API keys (comma-separated). Falls back to GROQ_API_KEY if only one.
_raw_keys = os.getenv("GROQ_API_KEYS", "")
GROQ_API_KEYS: list[str] = [
    k.strip() for k in _raw_keys.split(",") if k.strip()
] if _raw_keys else ([GROQ_API_KEY] if GROQ_API_KEY else [])

# ---------------------------------------------------------------------------
# OpenRouter settings (Fallback for Groq rate limits)
# ---------------------------------------------------------------------------
OPENROUTER_URL: str = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b")
_raw_openrouter_keys = os.getenv("OPENROUTER_API_KEYS", "")
OPENROUTER_API_KEYS: list[str] = [
    k.strip() for k in _raw_openrouter_keys.split(",") if k.strip()
] if _raw_openrouter_keys else ([os.getenv("OPENROUTER_API_KEY", "").strip()] if os.getenv("OPENROUTER_API_KEY", "").strip() else [])

# ---------------------------------------------------------------------------
# IBM watsonx.ai settings
# ---------------------------------------------------------------------------
WATSONX_API_KEY: str = os.getenv("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID: str = os.getenv("WATSONX_PROJECT_ID", "")
WATSONX_URL: str = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
WATSONX_MODEL_ID: str = os.getenv("WATSONX_MODEL_ID", "meta-llama/llama-3-3-70b-instruct")
# Used when the primary model hits a 429/consumption_limit_reached after all retries.
WATSONX_FALLBACK_MODEL_ID: str = os.getenv("WATSONX_FALLBACK_MODEL_ID", "ibm/granite-4-h-small")
WATSONX_MAX_TOKENS_PLAN: int = int(os.getenv("WATSONX_MAX_TOKENS_PLAN", "4096"))
WATSONX_MAX_TOKENS_SLIDE: int = int(os.getenv("WATSONX_MAX_TOKENS_SLIDE", "2048"))
WATSONX_TEMPERATURE: float = float(os.getenv("WATSONX_TEMPERATURE", "0.3"))

# Multiple API keys (comma-separated). Falls back to WATSONX_API_KEY if only one.
_raw_watsonx_keys = os.getenv("WATSONX_API_KEYS", "")
WATSONX_API_KEYS: list[str] = [
    k.strip() for k in _raw_watsonx_keys.split(",") if k.strip()
] if _raw_watsonx_keys else ([WATSONX_API_KEY] if WATSONX_API_KEY else [])

# Per-key project IDs (comma-separated, same order as WATSONX_API_KEYS) — lets each
# collaborator's key bill against their own project instead of a single shared one.
# Falls back to WATSONX_PROJECT_ID for every key when not set.
_raw_watsonx_project_ids = os.getenv("WATSONX_PROJECT_IDS", "")
WATSONX_PROJECT_IDS: list[str] = [
    p.strip() for p in _raw_watsonx_project_ids.split(",") if p.strip()
] if _raw_watsonx_project_ids else ([WATSONX_PROJECT_ID] if WATSONX_PROJECT_ID else [])

# ---------------------------------------------------------------------------
# Semantic chunking settings
# ---------------------------------------------------------------------------
# Safety cap: only used when a semantic section is too large.
# Primary chunking is always heading/sub-heading based.
LLM_MAX_CHUNK_CHARS: int = int(os.getenv("LLM_MAX_CHUNK_CHARS", "8000"))
# Sections smaller than this are merged with siblings before chunking.
LLM_MIN_SECTION_CHARS: int = int(os.getenv("LLM_MIN_SECTION_CHARS", "300"))

# ---------------------------------------------------------------------------
# Upload / processing limits
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20"))
MAX_UPLOAD_SIZE_BYTES: int = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_SOURCE_TEXT_CHARS: int = int(os.getenv("MAX_SOURCE_TEXT_CHARS", "12000"))
SUPPORTED_FILE_TYPES: list[str] = ["txt", "pdf", "docx", "pptx", "xlsx"]

# ---------------------------------------------------------------------------
# Layout identifiers — single source of truth
# ---------------------------------------------------------------------------
LAYOUT_REGISTRY: dict[str, str] = {
    "TITLE": "title",
    "TITLE_AND_CONTENT": "title_content",
    "TWO_COLUMN": "two_column",
    "SECTION_HEADER": "section_header",
    "IMAGE_TEXT": "image_text",
    "COMPARISON": "comparison",
    "TIMELINE": "timeline",
    "PROCESS": "process",
    "ARCHITECTURE": "architecture",
    "STATISTICS": "statistics",
    "CONCLUSION": "conclusion",
}

FALLBACK_LAYOUT: str = "TITLE_AND_CONTENT"

# ---------------------------------------------------------------------------
# Slide count limits
# ---------------------------------------------------------------------------
MIN_SLIDES: int = 3
MAX_SLIDES: int = 30
DEFAULT_SLIDES: int = 10

# ---------------------------------------------------------------------------
# Presentation style options
# ---------------------------------------------------------------------------
AUDIENCE_OPTIONS: list[str] = ["General", "Business", "Technical", "Executive", "Educational"]
STYLE_OPTIONS: list[str] = ["Professional", "Executive", "Educational", "Technical", "Creative"]
LANGUAGE_OPTIONS: list[str] = [
    "English", "Spanish", "French", "German", "Portuguese",
    "Italian", "Dutch", "Japanese", "Chinese (Simplified)", "Arabic",
]

# ---------------------------------------------------------------------------
# Font settings (used in programmatic template generation)
# ---------------------------------------------------------------------------
FONT_TITLE_SIZE: int = 40        # pt
FONT_SUBTITLE_SIZE: int = 24     # pt
FONT_HEADING_SIZE: int = 28      # pt
FONT_BODY_SIZE: int = 18         # pt
FONT_SMALL_SIZE: int = 14        # pt
FONT_MIN_SIZE: int = 10          # minimum auto-shrink limit

FONT_FAMILY: str = "Calibri"

# ---------------------------------------------------------------------------
# Theme colors (dark professional theme)
# ---------------------------------------------------------------------------
COLOR_BACKGROUND = "1A1A2E"     # Deep navy
COLOR_ACCENT_1 = "16213E"       # Darker navy
COLOR_ACCENT_2 = "0F3460"       # Mid blue
COLOR_HIGHLIGHT = "533483"      # Purple highlight
COLOR_TEXT_LIGHT = "E0E0E0"     # Off-white
COLOR_TEXT_WHITE = "FFFFFF"     # Pure white
COLOR_TEXT_DARK = "1A1A2E"      # Dark for light backgrounds
COLOR_BULLET_ACCENT = "E94560"  # Vibrant red-pink for accents

# ---------------------------------------------------------------------------
# App metadata
# ---------------------------------------------------------------------------
APP_TITLE = "AI PowerPoint Generator"
APP_SUBTITLE = "Transform documents and ideas into professional presentations"
APP_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Environment / Key management helpers
# ---------------------------------------------------------------------------
def update_env_variable(key: str, value: str) -> None:
    """Safely update or append a key=value pair in the local .env file."""
    env_file = APP_DIR / ".env"
    lines = []
    found = False
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                new_lines.append(f"{key}={value}")
                found = True
            else:
                new_lines.append(line)
        lines = new_lines

    if not found:
        lines.append(f"{key}={value}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value


def reload_keys() -> None:
    """Reload API keys and provider configuration from environment variables."""
    global LLM_PROVIDER, GROQ_API_KEY, GROQ_API_KEYS, WATSONX_API_KEY, WATSONX_API_KEYS, WATSONX_PROJECT_ID, OPENROUTER_API_KEYS
    env_file = APP_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
    
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "watsonx").strip().lower()
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    _raw_keys = os.getenv("GROQ_API_KEYS", "")
    GROQ_API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()] if _raw_keys else ([GROQ_API_KEY] if GROQ_API_KEY else [])
    
    WATSONX_API_KEY = os.getenv("WATSONX_API_KEY", "")
    _raw_wx_keys = os.getenv("WATSONX_API_KEYS", "")
    WATSONX_API_KEYS = [k.strip() for k in _raw_wx_keys.split(",") if k.strip()] if _raw_wx_keys else ([WATSONX_API_KEY] if WATSONX_API_KEY else [])
    WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")

    _raw_or_keys = os.getenv("OPENROUTER_API_KEYS", "")
    OPENROUTER_API_KEYS = [k.strip() for k in _raw_or_keys.split(",") if k.strip()] if _raw_or_keys else ([os.getenv("OPENROUTER_API_KEY", "").strip()] if os.getenv("OPENROUTER_API_KEY", "").strip() else [])

