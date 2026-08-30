#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Exposes the typed agent-canon tool run namespace without an arbitrary shell executor.
# upstream implementation ../../tools/runtime/dispatch/tool_dispatch.py catalog dispatcher
# downstream implementation ./entrypoint.sh resident container command boundary
# @dependency-end

set -euo pipefail

if [[ "${1:-}" != "tool" || "${2:-}" != "run" ]]; then
    echo "usage: agent-canon tool run <catalog-id> -- [args...]" >&2
    exit 64
fi
shift 2

exec env AGENT_CANON_EXECUTION_PLANE=tool-container \
    python3 /usr/local/share/agent-canon/runtime/tools/runtime/dispatch/tool_dispatch.py \
    --container-exec \
    --root /usr/local/share/agent-canon/runtime \
    run "$@"
