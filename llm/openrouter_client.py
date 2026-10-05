"""
llm/openrouter_client.py — OpenRouter API wrapper with multi-key load balancing and fallback.

Responsibilities:
- Call OpenRouter OpenAI-compatible chat completions API.
- Distribute requests across multiple OpenRouter API keys (round-robin load splitting).
- Failover across keys if any key encounters a rate limit (HTTP 429) or transient error.
- Extract valid JSON using shared json_utils.
- Record token usage via logging_utils.
"""

from __future__ import annotations

import json
import threading
import time
import warnings
from typing import Any, Dict, List, Optional, Union

import warnings
warnings.filterwarnings("ignore", message=".*urllib3.*or chardet.*")

import requests

from llm.json_utils import JSONParseError, parse_json_response, retry_json_completion
from utils.logging_utils import get_logger, log_llm_usage

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class OpenRouterClientError(Exception):
    """Base exception for all OpenRouter client errors."""


class OpenRouterAuthError(OpenRouterClientError):
    """Invalid or missing OpenRouter API key."""


class OpenRouterRateLimitError(OpenRouterClientError):
    """Rate limit exceeded on OpenRouter."""


class OpenRouterAPIError(OpenRouterClientError):
    """Generic OpenRouter API error."""


def _mask_key(api_key: str) -> str:
    """Return a log-safe identifier for an API key (last 4 chars only)."""
    key = (api_key or "").strip()
    return f"...{key[-4:]}" if len(key) > 4 else "..."


# ---------------------------------------------------------------------------
# OpenRouter Client
# ---------------------------------------------------------------------------

class OpenRouterClient:
    """
    Client for OpenRouter API with multi-key round-robin load distribution.

    Usage:
        client = OpenRouterClient(
            api_keys=["sk-or-v1-key1...", "sk-or-v1-key2..."],
            model="openai/gpt-oss-120b",
        )
        text = client.chat_complete(messages=[...])
        data = client.chat_complete_json(messages=[...])
    """

    def __init__(
        self,
        api_keys: Union[str, List[str]],
        model: str = "openai/gpt-oss-120b",
        url: str = "https://openrouter.ai/api/v1/chat/completions",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries: int = 3,
        timeout: int = 90,
    ) -> None:
        if isinstance(api_keys, str):
            raw_keys = [k.strip() for k in api_keys.split(",") if k.strip()]
        else:
            raw_keys = [k.strip() for k in api_keys if k and k.strip()]

        if not raw_keys:
            raise OpenRouterAuthError(
                "No OpenRouter API keys provided. Set OPENROUTER_API_KEYS in your .env file."
            )

        self.api_keys: List[str] = raw_keys
        self.model = model
        self.url = url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.timeout = timeout

        self._index = 0
        self._lock = threading.Lock()

        logger.info(
            "OpenRouterClient initialized with %d key(s) [model=%s, url=%s]",
            len(self.api_keys),
            self.model,
            self.url,
        )

    @property
    def key_count(self) -> int:
        return len(self.api_keys)

    def _get_next_key_info(self) -> tuple[int, str]:
        """Return the next key index (1-based) and key string in round-robin order."""
        with self._lock:
            idx = self._index % len(self.api_keys)
            self._index += 1
            return idx + 1, self.api_keys[idx]

    def chat_complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Send a chat completion request to OpenRouter.
        Cycles across keys in round-robin order to split load, and fails over
        to alternative keys if a key encounters rate limits.
        """
        _temp = temperature if temperature is not None else self.temperature
        _max_tok = max_tokens if max_tokens is not None else self.max_tokens

        total_keys = len(self.api_keys)
        last_error: Optional[Exception] = None

        # Attempt across available keys to distribute load and fail over if rate-limited
        for attempt_idx in range(total_keys):
            key_num, key = self._get_next_key_info()
            key_label = _mask_key(key)

            logger.info(
                "OpenRouter request — key #%d (%s) model=%s temp=%.2f max_tokens=%d messages=%d",
                key_num,
                key_label,
                self.model,
                _temp,
                _max_tok,
                len(messages),
            )

            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://localhost/ai-ppt-engine",
                "X-Title": "ai-ppt-engine",
            }

            payload: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": _temp,
                "max_tokens": _max_tok,
            }
            if "gpt-oss" in self.model:
                payload["reasoning"] = {"effort": "low"}

            try:
                response = requests.post(
                    self.url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    resp_json = response.json()
                    choices = resp_json.get("choices", [])
                    if not choices:
                        raise OpenRouterAPIError("OpenRouter returned empty choices list.")

                    content = choices[0].get("message", {}).get("content") or ""
                    usage = resp_json.get("usage", {})
                    log_llm_usage(
                        provider="openrouter",
                        key_number=key_num,
                        key_label=key_label,
                        model=self.model,
                        prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"),
                        total_tokens=usage.get("total_tokens"),
                    )
                    logger.debug("OpenRouter response length: %d chars (key #%d)", len(content), key_num)
                    return content

                if response.status_code == 429:
                    logger.warning(
                        "OpenRouter rate limit on key #%d (%s) [status 429]. Attempting next key...",
                        key_num,
                        key_label,
                    )
                    last_error = OpenRouterRateLimitError(
                        f"OpenRouter rate limit on key #{key_num} ({key_label}): {response.text[:200]}"
                    )
                    continue

                if response.status_code in (401, 403):
                    logger.warning(
                        "OpenRouter authentication failure on key #%d (%s) [status %d]. Attempting next key...",
                        key_num,
                        key_label,
                        response.status_code,
                    )
                    last_error = OpenRouterAuthError(
                        f"OpenRouter auth failure on key #{key_num}: {response.text[:200]}"
                    )
                    continue

                if response.status_code >= 500:
                    logger.warning(
                        "OpenRouter server error (status %d) on key #%d (%s). Attempting next key...",
                        response.status_code,
                        key_num,
                        key_label,
                    )
                    last_error = OpenRouterAPIError(
                        f"OpenRouter server error {response.status_code}: {response.text[:200]}"
                    )
                    continue

                raise OpenRouterAPIError(
                    f"OpenRouter API error (status {response.status_code}): {response.text[:300]}"
                )

            except requests.RequestException as req_err:
                logger.warning(
                    "Network error connecting to OpenRouter on key #%d (%s): %s. Attempting next key...",
                    key_num,
                    key_label,
                    req_err,
                )
                last_error = OpenRouterAPIError(f"Network error calling OpenRouter: {req_err}")
                continue

        if last_error:
            raise last_error

        raise OpenRouterAPIError("All OpenRouter API keys exhausted without success.")

    def chat_complete_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request to OpenRouter and parse the response as JSON.
        On JSON parse failure, sends a correction prompt and retries up to self.max_retries times.
        """
        return retry_json_completion(
            self.chat_complete,
            messages,
            self.max_retries,
            temperature=temperature,
            max_tokens=max_tokens,
        )
