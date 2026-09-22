"""
llm/json_utils.py — Provider-agnostic JSON extraction/retry helpers.

Shared by llm/groq_client.py and llm/watsonx_client.py so both LLM providers
use identical JSON-extraction and correction-retry behavior.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional

from utils.logging_utils import get_logger

logger = get_logger(__name__)


class JSONParseError(Exception):
    """LLM returned invalid JSON after all retries."""


def extract_json_from_text(text: str) -> str:
    """
    Try to extract a JSON object or array from raw LLM text.

    Strategies (in order):
    1. Strip markdown code fences (```json ... ```)
    2. Find the first { ... } or [ ... ] block
    3. Return the text as-is and let json.loads raise
    """
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```", re.IGNORECASE)
    match = fence_pattern.search(text)
    if match:
        return match.group(1).strip()

    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        return obj_match.group(0)

    arr_match = re.search(r"\[[\s\S]*\]", text)
    if arr_match:
        return arr_match.group(0)

    return text.strip()


def parse_json_response(raw: str) -> Dict[str, Any]:
    """Parse JSON from a raw LLM response, raising JSONParseError on failure."""
    extracted = extract_json_from_text(raw)
    try:
        return json.loads(extracted)
    except json.JSONDecodeError as e:
        raise JSONParseError(
            f"JSON decode failed: {e}\nExtracted text (first 500 chars): {extracted[:500]}"
        ) from e


def retry_json_completion(
    chat_complete_fn: Callable[..., str],
    messages: List[Dict[str, str]],
    max_retries: int,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Call chat_complete_fn repeatedly, parsing the response as JSON.

    On JSON parse failure, appends a correction turn to the conversation and
    retries up to max_retries times. Used by both GroqClient and WatsonxClient
    so the retry/correction behavior stays identical across providers.
    """
    from llm.prompts import JSON_CORRECTION_PROMPT

    last_error: Optional[Exception] = None
    current_messages = list(messages)
    raw_response = ""

    for attempt in range(1, max_retries + 1):
        try:
            raw_response = chat_complete_fn(
                current_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            data = parse_json_response(raw_response)
            if attempt > 1:
                logger.info("JSON parsed successfully on attempt %d", attempt)
            return data

        except JSONParseError as e:
            last_error = e
            logger.warning(
                "JSON parse failed on attempt %d/%d: %s",
                attempt,
                max_retries,
                str(e)[:200],
            )

            if attempt < max_retries:
                raw_snippet = raw_response[-1000:] if len(raw_response) > 1000 else raw_response
                correction_prompt = JSON_CORRECTION_PROMPT.format(
                    error_message=str(e)[:400],
                    invalid_json=raw_snippet,
                )
                current_messages = list(messages) + [
                    {"role": "assistant", "content": raw_snippet},
                    {"role": "user", "content": correction_prompt},
                ]
                time.sleep(1.0 * attempt)

    raise JSONParseError(
        f"Failed to obtain valid JSON after {max_retries} attempts. "
        f"Last error: {last_error}"
    ) from last_error
