#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Forwards legacy docs checks CI automation to the unified Rust docs tool.
# upstream design ../README.md shared automation index
# upstream implementation ../../rust/agent-canon/src/docs.rs unified Rust docs check implementation
# @dependency-end

set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WORKSPACE_ROOT"

caller_chain="$(ps -o command= -p "${PPID:-0}" 2>/dev/null || true)"
echo "AGENT_CANON_FORWARDER=deprecated" >&2
echo "AGENT_CANON_FORWARDER_SEVERITY=fix-now" >&2
echo "AGENT_CANON_FORWARDER_CALLER_CHAIN=${caller_chain:-unknown}" >&2
echo "AGENT_CANON_FORWARDER_CANONICAL=tools/bin/agent-canon docs check" >&2

exec tools/bin/agent-canon docs check "$@"
