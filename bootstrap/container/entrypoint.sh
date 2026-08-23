#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Starts one resident AgentCanon tool process or performs its read-only health probe.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md resident container lifecycle
# downstream implementation ./Dockerfile shared tool image and Docker healthcheck
# @dependency-end

set -euo pipefail

health() {
    [[ -x /usr/local/bin/agent-canon ]] || {
        echo "agent-canon-container: agent-canon CLI is missing" >&2
        return 1
    }
    [[ -x /usr/local/bin/agent-canon-tool ]] || {
        echo "agent-canon-container: typed tool dispatcher is missing" >&2
        return 1
    }
    [[ -x /usr/local/bin/pyright-langserver ]] || {
        echo "agent-canon-container: pyright language server is missing" >&2
        return 1
    }
    [[ -x /usr/local/bin/bash-language-server ]] || {
        echo "agent-canon-container: bash language server is missing" >&2
        return 1
    }
    [[ -x /usr/bin/clangd-18 ]] || {
        echo "agent-canon-container: clangd language server is missing" >&2
        return 1
    }
    [[ -r /usr/local/share/agent-canon/image-dependencies/plan.json ]] || {
        echo "agent-canon-container: image dependency receipt is missing" >&2
        return 1
    }
    [[ -d /tmp && -w /tmp ]] || {
        echo "agent-canon-container: writable /tmp tmpfs is required" >&2
        return 1
    }
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
