# @dependency-start
# contract test fixture
# responsibility Selects the existing native executable for docs-command tests without creating a Cargo target.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/main.rs owns the standalone formatter CLI
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md assigns bootstrap routing to user tools
# downstream implementation ../tools/test_check_markdown_math.py uses the fixture for math checks
# downstream implementation ../tools/test_fix_mermaid.py uses the fixture for Mermaid fixes
# @dependency-end
"""Return the selected native AgentCanon executable for CLI tests."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def standalone_agent_canon() -> Path:
    """Resolve a selected environment binary or an existing PATH command."""
    configured = os.environ.get("AGENT_CANON_NATIVE_BIN") or os.environ.get(
        "AGENT_CANON_CLI"
    )
    candidate = Path(configured) if configured else Path(shutil.which("agent-canon") or "")
    if not candidate or not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise RuntimeError(
            "native AgentCanon executable is unavailable; set AGENT_CANON_NATIVE_BIN "
            "or AGENT_CANON_CLI, or put agent-canon on PATH"
        )
    return candidate.resolve()
