"""
core/content_model_extractor.py — Stage 1: template-independent content extraction.

Produces a ContentModel (typed, traceable content items + relationships) from raw
source text. Knows nothing about any presentation template — reusable across all
template pipelines.
"""
from __future__ import annotations

from pydantic import ValidationError

from llm.content_model_schemas import ContentModel
from llm.groq_client import GroqClient, JSONParseError
from llm.prompts_content_model import SYSTEM_ROLE_CONTENT_EXTRACTOR, build_content_model_extraction_prompt
from utils.logging_utils import get_logger
from utils.text_utils import truncate_text

logger = get_logger(__name__)


def extract_content_model(
    client: GroqClient,
    source_text: str,
    max_source_chars: int = 12000,
) -> ContentModel:
    """Best-effort extraction: on any LLM/parse failure, returns an empty ContentModel
    rather than raising, so the presentation planner can always fall back to reading
    the raw source text directly instead of being blocked by this optional stage.
    """
    truncated_source = truncate_text(source_text, max_source_chars)
    prompt = build_content_model_extraction_prompt(source_content=truncated_source)
    messages = [
        {"role": "system", "content": SYSTEM_ROLE_CONTENT_EXTRACTOR},
        {"role": "user", "content": prompt},
    ]

    try:
        raw_data = client.chat_complete_json(messages=messages, temperature=0.2, max_tokens=4096)
        model = ContentModel.model_validate(raw_data)
    except (JSONParseError, ValidationError) as e:
        logger.warning("Content model extraction failed, continuing without it: %s", e)
        return ContentModel()
    except Exception as e:
        logger.warning("Content model extraction LLM call failed, continuing without it: %s", e)
        return ContentModel()

    logger.info(
        "Content model extracted: %d items, %d relationships.",
        len(model.content_items), len(model.relationships),
    )
    return model
