#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Validates the typed shared tool dependency plan used by the bootstrap image.
# upstream design ../../../CONTAINER_OPERATIONS.md canonical shared image and mounted-target separation
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md bootstrap dependency contract
# downstream implementation ../../runtime/dispatch/agent-canon/src/environment_dependencies.rs parses, merges, and orders the plan
# downstream test ../../../tests/agent_tools/test_environment_dependencies_cli.py exercises the native validator route
# @dependency-end

set -euo pipefail

workspace_input="."
if [ "$#" -gt 0 ]; then
  workspace_input="$1"
fi
workspace="$(cd "$workspace_input" && pwd -P)"
engine="$workspace/tools/bin/agent-canon"
manifest="$workspace/bootstrap/container/image/dependencies.toml"

[ -x "$engine" ] || {
  echo "shared tool dependency engine is unavailable: $engine" >&2
  exit 1
}
[ -f "$manifest" ] || {
  echo "shared tool dependency manifest is unavailable: $manifest" >&2
  exit 1
}

"$engine" environment-dependencies validate \
  --workspace "$workspace" \
  --manifest "$manifest" \
  --format text
