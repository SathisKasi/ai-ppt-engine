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
from llm.semantic_cache import SemanticCache

logger = get_logger(__name__)


class KeyManagerError(Exception):
    """Raised when no keys are available."""


class KeyManager:
    """
    Thread-safe round-robin API key manager.

    Keys are rotated per request so that sequential section analyses
    automatically spread load across all provided API keys.
    """

    def __init__(self, keys: List[str], model: str, temperature: float = 0.3,
                 max_tokens: int = 2048, max_retries: int = 3,
                 semantic_cache: Optional[SemanticCache] = None) -> None:
        valid = [k.strip() for k in keys if k and k.strip()]
        if not valid:
            raise KeyManagerError("No valid API keys provided.")
        self._keys = valid
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._semantic_cache = semantic_cache
        self._index = 0
        self._lock = threading.Lock()
        logger.info("KeyManager initialized with %d key(s)", len(self._keys))

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

    def get_client(self, chunk_index: Optional[int] = None, max_tokens: Optional[int] = None):
        """
        Return a GroqClient bound to the key for this chunk.

        Args:
            chunk_index: Zero-based index of the chunk (determines key).
                         If None, uses the stateful round-robin counter.
            max_tokens:  Override max_tokens for this client instance.
        """
        from llm.groq_client import GroqClient  # local import to avoid circular

        if chunk_index is not None:
            key = self.key_for_index(chunk_index)
            key_num = chunk_index % len(self._keys) + 1
        else:
            key = self.next_key()
            key_num = self._index  # already incremented

        logger.debug("Chunk %s → key #%d", chunk_index, key_num)

        return GroqClient(
            api_key=key,
            model=self._model,
            temperature=self._temperature,
            max_tokens=max_tokens or self._max_tokens,
            max_retries=self._max_retries,
            semantic_cache=self._semantic_cache,
        )

    @classmethod
    def from_config(cls) -> "KeyManager":
        """Convenience factory that reads from the app config."""
        import config
        return cls(
            keys=config.GROQ_API_KEYS,
            model=config.GROQ_MODEL,
            temperature=config.GROQ_TEMPERATURE,
            max_tokens=config.GROQ_MAX_TOKENS_PLAN,
            max_retries=config.LLM_MAX_RETRIES,
            semantic_cache=SemanticCache(
                config.SEMANTIC_CACHE_PATH,
                config.SEMANTIC_CACHE_ENABLED,
            ),
        )
