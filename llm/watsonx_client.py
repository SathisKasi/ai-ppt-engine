"""watsonx.ai chat client with JSON parsing and retry support."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

from llm.groq_client import JSONParseError, parse_json_response
from utils.logging_utils import get_logger

logger = get_logger(__name__)


class WatsonxClientError(Exception):
    """Base exception for watsonx.ai client errors."""


class WatsonxAuthError(WatsonxClientError):
    """Invalid or missing IBM Cloud credentials."""


class WatsonxRateLimitError(WatsonxClientError):
    """watsonx.ai rate limit exceeded."""


class WatsonxAPIError(WatsonxClientError):
    """Generic watsonx.ai API or network error."""


class WatsonxClient:
    """Small REST client matching the application's LLM client contract."""

    def __init__(
        self,
        api_key: str,
        project_id: str,
        model: str = "ibm/granite-3-8b-instruct",
        url: str = "https://us-south.ml.cloud.ibm.com",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries: int = 3,
        timeout: int = 120,
    ) -> None:
        if not api_key.strip():
            raise WatsonxAuthError("WATSONX_API_KEY is missing.")
        if not project_id.strip():
            raise WatsonxAuthError("WATSONX_PROJECT_ID is missing.")

        self.api_key = api_key.strip()
        self.project_id = project_id.strip()
        self.model = model
        self.url = url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.timeout = timeout
        self._access_token: Optional[str] = None

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        try:
            response = requests.post(
                "https://iam.cloud.ibm.com/identity/token",
                data={
                    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                    "apikey": self.api_key,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
        except requests.RequestException as error:
            raise WatsonxAPIError(f"Could not reach IBM IAM: {error}") from error

        if response.status_code in (400, 401, 403):
            raise WatsonxAuthError("IBM Cloud authentication failed. Check WATSONX_API_KEY.")
        if not response.ok:
            raise WatsonxAPIError(f"IBM IAM returned HTTP {response.status_code}.")

        try:
            self._access_token = response.json()["access_token"]
        except (ValueError, KeyError) as error:
            raise WatsonxAPIError("IBM IAM returned an invalid token response.") from error
        return self._access_token

    def chat_complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Send a chat request and return the generated text."""
        parameters: Dict[str, Any] = {
            "decoding_method": "greedy",
            "max_new_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        payload = {
            "model_id": self.model,
            "project_id": self.project_id,
            "messages": messages,
            "parameters": parameters,
        }
        endpoint = f"{self.url}/ml/v1/text/chat?version=2024-10-08"

        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._get_access_token()}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise WatsonxAPIError(f"Could not reach watsonx.ai: {error}") from error

        if response.status_code in (401, 403):
            self._access_token = None
            raise WatsonxAuthError("watsonx.ai authorization failed. Check project access and credentials.")
        if response.status_code == 429:
            raise WatsonxRateLimitError("watsonx.ai rate limit exceeded. Please retry shortly.")
        if not response.ok:
            detail = response.text[:500]
            raise WatsonxAPIError(f"watsonx.ai returned HTTP {response.status_code}: {detail}")

        try:
            result = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise WatsonxAPIError("watsonx.ai returned an unexpected chat response.") from error
        return result or ""

    def chat_complete_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send a chat request and retry when the model returns invalid JSON."""
        from llm.prompts import JSON_CORRECTION_PROMPT

        last_error: Optional[Exception] = None
        current_messages = list(messages)
        raw_response = ""

        for attempt in range(1, self.max_retries + 1):
            try:
                raw_response = self.chat_complete(current_messages, temperature, max_tokens)
                return parse_json_response(raw_response)
            except JSONParseError as error:
                last_error = error
                if attempt < self.max_retries:
                    current_messages = list(messages) + [
                        {"role": "assistant", "content": raw_response},
                        {"role": "user", "content": JSON_CORRECTION_PROMPT.format(
                            error_message=str(error)[:500],
                            invalid_json=raw_response[:2000],
                        )},
                    ]
                    time.sleep(float(attempt))

        raise JSONParseError(
            f"Failed to obtain valid JSON after {self.max_retries} attempts. Last error: {last_error}"
        ) from last_error