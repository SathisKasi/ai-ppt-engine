"""
llm/groq_client.py — Groq API wrapper with JSON extraction and retry logic.

Responsibilities:
- Wrap the Groq Python SDK for chat completions.
- Extract valid JSON from raw LLM responses (handles markdown fences, preamble).
- Retry on JSON parse failure with a correction prompt.
- Translate Groq SDK exceptions into application-level exceptions.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

from utils.logging_utils import get_logger
from llm.semantic_cache import SemanticCache
from utils.guardrails import sanitize_messages

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class GroqClientError(Exception):
    """Base exception for all Groq client errors."""


class GroqAuthError(GroqClientError):
    """Invalid or missing API key."""


class GroqRateLimitError(GroqClientError):
    """Rate limit exceeded."""


class GroqAPIError(GroqClientError):
    """Generic API error (network, server, etc.)."""


class JSONParseError(GroqClientError):
    """LLM returned invalid JSON after all retries."""


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def _extract_json_from_text(text: str) -> str:
    """
    Try to extract a JSON object or array from raw LLM text.

    Strategies (in order):
    1. Strip markdown code fences (```json ... ```)
    2. Find the first { ... } or [ ... ] block
    3. Return the text as-is and let json.loads raise
    """
    # Strip markdown fences
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```", re.IGNORECASE)
    match = fence_pattern.search(text)
    if match:
        return match.group(1).strip()

    # Find first JSON object
    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        return obj_match.group(0)

    # Find first JSON array
    arr_match = re.search(r"\[[\s\S]*\]", text)
    if arr_match:
        return arr_match.group(0)

    return text.strip()


def parse_json_response(raw: str) -> Dict[str, Any]:
    """Parse JSON from a raw LLM response, raising JSONParseError on failure."""
    extracted = _extract_json_from_text(raw)
    try:
        return json.loads(extracted)
    except json.JSONDecodeError as e:
        raise JSONParseError(
            f"JSON decode failed: {e}\nExtracted text (first 500 chars): {extracted[:500]}"
        ) from e


# ---------------------------------------------------------------------------
# Groq client
# ---------------------------------------------------------------------------

class GroqClient:
    """
    Thin wrapper around the Groq Python SDK.

    Usage:
        client = GroqClient(api_key="gsk_...", model="openai/gpt-oss-120b")
        raw = client.chat_complete(messages=[...])
        data = client.chat_complete_json(messages=[...])
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries: int = 3,
        semantic_cache: Optional[SemanticCache] = None,
    ) -> None:
        if not api_key or api_key.strip() == "":
            raise GroqAuthError(
                "Groq API key is missing. Set GROQ_API_KEY in your .env file "
                "or enter it in the sidebar."
            )

        try:
            from groq import Groq, APIStatusError, RateLimitError, AuthenticationError
            self._Groq = Groq
            self._APIStatusError = APIStatusError
            self._RateLimitError = RateLimitError
            self._AuthenticationError = AuthenticationError
            self._client = Groq(api_key=api_key.strip())
        except ImportError as e:
            raise GroqClientError(
                "groq package is not installed. Run: pip install groq"
            ) from e

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.semantic_cache = semantic_cache

    def chat_complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Send a chat completion request to Groq.
        Returns the raw text response.
        """
        _temp = temperature if temperature is not None else self.temperature
        _max_tok = max_tokens if max_tokens is not None else self.max_tokens
        messages = sanitize_messages(messages)

        logger.debug(
            "Groq request — model=%s temp=%.2f max_tokens=%d messages=%d",
            self.model,
            _temp,
            _max_tok,
            len(messages),
        )

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=_temp,
                max_tokens=_max_tok,
            )
            content = response.choices[0].message.content or ""
            logger.debug("Groq response length: %d chars", len(content))
            return content

        except self._AuthenticationError as e:
            raise GroqAuthError(
                "Authentication failed. Please check your Groq API key."
            ) from e

        except self._RateLimitError as e:
            raise GroqRateLimitError(
                "Groq rate limit exceeded. Please wait a moment and try again."
            ) from e

        except self._APIStatusError as e:
            raise GroqAPIError(
                f"Groq API error (status {e.status_code}): {e.message}"
            ) from e

        except Exception as e:
            raise GroqAPIError(f"Unexpected error calling Groq: {e}") from e

    def chat_complete_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request and parse the response as JSON.

        On JSON parse failure, sends a correction prompt and retries
        up to self.max_retries times.
        """
        from llm.prompts import JSON_CORRECTION_PROMPT

        last_error: Optional[Exception] = None
        current_messages = list(messages)
        raw_response = ""

        for attempt in range(1, self.max_retries + 1):
            try:
                cache_key = None
                if self.semantic_cache:
                    cache_key = self.semantic_cache.make_key(
                        "groq",
                        self.model,
                        current_messages,
                        temperature if temperature is not None else self.temperature,
                        max_tokens if max_tokens is not None else self.max_tokens,
                    )
                    cached_response = self.semantic_cache.get(cache_key)
                    if cached_response is not None:
                        logger.info("Semantic cache hit: model=%s", self.model)
                        return parse_json_response(cached_response)

                raw_response = self.chat_complete(
                    current_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                data = parse_json_response(raw_response)
                if self.semantic_cache and cache_key:
                    self.semantic_cache.put(cache_key, raw_response)
                if attempt > 1:
                    logger.info("JSON parsed successfully on attempt %d", attempt)
                return data

            except JSONParseError as e:
                last_error = e
                logger.warning(
                    "JSON parse failed on attempt %d/%d: %s",
                    attempt,
                    self.max_retries,
                    str(e)[:200],
                )

                if attempt < self.max_retries:
                    # Add correction turn to the conversation
                    correction_prompt = JSON_CORRECTION_PROMPT.format(
                        error_message=str(e)[:500],
                        invalid_json=raw_response[:2000],
                    )
                    current_messages = list(messages) + [
                        {"role": "assistant", "content": raw_response},
                        {"role": "user", "content": correction_prompt},
                    ]
                    # Brief back-off between retries
                    time.sleep(1.0 * attempt)

        raise JSONParseError(
            f"Failed to obtain valid JSON after {self.max_retries} attempts. "
            f"Last error: {last_error}"
        ) from last_error
