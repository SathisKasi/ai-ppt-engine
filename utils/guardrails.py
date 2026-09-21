"""Input and LLM-boundary guardrails for the presentation generator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List


class GuardrailViolation(ValueError):
    """Raised when input cannot safely enter the generation pipeline."""


@dataclass(frozen=True)
class GuardrailResult:
    text: str
    masked_items: int = 0


# These patterns target credentials and direct identifiers, not ordinary prose.
_SENSITIVE_PATTERNS = (
    ("API_KEY", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,})\b")),
    ("BEARER_TOKEN", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?\d[\d ()-]{8,}\d)(?!\d)")),
    ("CARD_NUMBER", re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
)

_INJECTION_PATTERNS = (
    re.compile(r"(?i)\b(ignore|disregard|override|forget)\b.{0,80}\b(previous|prior|above|system|developer|instruction)s?\b"),
    re.compile(r"(?i)\b(reveal|show|print| disclose|expose)\b.{0,80}\b(system prompt|developer message|api key|secret|credential)s?\b"),
    re.compile(r"(?i)\b(jailbreak|dan mode|do anything now|bypass (?:all )?safety)\b"),
    re.compile(r"(?i)\bexecute\b.{0,50}\b(shell|powershell|cmd|terminal|python)\b"),
)

_UNSAFE_PATTERNS = (
    re.compile(r"(?i)\b(build|make|write|create|deploy|instructions? for)\b.{0,80}\b(bomb|explosive|weapon|ransomware|keylogger|credential stealer)\b"),
    re.compile(r"(?i)\b(step[- ]by[- ]step|instructions?)\b.{0,80}\b(self[- ]harm|suicide)\b"),
    re.compile(r"(?i)\b(child sexual|sexual abuse material|exploit a minor)\b"),
)

_OUT_OF_SCOPE_PATTERNS = (
    re.compile(r"(?i)\b(read|write|delete|modify|execute)\b.{0,60}\b(file|folder|directory|database|server|terminal)\b"),
    re.compile(r"(?i)\b(send|transfer|refund|purchase|trade)\b.{0,60}\b(payment|money|funds|email)\b"),
)


def mask_sensitive_data(text: str) -> GuardrailResult:
    """Replace credentials and direct identifiers before model calls."""
    masked = text
    count = 0
    for label, pattern in _SENSITIVE_PATTERNS:
        masked, replacements = pattern.subn(f"[MASKED_{label}]", masked)
        count += replacements
    return GuardrailResult(masked, count)


def validate_input(text: str, *, mode: str = "prompt") -> GuardrailResult:
    """Validate user/document text and return its masked form.

    Uploaded documents may contain arbitrary business topics, so scope checks
    focus on operational requests rather than restricting the document subject.
    """
    if not text or not text.strip():
        raise GuardrailViolation("Input is empty.")

    normalized = text.strip()
    if len(normalized) > 2_000_000:
        raise GuardrailViolation("Input is too large for safe processing.")

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(normalized):
            raise GuardrailViolation(
                "The input appears to contain instructions intended to override the application's AI instructions."
            )
    for pattern in _UNSAFE_PATTERNS:
        if pattern.search(normalized):
            raise GuardrailViolation("The requested content is not supported by this application.")
    if mode == "prompt":
        for pattern in _OUT_OF_SCOPE_PATTERNS:
            if pattern.search(normalized):
                raise GuardrailViolation(
                    "The prompt contains an operational action outside this presentation-generation application."
                )

    return mask_sensitive_data(normalized)


def sanitize_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Validate and mask all model-bound message content."""
    safe_messages: List[Dict[str, str]] = []
    for message in messages:
        content = str(message.get("content", ""))
        if message.get("role") == "system":
            result = mask_sensitive_data(content)
        else:
            result = validate_input(content, mode="document")
        safe_messages.append({**message, "content": result.text})
    return safe_messages