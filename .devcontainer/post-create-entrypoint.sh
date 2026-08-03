#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Runs the shared container-local post-create lifecycle before the optional derived-repository hook and propagates either stage's exit status.
# upstream design ../documents/design/devcontainer/parent-devcontainer-policy.md shared-first default lifecycle and parent customization boundary
# upstream implementation ../tools/agent_tools/agent_canon_source_root.py resolves the public source-root command entrypoint
# downstream implementation ./post-create.sh executes shared dependency installation and runtime projection
# downstream implementation ../.devcontainer/post-create-parent.sh provides the derived-repository customization hook when present
# @dependency-end

set -euo pipefail

workspace="${1:-}"
[ -n "$workspace" ] || {
  echo "post-create entrypoint requires the selected workspace path" >&2
  exit 1
}

workspace="$(cd "$workspace" && pwd -P)"
entrypoint_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Keep the shared lifecycle first. `set -e` preserves its exact non-zero status
# and prevents the derived hook from running after a failed shared stage.
bash "$entrypoint_dir/post-create.sh" "$workspace"

parent_hook="$workspace/.devcontainer/post-create-parent.sh"
if [ -f "$parent_hook" ]; then
  # The parent hook is optional in standalone AgentCanon, but its status is
  # part of the public resolver contract whenever the derived hook exists.
  bash "$parent_hook" "$workspace"
fi
