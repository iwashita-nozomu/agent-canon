#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides the thin Python adapter to the Rust AgentCanon memory CLI.
# upstream implementation ../../rust/agent-canon/src/memory.rs owns memory schema, parsing, validation, search, duplicate detection, and serialization.
# downstream implementation ../../tools/bin/agent-canon owns the Rust CLI entrypoint.
# downstream implementation ../../tests/agent_tools/test_memory_record.py validates adapter transport.
# @dependency-end

"""Forward memory operations to the Rust-owned AgentCanon memory command."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def repository_root() -> Path:
    """Resolve the standalone AgentCanon source root from this adapter path."""
    return Path(__file__).resolve().parents[2]


def main() -> int:
    """Forward all arguments without reimplementing memory semantics."""
    root = repository_root()
    command = [str(root / "tools" / "bin" / "agent-canon"), "memory", *sys.argv[1:]]
    environment = os.environ.copy()
    return subprocess.run(command, cwd=root, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
