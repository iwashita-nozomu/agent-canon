#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Starts one resident AgentCanon tool process or performs its read-only health probe.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md resident container lifecycle
# downstream implementation ./Dockerfile shared tool image and Docker healthcheck
# @dependency-end

set -euo pipefail

health() {
    return 0
}

case "${1:-}" in
    health|--healthcheck)
        [[ "$#" -eq 1 ]] || {
            echo "usage: $0 health" >&2
            exit 64
        }
    health
        ;;
    tool)
        [[ "${2:-}" == "run" && "$#" -ge 3 ]] || {
            echo "usage: $0 tool run <catalog-id> -- [args...]" >&2
            exit 64
        }
        exec /usr/local/bin/agent-canon-tool "$@"
        ;;
    resident)
        exec sleep infinity
        ;;
    *)
        echo "usage: $0 health | resident | tool run <catalog-id> -- [args...]" >&2
        exit 64
        ;;
esac
