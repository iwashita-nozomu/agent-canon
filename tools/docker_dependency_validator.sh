#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Validates the typed devcontainer dependency plan and image/tool ownership boundary.
# upstream design ../CONTAINER_OPERATIONS.md canonical product-image and mounted-tool separation
# upstream design ../documents/design/devcontainer/parent-dependency-manifest-followup.md parent manifest follow-up contract
# downstream implementation agent_tools/devcontainer_dependencies.py parses, merges, and orders the plan
# downstream implementation ../tests/agent_tools/test_devcontainer_dependencies.py exercises the validator route
# @dependency-end

set -euo pipefail

workspace_input="."
if [ "$#" -gt 0 ]; then
  workspace_input="$1"
fi
workspace="$(cd "$workspace_input" && pwd)"
if [ -f "$workspace/vendor/agent-canon/tools/agent_tools/devcontainer_dependencies.py" ]; then
  engine="$workspace/vendor/agent-canon/tools/agent_tools/devcontainer_dependencies.py"
  vendor_root="$workspace/vendor/agent-canon"
else
  engine="$workspace/tools/agent_tools/devcontainer_dependencies.py"
  vendor_root="$workspace"
fi

[ -f "$engine" ] || {
  echo "typed devcontainer dependency engine is unavailable: $engine" >&2
  exit 1
}

python3 "$engine" boundary \
  --workspace "$workspace" \
  --vendor-root "$vendor_root" \
  --format text

python3 "$engine" validate \
  --workspace "$workspace" \
  --vendor-root "$vendor_root" \
  --format text
