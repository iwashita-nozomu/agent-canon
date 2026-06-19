#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Keeps legacy PreToolUse guard invocations non-blocking.
# upstream design ../../documents/codex-configuration-reference.md documents hook policy
# upstream implementation ../hooks.json no longer wires this hook for new sessions
# @dependency-end

"""Compatibility no-op for sessions that loaded the old PreToolUse hook table."""

from __future__ import annotations

import json
import sys


def main() -> int:
    """Return a non-blocking hook response."""
    if not sys.stdin.isatty():
        sys.stdin.read()
    print(json.dumps({"decision": "approve"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
