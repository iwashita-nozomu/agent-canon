#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Provides the standalone compatibility wrapper for prompt secret safety.
# upstream implementation ./hook_safety.py owns pure secret matching and redacted payloads.
# upstream design ../../documents/codex/codex-configuration-reference.md documents Codex hook events.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates guard decisions.
# @dependency-end

"""Prevent obvious credentials from entering the model-visible prompt."""

from __future__ import annotations

import json
import sys

from hook_safety import payload_prompt, secret_block_payload, secret_kind  # noqa: E402


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


def main() -> int:
    """Block prompts that contain high-confidence secret patterns."""
    matched_kind = secret_kind(payload_prompt(load_payload()))
    if matched_kind is not None:
        json.dump(secret_block_payload(matched_kind), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
