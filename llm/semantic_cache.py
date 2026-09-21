"""Content-addressed cache for successful LLM responses."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional


class SemanticCache:
    """SQLite-backed cache that only reuses identical requests."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._lock = threading.Lock()
        if enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS semantic_cache ("
                    "cache_key TEXT PRIMARY KEY, response TEXT NOT NULL, created_at REAL NOT NULL)"
                )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path), timeout=10)

    @staticmethod
    def make_key(
        provider: str,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        payload = {
            "provider": provider,
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get(self, cache_key: str) -> Optional[str]:
        if not self.enabled:
            return None
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT response FROM semantic_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        return row[0] if row else None

    def put(self, cache_key: str, response: str) -> None:
        if not self.enabled:
            return
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO semantic_cache(cache_key, response, created_at) "
                "VALUES (?, ?, ?)",
                (cache_key, response, time.time()),
            )