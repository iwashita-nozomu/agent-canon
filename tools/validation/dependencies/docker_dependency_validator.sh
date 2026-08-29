#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Validates the typed shared tool dependency plan used by the bootstrap image.
# upstream design ../CONTAINER_OPERATIONS.md canonical shared image and mounted-target separation
# upstream design ../documents/design/agent-canon-bootstrap-tool-runtime.md bootstrap dependency contract
# downstream implementation agent_tools/dependency_plan.py parses, merges, and orders the plan
# downstream implementation ../tests/agent_tools/test_devcontainer_dependencies.py exercises the validator route
# @dependency-end

set -euo pipefail

workspace_input="."
if [ "$#" -gt 0 ]; then
  workspace_input="$1"
fi
workspace="$(cd "$workspace_input" && pwd -P)"
engine="$workspace/tools/analysis/dependencies/dependency_plan.py"
manifest="$workspace/bootstrap/container/image/dependencies.toml"

[ -f "$engine" ] || {
  echo "shared tool dependency engine is unavailable: $engine" >&2
  exit 1
}
[ -f "$manifest" ] || {
  echo "shared tool dependency manifest is unavailable: $manifest" >&2
  exit 1
}

python3 "$engine" validate \
  --workspace "$workspace" \
  --manifest "$manifest" \
  --format text
