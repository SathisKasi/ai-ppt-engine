"""
llm/groq_client.py — Groq API wrapper with JSON extraction and retry logic.

Responsibilities:
- Wrap the Groq Python SDK for chat completions.
- Extract valid JSON from raw LLM responses (handles markdown fences, preamble).
- Retry on JSON parse failure with a correction prompt.
- Translate Groq SDK exceptions into application-level exceptions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from llm.json_utils import JSONParseError, parse_json_response, retry_json_completion
from utils.logging_utils import get_logger, log_llm_usage

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


# JSONParseError, parse_json_response re-exported from llm.json_utils for
# backward compatibility with existing `from llm.groq_client import JSONParseError` call sites.


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
        key_number: Optional[int] = None,
        openrouter_client: Optional[Any] = None,
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
        self.key_number = key_number
        self._key_label = f"...{api_key.strip()[-4:]}" if len(api_key.strip()) > 4 else "..."

        self.openrouter_client = openrouter_client
        if self.openrouter_client is None:
            try:
                import config
                if getattr(config, "OPENROUTER_API_KEYS", None):
                    from llm.openrouter_client import OpenRouterClient
                    self.openrouter_client = OpenRouterClient(
                        api_keys=config.OPENROUTER_API_KEYS,
                        model=getattr(config, "OPENROUTER_MODEL", "openai/gpt-oss-120b"),
                        url=getattr(config, "OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions"),
                        temperature=temperature,
                        max_tokens=max_tokens,
                        max_retries=max_retries,
                    )
            except Exception as e:
                logger.debug("Could not auto-initialize OpenRouter fallback client: %s", e)

    def _is_rate_or_capacity_error(self, exc: Exception) -> tuple[bool, str]:
        """
        Check if an error represents a rate limit, TPM quota, request size limit,
        or service capacity issue that should fail over to OpenRouter.
        """
        if not self.openrouter_client:
            return False, "no OpenRouter client configured"

        # 1. Direct RateLimitError from SDK
        if self._RateLimitError and isinstance(exc, self._RateLimitError):
            return True, "RateLimitError"

        # 2. APIStatusError with status codes:
        # 429 (Too Many Requests / Rate Limit)
        # 413 (Payload Too Large / TPM tokens limit exceeded)
        # 503 (Service Unavailable / Capacity overloaded)
        status = getattr(exc, "status_code", None)
        if status in (413, 429, 503):
            return True, f"HTTP status {status}"

        # 3. Check error body if available
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            err_dict = body.get("error", {})
            if isinstance(err_dict, dict):
                code = str(err_dict.get("code", "")).lower()
                err_type = str(err_dict.get("type", "")).lower()
                msg = str(err_dict.get("message", "")).lower()
                if "rate_limit" in code or "token" in err_type or "too large" in msg or "tpm" in msg:
                    return True, f"Groq error code='{code}', type='{err_type}'"

        # 4. Check error string representation
        err_str = str(exc).lower()
        trigger_phrases = (
            "rate limit",
            "rate_limit_exceeded",
            "request too large",
            "tokens per minute",
            "tpm",
            "status 413",
            "status 429",
            "error code: 413",
            "error code: 429",
            "limit 8000",
            "service tier on_demand",
        )
        for phrase in trigger_phrases:
            if phrase in err_str:
                return True, f"matched '{phrase}' in error"

        return False, ""

    def _fallback_to_openrouter(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        reason: str = "Rate limit",
    ) -> str:
        """Call OpenRouter fallback when Groq rate or capacity limits are exceeded."""
        if not self.openrouter_client:
            raise GroqRateLimitError(f"Groq limit exceeded ({reason}), and no OpenRouter backup configured.")
        logger.warning(
            "Groq limit exceeded on key #%s (%s) [%s] — failing over to OpenRouter (model=%s, %d keys active)",
            self.key_number,
            self._key_label,
            reason,
            self.openrouter_client.model,
            self.openrouter_client.key_count,
        )
        return self.openrouter_client.chat_complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def chat_complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Send a chat completion request to Groq.
        Returns the raw text response.
        If Groq rate limit, TPM quota, or HTTP 413 is encountered, transparently fails over to OpenRouter.
        """
        _temp = temperature if temperature is not None else self.temperature
        _max_tok = max_tokens if max_tokens is not None else self.max_tokens

        logger.debug(
            "Groq request — model=%s temp=%.2f max_tokens=%d messages=%d",
            self.model,
            _temp,
            _max_tok,
            len(messages),
        )

        extra_kwargs = {}
        if "gpt-oss" in self.model:
            extra_kwargs["extra_body"] = {"reasoning_effort": "low"}

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=_temp,
                max_tokens=_max_tok,
                **extra_kwargs,
            )
            content = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            log_llm_usage(
                provider="groq",
                key_number=self.key_number,
                key_label=self._key_label,
                model=self.model,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            )
            logger.debug("Groq response length: %d chars", len(content))
            return content

        except self._AuthenticationError as e:
            raise GroqAuthError(
                "Authentication failed. Please check your Groq API key."
            ) from e

        except self._RateLimitError as e:
            if self.openrouter_client:
                try:
                    return self._fallback_to_openrouter(
                        messages=messages,
                        temperature=_temp,
                        max_tokens=_max_tok,
                        reason="RateLimitError",
                    )
                except Exception as or_err:
                    logger.error("OpenRouter fallback failed after Groq rate limit: %s", or_err)
                    raise GroqRateLimitError(
                        f"Groq rate limit exceeded and OpenRouter fallback failed: {or_err}"
                    ) from or_err
            raise GroqRateLimitError(
                "Groq rate limit exceeded. Please wait a moment and try again."
            ) from e

        except self._APIStatusError as e:
            is_limit, reason = self._is_rate_or_capacity_error(e)
            if is_limit:
                try:
                    return self._fallback_to_openrouter(
                        messages=messages,
                        temperature=_temp,
                        max_tokens=_max_tok,
                        reason=reason,
                    )
                except Exception as or_err:
                    logger.error("OpenRouter fallback failed after Groq API status error (%s): %s", reason, or_err)
                    raise GroqRateLimitError(
                        f"Groq limit exceeded ({reason}) and OpenRouter fallback failed: {or_err}"
                    ) from or_err
            raise GroqAPIError(
                f"Groq API error (status {e.status_code}): {e.message}"
            ) from e

        except Exception as e:
            is_limit, reason = self._is_rate_or_capacity_error(e)
            if is_limit:
                try:
                    return self._fallback_to_openrouter(
                        messages=messages,
                        temperature=_temp,
                        max_tokens=_max_tok,
                        reason=reason,
                    )
                except Exception as or_err:
                    logger.error("OpenRouter fallback failed after Groq error (%s): %s", reason, or_err)
                    raise GroqRateLimitError(
                        f"Groq limit encountered ({reason}) and OpenRouter fallback failed: {or_err}"
                    ) from or_err
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
        return retry_json_completion(
            self.chat_complete,
            messages,
            self.max_retries,
            temperature=temperature,
            max_tokens=max_tokens,
        )
