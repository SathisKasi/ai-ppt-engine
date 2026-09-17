"""
llm/watsonx_client.py — IBM watsonx.ai wrapper mirroring the GroqClient interface.

Responsibilities:
- Wrap the ibm-watsonx-ai SDK's chat completions API.
- Reuse the shared JSON extraction/retry logic from llm/json_utils.py.
- Translate watsonx SDK/HTTP errors into application-level exceptions.

Usage:
    client = WatsonxClient(
        api_key="...",
        project_id="...",
        url="https://us-south.ml.cloud.ibm.com",
        model="openai/gpt-oss-120b",
    )
    raw = client.chat_complete(messages=[...])
    data = client.chat_complete_json(messages=[...])
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from llm.json_utils import JSONParseError, retry_json_completion
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Base delay (seconds) for exponential backoff on 429/consumption-limit responses.
RATE_LIMIT_BACKOFF_BASE_SECONDS = 5.0

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class WatsonxClientError(Exception):
    """Base exception for all watsonx client errors."""


class WatsonxAuthError(WatsonxClientError):
    """Invalid or missing API key / project ID."""


class WatsonxRateLimitError(WatsonxClientError):
    """Rate limit or quota exceeded."""


class WatsonxAPIError(WatsonxClientError):
    """Generic API error (network, server, etc.)."""


# ---------------------------------------------------------------------------
# watsonx client
# ---------------------------------------------------------------------------

class WatsonxClient:
    """
    Thin wrapper around the ibm-watsonx-ai SDK's chat completion API.

    Exposes the same public interface as GroqClient (chat_complete /
    chat_complete_json) so it can be used as a drop-in replacement anywhere
    a GroqClient is currently accepted.
    """

    def __init__(
        self,
        api_key: str,
        project_id: str,
        url: str,
        model: str = "openai/gpt-oss-120b",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries: int = 3,
    ) -> None:
        if not api_key or api_key.strip() == "":
            raise WatsonxAuthError(
                "watsonx API key is missing. Set WATSONX_API_KEY in your .env file."
            )
        if not project_id or project_id.strip() == "":
            raise WatsonxAuthError(
                "watsonx project ID is missing. Set WATSONX_PROJECT_ID in your .env file."
            )
        if not url or url.strip() == "":
            raise WatsonxAuthError(
                "watsonx service URL is missing. Set WATSONX_URL in your .env file."
            )

        try:
            from ibm_watsonx_ai import Credentials, APIClient
            from ibm_watsonx_ai.foundation_models import ModelInference
        except ImportError as e:
            raise WatsonxClientError(
                "ibm-watsonx-ai package is not installed. Run: pip install ibm-watsonx-ai"
            ) from e

        try:
            credentials = Credentials(url=url.strip(), api_key=api_key.strip())
            api_client = APIClient(credentials, project_id=project_id.strip())
            self._model_inference = ModelInference(
                model_id=model,
                api_client=api_client,
                # Disable the SDK's own internal retry-on-429 (defaults to up to 10
                # retries with exponential backoff) — our chat_complete() loop below
                # already handles rate-limit retries, and letting both retry would
                # compound into multi-minute waits per call.
                max_retries=0,
            )
        except Exception as e:
            raise WatsonxAuthError(
                f"Failed to initialize watsonx client (check API key / project ID / URL): {e}"
            ) from e

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries

    def _classify_error(self, e: Exception) -> Exception:
        """Map an ibm-watsonx-ai SDK exception to an application-level exception."""
        # The SDK doesn't expose a status_code attribute — the HTTP status and
        # error body are embedded in the exception's message text.
        status_code = getattr(e, "status_code", None) or getattr(e, "http_status_code", None)
        msg = str(e)
        lowered = msg.lower()
        if status_code is None:
            status_match = re.search(r"status code:\s*(\d+)", lowered)
            if status_match:
                status_code = int(status_match.group(1))

        if status_code == 401 or "unauthorized" in lowered or "authentication" in lowered:
            return WatsonxAuthError(
                f"Authentication failed. Please check your watsonx API key/project ID: {e}"
            )

        if (
            status_code == 429
            or "rate limit" in lowered
            or "quota" in lowered
            or "too many requests" in lowered
            or "consumption_limit_reached" in lowered
            or "usage limit" in lowered
        ):
            return WatsonxRateLimitError(
                "watsonx rate limit/quota exceeded. Please wait a moment and try again."
            )

        return WatsonxAPIError(f"Unexpected error calling watsonx: {e}")

    def chat_complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Send a chat completion request to watsonx.ai.
        Returns the raw text response.

        Automatically retries with exponential backoff when the account's free-tier
        concurrent-request limit (HTTP 429 / consumption_limit_reached) is hit, since
        that condition typically clears within a few seconds.
        """
        _temp = temperature if temperature is not None else self.temperature
        _max_tok = max_tokens if max_tokens is not None else self.max_tokens

        logger.debug(
            "watsonx request — model=%s temp=%.2f max_tokens=%d messages=%d",
            self.model,
            _temp,
            _max_tok,
            len(messages),
        )

        params = {
            "temperature": _temp,
            "max_tokens": _max_tok,
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._model_inference.chat(messages=messages, params=params)
                choice = response["choices"][0]
                message = choice["message"]
                content = message.get("content") or ""
                if not content:
                    # Reasoning models (e.g. gpt-oss) can exhaust max_tokens on hidden
                    # chain-of-thought before emitting final content.
                    logger.warning(
                        "watsonx returned empty content (finish_reason=%s). "
                        "If this recurs, increase max_tokens for model %s.",
                        choice.get("finish_reason"),
                        self.model,
                    )
                logger.debug("watsonx response length: %d chars", len(content))
                return content

            except Exception as e:
                classified = self._classify_error(e)
                last_error = classified

                if isinstance(classified, WatsonxRateLimitError) and attempt < self.max_retries:
                    delay = RATE_LIMIT_BACKOFF_BASE_SECONDS * attempt
                    logger.warning(
                        "watsonx rate limited (attempt %d/%d) — retrying in %.1fs",
                        attempt, self.max_retries, delay,
                    )
                    time.sleep(delay)
                    continue

                raise classified from e

        raise last_error  # pragma: no cover — loop always returns or raises

    def chat_complete_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request and parse the response as JSON.

        On JSON parse failure, sends a correction prompt and retries
        up to self.max_retries times (shared logic with GroqClient).
        """
        return retry_json_completion(
            self.chat_complete,
            messages,
            self.max_retries,
            temperature=temperature,
            max_tokens=max_tokens,
        )
