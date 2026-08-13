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

expected_runtime_user="project"
expected_runtime_home="/home/project"
[ "${AGENT_CANON_CONTAINER_USER:-}" = "$expected_runtime_user" ] || {
  echo "post-create runtime user marker mismatch: expected $expected_runtime_user" >&2
  exit 1
}
runtime_uid="$(id -u)"
runtime_gid="$(id -g)"
[[ "$runtime_uid" =~ ^[1-9][0-9]*$ ]] || {
  echo "post-create project identity UID must be a nonzero decimal: $runtime_uid" >&2
  exit 1
}
[[ "$runtime_gid" =~ ^[0-9]+$ ]] || {
  echo "post-create project primary GID must be a nonnegative decimal: $runtime_gid" >&2
  exit 1
}
[ "$(id -un)" = "$expected_runtime_user" ] || {
  echo "post-create user mismatch: expected ${expected_runtime_user}, got $(id -un)" >&2
  exit 1
}
[ "$HOME" = "$expected_runtime_home" ] || {
  echo "post-create HOME mismatch: expected ${expected_runtime_home}, got ${HOME:-<unset>}" >&2
  exit 1
}
workspace_write_probe=""
trap 'if [ -n "${workspace_write_probe:-}" ]; then rm -f -- "$workspace_write_probe"; fi' EXIT

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

workspace_write_probe="$(mktemp "$workspace/identity-write.XXXXXX")"
printf '%s\n' "project" >"$workspace_write_probe"
[ "$(cat "$workspace_write_probe")" = "project" ] || {
  echo "post-create workspace readback failed: $workspace_write_probe" >&2
  exit 1
}
rm -f -- "$workspace_write_probe"
workspace_write_probe=""

echo "DEVCONTAINER_IMAGE_DEPENDENCIES_ROOT=$image_root"
echo "AGENT_CANON_RUNTIME_ROOT=$runtime_root"
echo "AGENT_CANON_CONTAINER_USER=$expected_runtime_user"
echo "AGENT_CANON_RUNTIME_UID=$runtime_uid"
echo "AGENT_CANON_RUNTIME_GID=$runtime_gid"
echo "AGENT_CANON_RUNTIME_HOME=$HOME"
for tool in node npm npx corepack codex gh jq tree clang-format clangd-18 pyright pyright-langserver bash-language-server rust-analyzer agent-canon; do
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
