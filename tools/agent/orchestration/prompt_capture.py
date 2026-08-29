#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Captures bounded, redacted prompt evidence without side effects.
# upstream design ../../../documents/design/agentcanon-hook-simplification-wave3.md owns prompt capture parity.
# downstream implementation ./prompt_classifier.py consumes PromptCapture.
# downstream implementation ../../runtime/archive/behavior_event_assembly.py serializes prompt fields.
# downstream implementation ../../../tests/agent_tools/test_prompt_capture.py validates redaction and bounds.
# @dependency-end
"""Pure prompt capture and redaction owner."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

DEFAULT_EXCERPT_LIMIT = 600
_SECRET_RE = re.compile(
    r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----|"
    r"\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9_]{30,}\b|"
    r"\bsk-[A-Za-z0-9_-]{32,}\b"
)


@dataclass(frozen=True)
class PromptCapture:
    status: str
    excerpt_redacted: str
    char_count: int
    fingerprint: str
    truncated: bool

    @property
    def prompt_excerpt_redacted(self) -> str:
        return self.excerpt_redacted

    @property
    def prompt_char_count(self) -> int:
        return self.char_count

    def should_log(self) -> bool:
        return self.status == "present"


def _redact(text: str, rules: Iterable[tuple[re.Pattern[str], str]] = ()) -> str:
    redacted = _SECRET_RE.sub("[REDACTED_SECRET]", text)
    for pattern, replacement in rules:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def capture_prompt(
    payload: object,
    redaction_rules: Iterable[tuple[re.Pattern[str], str]] = (),
    excerpt_limit: int = DEFAULT_EXCERPT_LIMIT,
) -> PromptCapture:
    """Return bounded prompt evidence; never retain raw prompt text."""
    if excerpt_limit < 0:
        raise ValueError("excerpt_limit must be non-negative")
    prompt = ""
    if isinstance(payload, dict) and isinstance(payload.get("prompt"), str):
        prompt = payload["prompt"]
    if not prompt:
        return PromptCapture("missing", "", 0, "", False)
    redacted = _redact(prompt, redaction_rules)
    excerpt = redacted[:excerpt_limit]
    return PromptCapture(
        "present",
        excerpt,
        len(prompt),
        hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
        len(redacted) > excerpt_limit,
    )


def redact_sensitive_text(text: str) -> str:
    """Expose the same deterministic redaction for owner tests."""
    return _redact(text)
