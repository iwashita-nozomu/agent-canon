#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Runs the shared lifecycle around the validated mounted dependency plan.
# upstream design ../CONTAINER_OPERATIONS.md container image versus mounted developer/agent tooling boundary
# upstream design ../documents/design/devcontainer/parent-dependency-manifest-followup.md parent manifest merge and post-create order
# upstream implementation bootstrap-dependencies.sh establishes the fixed base capability set
# upstream implementation ../tools/agent_tools/devcontainer_dependencies.py validates and executes records
# downstream implementation ../rust/agent-canon/src/structured_analysis.rs builds the AgentCanon cache
# @dependency-end

set -euo pipefail

umask 0007
[ "$(umask)" = "0007" ] || {
  echo "post-create runtime umask is not exactly 0007" >&2
  exit 1
}

workspace="$1"
[ -n "$workspace" ] || {
  echo "post-create requires the selected repository root argument" >&2
  exit 1
}

workspace="$(cd "$workspace" && pwd)"
devcontainer_dir="$(cd "$(dirname "$0")" && pwd)"
agent_canon_root="$(cd -P "$devcontainer_dir/.." && pwd)"
tools_home="$HOME/.tools"
runtime_root="/var/lib/agent-canon/runtime"
source_projection_root="$workspace/reports/agents/devcontainer/runtime"
playwright_browsers_path="/usr/local/share/ms-playwright"
pip_user_script_dir="$(python3 - <<'PY'
import site
from pathlib import Path

print(Path(site.getuserbase()) / "bin")
PY
)"
export PLAYWRIGHT_BROWSERS_PATH="$playwright_browsers_path"

publish_agent_tools_profile() {
  local profile_script
  install -d -m 755 "$tools_home/bin"
  profile_script="$(mktemp)"
  cat >"$profile_script" <<EOF
export AGENT_CANON_TOOLS_HOME="$tools_home"
export AGENT_CANON_RUNTIME_ROOT="$runtime_root"
export AGENT_CANON_SOURCE_PROJECTION_ROOT="$source_projection_root"
export PLAYWRIGHT_BROWSERS_PATH="$playwright_browsers_path"
case ":\$PATH:" in
  *:"$tools_home/bin":*) ;;
  *) export PATH="$tools_home/bin:\$PATH" ;;
esac
case ":\$PATH:" in
  *:"$pip_user_script_dir":*) ;;
  *) export PATH="$pip_user_script_dir:\$PATH" ;;
esac
EOF
  if [ "$(id -u)" -eq 0 ]; then
    install -m 644 "$profile_script" /etc/profile.d/agent-canon-tools.sh
  elif command -v sudo >/dev/null 2>&1; then
    sudo install -m 644 "$profile_script" /etc/profile.d/agent-canon-tools.sh
  else
    echo "post-create requires root or sudo for the shared profile" >&2
    rm -f "$profile_script"
    return 1
  fi
  rm -f "$profile_script"
  export PATH="$tools_home/bin:$PATH"
}

register_safe_directories() {
  if [ -f "$workspace/docker/register_safe_directories.sh" ]; then
    bash "$workspace/docker/register_safe_directories.sh" "$workspace"
    return
  fi
  git config --global --add safe.directory "$workspace" || true
  if [ -d "$workspace/.git" ]; then
    git config --global --add safe.directory "$workspace/.git" || true
  fi
}

agent_canon_source_root() {
  if [ -f "$workspace/vendor/agent-canon/rust/agent-canon/Cargo.toml" ]; then
    printf '%s\n' "$workspace/vendor/agent-canon"
  elif [ -f "$workspace/rust/agent-canon/Cargo.toml" ]; then
    printf '%s\n' "$workspace"
  else
    echo "AgentCanon Rust source is unavailable" >&2
    return 1
  fi
}

publish_agent_canon_cli() {
  local canon_root
  local binary
  canon_root="$(agent_canon_source_root)"
  binary="$canon_root/rust/agent-canon/target/release/agent-canon"
  [ -x "$binary" ] || {
    echo "AgentCanon cargo-source-build did not produce $binary" >&2
    return 1
  }
  install -d -m 755 "$tools_home/agent-canon/bin" "$tools_home/bin"
  install -m 755 "$binary" "$tools_home/agent-canon/bin/agent-canon"
  ln -sfn "$tools_home/agent-canon/bin/agent-canon" "$tools_home/bin/agent-canon"
  if [ "$(id -u)" -eq 0 ]; then
    ln -sfn "$tools_home/bin/agent-canon" /usr/local/bin/agent-canon
  elif command -v sudo >/dev/null 2>&1; then
    sudo ln -sfn "$tools_home/bin/agent-canon" /usr/local/bin/agent-canon
  else
    echo "post-create requires root or sudo for /usr/local/bin/agent-canon" >&2
    return 1
  fi
  "$tools_home/bin/agent-canon" --version
}

build_agent_canon_cache() {
  command -v agent-canon >/dev/null 2>&1 || {
    echo "AgentCanon CLI is unavailable after dependency execution" >&2
    return 1
  }
  agent-canon structured-analysis build --root "$workspace" --profile devcontainer
  echo "STRUCTURED_ANALYSIS_BOOTSTRAP=pass"
}

publish_container_local_runtime() {
  local tool_status
  install -d -m 755 "$runtime_root" "$runtime_root/runs" "$runtime_root/logs" "$source_projection_root"
  tool_status="$(
    for tool in agent-canon codex gh jq tree; do
      if command -v "$tool" >/dev/null 2>&1; then
        printf '    "%s": {"available": true, "source": "declarative"},\n' "$tool"
      else
        printf '    "%s": {"available": false, "source": "declarative"},\n' "$tool"
      fi
    done | sed '$ s/,$//'
  )"
  {
    printf '{\n'
    printf '  "schema_version": "container-tool-availability/v2",\n'
    printf '  "runtime_root": %s,\n' "$(printf '%s' "$runtime_root" | jq -R .)"
    printf '  "source_projection_root": %s,\n' "$(printf '%s' "$source_projection_root" | jq -R .)"
    printf '  "playwright_browsers_path": %s,\n' "$(printf '%s' "$playwright_browsers_path" | jq -R .)"
    printf '  "tools": {\n%s\n  }\n}\n' "$tool_status"
  } >"$runtime_root/tool-availability.json"
  cp "$runtime_root/tool-availability.json" "$source_projection_root/tool-availability.json"
  echo "ENVIRONMENT_RUNTIME_PROJECTION=$source_projection_root"
  echo "ENVIRONMENT_TOOL_AVAILABILITY=$runtime_root/tool-availability.json"
}

"$devcontainer_dir/finalize-shared-runtime.sh"
"$devcontainer_dir/bootstrap-dependencies.sh"
"$devcontainer_dir/bootstrap-dependencies.sh" --check

python3 "$agent_canon_root/tools/agent_tools/devcontainer_dependencies.py" \
  validate --workspace "$workspace" --vendor-root "$agent_canon_root" --format text
python3 "$agent_canon_root/tools/agent_tools/devcontainer_dependencies.py" \
  install --workspace "$workspace" --vendor-root "$agent_canon_root" --receipts \
  "$workspace/.agent-canon/dependency-receipts" --format text

register_safe_directories
publish_agent_tools_profile

if [ -f "$workspace/docker/install_python_dependencies.sh" ]; then
  bash "$workspace/docker/install_python_dependencies.sh" "$workspace"
else
  echo "repo-local Python dependency installer absent; skipping docker/install_python_dependencies.sh"
fi

publish_agent_canon_cli
build_agent_canon_cache
publish_container_local_runtime
