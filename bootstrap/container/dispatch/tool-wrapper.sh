#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Exposes the typed agent-canon tool run namespace without an arbitrary shell executor.
# upstream implementation ../../../tools/runtime/dispatch/agent-canon/src/tool_dispatch.rs catalog dispatcher
# downstream implementation ../lifecycle/entrypoint.sh resident container command boundary
# @dependency-end

set -euo pipefail

if [[ "${1:-}" != "tool" || "${2:-}" != "run" ]]; then
    echo "usage: agent-canon tool run <catalog-id> -- [args...]" >&2
    exit 64
fi
shift 2

cache_root=${AGENT_CANON_CACHE_ROOT:-/var/lib/agent-canon/cache}
exec env AGENT_CANON_EXECUTION_PLANE=tool-container \
    AGENT_CANON_SOURCE_ROOT=/opt/agent-canon/source \
    "$cache_root/bin/agent-canon" \
    tool run --container-exec --root /opt/agent-canon/source "$@"
