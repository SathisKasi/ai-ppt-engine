"""
llm/key_manager.py — Multi-API-key round-robin manager.

Distributes Groq API calls across multiple keys so that:
- Different document sections use different keys
- No single key is rate-limited during parallel/sequential section analysis
- Keys cycle deterministically by chunk index

Usage:
    km = KeyManager(config.GROQ_API_KEYS, config.GROQ_MODEL)
    client = km.get_client(chunk_index=3)   # uses key[3 % len(keys)]
    key    = km.next_key()                  # stateful round-robin
"""

from __future__ import annotations

import threading
from typing import List, Optional

from utils.logging_utils import get_logger

logger = get_logger(__name__)


def _mask_key(api_key: str) -> str:
    """Return a log-safe identifier for an API key (last 4 chars only)."""
    key = (api_key or "").strip()
    return f"...{key[-4:]}" if len(key) > 4 else "..."


class KeyManagerError(Exception):
    """Raised when no keys are available."""


class KeyManager:
    """
    Thread-safe round-robin API key manager.

    Keys are rotated per request so that sequential section analyses
    automatically spread load across all provided API keys.
    """

    def __init__(self, keys: List[str], model: str, temperature: float = 0.3,
                 max_tokens: int = 2048, max_retries: int = 3, provider: str = "groq",
                 project_id: Optional[str] = None, project_ids: Optional[List[str]] = None,
                 url: Optional[str] = None, fallback_model: Optional[str] = None,
                 openrouter_keys: Optional[List[str]] = None,
                 openrouter_url: Optional[str] = None,
                 openrouter_model: Optional[str] = None) -> None:
        valid = [k.strip() for k in keys if k and k.strip()]
        if not valid:
            raise KeyManagerError("No valid API keys provided.")
        self._keys = valid
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._provider = (provider or "groq").strip().lower()
        self._project_id = project_id
        # Optional per-key project IDs (same order as `keys`) so each collaborator's
        # key bills against their own watsonx project instead of a shared one.
        valid_project_ids = [p.strip() for p in (project_ids or []) if p and p.strip()]
        self._project_ids = valid_project_ids or None
        self._url = url
        self._fallback_model = fallback_model
        self._index = 0
        self._lock = threading.Lock()

        # Shared OpenRouter fallback client for Groq rate limits
        self._openrouter_client = None
        or_keys = openrouter_keys
        if or_keys is None:
            try:
                import config
                or_keys = getattr(config, "OPENROUTER_API_KEYS", None)
            except Exception:
                or_keys = None

        if or_keys:
            try:
                from llm.openrouter_client import OpenRouterClient
                import config
                self._openrouter_client = OpenRouterClient(
                    api_keys=or_keys,
                    model=openrouter_model or getattr(config, "OPENROUTER_MODEL", "openai/gpt-oss-120b"),
                    url=openrouter_url or getattr(config, "OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions"),
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_retries=max_retries,
                )
                logger.info(
                    "KeyManager initialized with OpenRouter backup (%d keys, model=%s)",
                    self._openrouter_client.key_count,
                    self._openrouter_client.model,
                )
            except Exception as exc:
                logger.warning("Failed to initialize OpenRouter backup in KeyManager: %s", exc)

        logger.info(
            "KeyManager initialized with %d key(s) [provider=%s, per_key_projects=%s, openrouter_backup=%s]",
            len(self._keys), self._provider, bool(self._project_ids), bool(self._openrouter_client),
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def next_key(self) -> str:
        """Return the next key in round-robin order (stateful)."""
        with self._lock:
            key = self._keys[self._index % len(self._keys)]
            self._index += 1
            return key

    def key_for_index(self, idx: int) -> str:
        """Return the key assigned to a given (zero-based) chunk index."""
        return self._keys[idx % len(self._keys)]

    def project_id_for_index(self, idx: int) -> Optional[str]:
        """Return the watsonx project ID paired with the key at this index."""
        if self._project_ids:
            return self._project_ids[idx % len(self._project_ids)]
        return self._project_id

    def get_client(self, chunk_index: Optional[int] = None, max_tokens: Optional[int] = None):
        """
        Return an LLM client (GroqClient, WatsonxClient, or OpenRouterClient per configured provider)
        bound to the key for this chunk.

        Args:
            chunk_index: Zero-based index of the chunk (determines key).
                         If None, uses the stateful round-robin counter.
            max_tokens:  Override max_tokens for this client instance.
        """
        if chunk_index is not None:
            key = self.key_for_index(chunk_index)
            key_num = chunk_index % len(self._keys) + 1
        else:
            key = self.next_key()
            key_num = self._index  # already incremented

        idx = key_num - 1

        if self._provider == "watsonx":
            from llm.watsonx_client import WatsonxClient  # local import to avoid circular

            project_id = self.project_id_for_index(idx)
            logger.info(
                "Chunk %s → key #%d (%s), project=%s [provider=%s]",
                chunk_index, key_num, _mask_key(key), project_id, self._provider,
            )
            return WatsonxClient(
                api_key=key,
                project_id=project_id,
                url=self._url,
                model=self._model,
                temperature=self._temperature,
                max_tokens=max_tokens or self._max_tokens,
                max_retries=self._max_retries,
                fallback_model=self._fallback_model,
                key_number=key_num,
            )

        if self._provider == "openrouter":
            from llm.openrouter_client import OpenRouterClient
            return OpenRouterClient(
                api_keys=self._keys,
                model=self._model,
                temperature=self._temperature,
                max_tokens=max_tokens or self._max_tokens,
                max_retries=self._max_retries,
                url=self._url or "https://openrouter.ai/api/v1/chat/completions",
            )

        logger.info("Chunk %s → key #%d (%s) [provider=%s]", chunk_index, key_num, _mask_key(key), self._provider)

        from llm.groq_client import GroqClient  # local import to avoid circular

        return GroqClient(
            api_key=key,
            model=self._model,
            temperature=self._temperature,
            max_tokens=max_tokens or self._max_tokens,
            max_retries=self._max_retries,
            key_number=key_num,
            openrouter_client=self._openrouter_client,
        )

    @classmethod
    def from_config(cls) -> "KeyManager":
        """Convenience factory that reads from the app config (provider-aware)."""
        import config

        if config.LLM_PROVIDER == "watsonx":
            return cls(
                keys=config.WATSONX_API_KEYS,
                model=config.WATSONX_MODEL_ID,
                temperature=config.WATSONX_TEMPERATURE,
                max_tokens=config.WATSONX_MAX_TOKENS_PLAN,
                max_retries=config.LLM_MAX_RETRIES,
                provider="watsonx",
                project_id=config.WATSONX_PROJECT_ID,
                project_ids=config.WATSONX_PROJECT_IDS,
                url=config.WATSONX_URL,
                fallback_model=config.WATSONX_FALLBACK_MODEL_ID,
            )

        if config.LLM_PROVIDER == "openrouter":
            return cls(
                keys=config.OPENROUTER_API_KEYS,
                model=config.OPENROUTER_MODEL,
                temperature=config.GROQ_TEMPERATURE,
                max_tokens=config.GROQ_MAX_TOKENS_PLAN,
                max_retries=config.LLM_MAX_RETRIES,
                provider="openrouter",
                url=config.OPENROUTER_URL,
            )

        return cls(
            keys=config.GROQ_API_KEYS,
            model=config.GROQ_MODEL,
            temperature=config.GROQ_TEMPERATURE,
            max_tokens=config.GROQ_MAX_TOKENS_PLAN,
            max_retries=config.LLM_MAX_RETRIES,
            provider="groq",
            openrouter_keys=config.OPENROUTER_API_KEYS,
            openrouter_url=config.OPENROUTER_URL,
            openrouter_model=config.OPENROUTER_MODEL,
        )
