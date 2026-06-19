#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks user prompts that appear to contain high-confidence secrets.
# upstream implementation ../hooks.json invokes this hook for UserPromptSubmit.
# upstream design ../../documents/codex-configuration-reference.md documents Codex hook events.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates guard decisions.
# @dependency-end

"""Prevent obvious credentials from entering the model-visible prompt."""

from __future__ import annotations

import json
import re
import sys

SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"-----BEGIN (RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----"),
        "private key block",
    ),
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "AWS access key id",
    ),
    (
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
        "GitHub token",
    ),
    (
        re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
        "OpenAI-style API key",
    ),
)


def load_payload() -> dict[str, object]:
    """Read the Codex hook payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def prompt_from(payload: dict[str, object]) -> str:
    """Extract the user prompt from a UserPromptSubmit payload."""
    prompt = payload.get("prompt")
    if isinstance(prompt, str):
        return prompt
    return ""


def emit_block(secret_kind: str) -> None:
    """Emit the UserPromptSubmit block shape."""
    json.dump(
        {
            "decision": "block",
            "reason": (
                "Prompt appears to include a "
                f"{secret_kind}. Remove the secret or replace it with a redacted placeholder."
            ),
            "next_action": "remove_secret_or_use_redacted_placeholder_then_retry",
            "remediation": [
                "Remove the secret material from the prompt.",
                "Replace examples with redacted placeholders such as `[REDACTED_TOKEN]`.",
                "Rotate the secret if it was pasted into the session by mistake.",
            ],
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def main() -> int:
    """Block prompts that contain high-confidence secret patterns."""
    prompt = prompt_from(load_payload())
    for pattern, secret_kind in SECRET_PATTERNS:
        if pattern.search(prompt):
            emit_block(secret_kind)
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
