#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Verifies image-owned AgentCanon dependencies and reads back the container runtime.
# upstream design ../documents/design/devcontainer/parent-devcontainer-policy.md image-only startup boundary
# upstream implementation ../tools/agent_tools/devcontainer_dependencies.py immutable image lifecycle
# downstream implementation ./post-create-entrypoint.sh dispatches the optional parent hook
# @dependency-end

set -euo pipefail

umask 0007
[ "$(umask)" = "0007" ] || {
  echo "post-create runtime umask is not exactly 0007" >&2
  exit 1
}

workspace="${1:-}"
[ -n "$workspace" ] || {
  echo "post-create requires the selected repository root argument" >&2
  exit 1
}
workspace="$(cd "$workspace" && pwd -P)"
devcontainer_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
agent_canon_root="$(cd -P "$devcontainer_dir/.." && pwd -P)"
home="${HOME:-}"
case "$home" in
  /*) ;;
  *)
    echo "post-create HOME must be an absolute container path: ${home:-<unset>}" >&2
    exit 1
    ;;
esac

if [ -n "${AGENT_CANON_CONTAINER_USER:-}" ]; then
  [ "$(id -u)" -ne 0 ] || {
    echo "post-create must execute as the dedicated non-root user" >&2
    exit 1
  }
  [ "$(id -un)" = "$AGENT_CANON_CONTAINER_USER" ] || {
    echo "post-create user mismatch: expected ${AGENT_CANON_CONTAINER_USER}, got $(id -un)" >&2
    exit 1
  }
  [ "$HOME" = "/home/${AGENT_CANON_CONTAINER_USER}" ] || {
    echo "post-create HOME mismatch: $HOME" >&2
    exit 1
  }
fi

python3 "$agent_canon_root/tools/agent_tools/devcontainer_dependencies.py" \
  image-verify --workspace "$workspace" --vendor-root "$agent_canon_root" --format text

runtime_root="${AGENT_CANON_RUNTIME_ROOT:-/var/lib/agent-canon/runtime}"
image_root="${AGENT_CANON_IMAGE_DEPENDENCIES_ROOT:-/usr/local/share/agent-canon/image-dependencies}"
[ -d "$runtime_root" ] && [ -r "$runtime_root" ] || {
  echo "post-create runtime readback failed: runtime root is unavailable: $runtime_root" >&2
  exit 1
}
[ -d "$image_root" ] && [ -r "$image_root" ] || {
  echo "post-create runtime readback failed: image dependency root is unavailable: $image_root" >&2
  exit 1
}

echo "DEVCONTAINER_IMAGE_DEPENDENCIES_ROOT=$image_root"
echo "AGENT_CANON_RUNTIME_ROOT=$runtime_root"
for tool in node npm npx corepack codex gh jq tree clang-format clangd-18 pyright pyright-langserver bash-language-server; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "DEVCONTAINER_TOOL_READBACK=$tool:available"
  else
    echo "DEVCONTAINER_TOOL_READBACK=$tool:unavailable"
  fi
done

source_projection_root="${AGENT_CANON_SOURCE_PROJECTION_ROOT:-$workspace/reports/agents/devcontainer/runtime}"
if [ -d "$source_projection_root" ] && [ -w "$source_projection_root" ]; then
  echo "ENVIRONMENT_RUNTIME_PROJECTION=$source_projection_root"
else
  echo "ENVIRONMENT_RUNTIME_PROJECTION=$runtime_root"
fi
echo "ENVIRONMENT_TOOL_AVAILABILITY=$image_root/plan.json"
