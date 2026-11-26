#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Starts the resident, verifies its image tools, and dispatches source-mounted commands.
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md resident container lifecycle
# downstream implementation ../image/Dockerfile shared tool image and Docker healthcheck
# @dependency-end

set -euo pipefail

compile() {
    verify_tools
    exec /opt/agent-canon/source/tools/runtime/container/compile.sh
}

verify_tools() (
    local scratch
    local verifier=/usr/local/bin/agent-canon-dependency-bootstrap
    scratch=$(mktemp -d)
    trap 'rm -r -- "$scratch"' EXIT

    CARGO_HOME=/usr/local/share/agent-canon/toolchains/cargo \
        "$verifier" environment-dependencies image-verify \
        --workspace /workspace \
        --manifest /usr/local/share/agent-canon/runtime/dependencies.toml \
        --format text

    cat > "$scratch/README.md" <<'EOF'
# Image smoke

Open the [linked fixture](target.txt). The formula is $x^2$.

```mermaid
flowchart LR
  A --> B
```
EOF
    printf 'Fixture\n' > "$scratch/target.txt"
    quarto pandoc --version >/dev/null
    "$verifier" docs check --root "$scratch" README.md
    printf '%s\n' 'q_{\rm model}' | katex --format mathml --output "$scratch/equation.xml"
    grep -q '<math' "$scratch/equation.xml"
)

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
    verify-tools)
        [[ "$#" -eq 1 ]] || {
            echo "usage: $0 verify-tools" >&2
            exit 64
        }
        verify_tools
        ;;
    tool)
        [[ "${2:-}" == "run" && "$#" -ge 3 ]] || {
            echo "usage: $0 tool run <catalog-id> -- [args...]" >&2
            exit 64
        }
        exec /usr/local/bin/agent-canon-tool "$@"
        ;;
    compile)
        [[ "$#" -eq 1 ]] || {
            echo "usage: $0 compile" >&2
            exit 64
        }
        compile
        ;;
    resident)
        exec sleep infinity
        ;;
    *)
        echo "usage: $0 health | resident | compile | verify-tools | tool run <catalog-id> -- [args...]" >&2
        exit 64
        ;;
esac
