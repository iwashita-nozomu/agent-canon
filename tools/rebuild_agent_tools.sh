#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Rebuilds local compiled AgentCanon tools after AgentCanon source updates.
# upstream design ../CONTAINER_OPERATIONS.md compiled tool cache and devcontainer boundary.
# upstream design ../documents/design/rust-agent-tool-migration.md Rust CLI migration and rebuild policy.
# upstream implementation ./agent_tools/parent_root_side_effects.py validates all rebuild output and cache paths.
# downstream implementation ./update_agent_canon.sh calls this after safe AgentCanon updates.
# downstream implementation ../tests/tools/test_update_agent_canon.py validates rebuild behavior.
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SUPERPROJECT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-superproject-working-tree 2>/dev/null || true)"
if [ -n "$SUPERPROJECT_DIR" ]; then
  ROOT_DIR="$SUPERPROJECT_DIR"
else
  ROOT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
fi
AGENT_CANON_SOURCE_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PARENT_ROOT_DIR="${AGENT_CANON_PARENT_ROOT:-$ROOT_DIR}"
PARENT_ROOT_DIR="$(cd "${PARENT_ROOT_DIR}" && pwd -P)"
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"
TOOLS_HOME="${AGENT_CANON_TOOLS_HOME:-${PARENT_ROOT_DIR}/.agent-canon/tools}"
CARGO_HOME="${AGENT_CANON_CARGO_HOME:-${CARGO_HOME:-${PARENT_ROOT_DIR}/.agent-canon/cache/cargo-home}}"
BUILD_TARGET_DIR="${CARGO_TARGET_DIR:-${AGENT_CANON_CLI_TARGET_DIR:-${PARENT_ROOT_DIR}/.agent-canon/cache/cargo-target}}"
FORCE_REBUILD="${AGENT_CANON_FORCE_TOOL_REBUILD:-0}"
BOUNDARY_SCRIPT="${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py"
if [ ! -f "$BOUNDARY_SCRIPT" ]; then
  echo "AGENT_CANON_TOOL_REBUILD=fail reason=missing-parent-boundary" >&2
  exit 1
fi
if [[ "${PARENT_ROOT_DIR}" != "${ROOT_DIR}" \
  && "${AGENT_CANON_CHILD_PURPOSE:-}" != "agent-canon-rebuild-script" ]]; then
  echo "AGENT_CANON_REBUILD_PARENT_HANDOFF=missing" >&2
  exit 2
fi
if [[ "${AGENT_CANON_CHILD_PURPOSE:-}" == "agent-canon-rebuild-script" ]]; then
  python3 "${BOUNDARY_SCRIPT}" verify-child \
    --root "${PARENT_ROOT_DIR}" \
    --source-root "${AGENT_CANON_SOURCE_ROOT}" \
    --purpose agent-canon-rebuild-script \
    --consume >/dev/null
else
  exec python3 "${BOUNDARY_SCRIPT}" exec-parent-bound \
    --root "${PARENT_ROOT_DIR}" \
    --source-root "${AGENT_CANON_SOURCE_ROOT}" \
    --purpose agent-canon-rebuild-script \
    --issue-handoff \
    -- bash "${BASH_SOURCE[0]}" "$@"
fi
unset AGENT_CANON_CHILD_HANDOFF AGENT_CANON_HANDOFF_AUDIENCE AGENT_CANON_CHILD_PURPOSE

resolve_parent_path() {
  python3 "$BOUNDARY_SCRIPT" resolve \
    --root "$PARENT_ROOT_DIR" \
    --candidate "$1" \
    --purpose "agent-canon-tool-rebuild-$2"
}

TOOLS_HOME="$(resolve_parent_path "$TOOLS_HOME" tools-home)"
CARGO_HOME="$(resolve_parent_path "$CARGO_HOME" cargo-home)"
BUILD_TARGET_DIR="$(resolve_parent_path "$BUILD_TARGET_DIR" cargo-target)"
if [ -n "${CARGO_TARGET_DIR:-}" ] && [ -n "${AGENT_CANON_CLI_TARGET_DIR:-}" ]; then
  CLI_TARGET_DIR="$(resolve_parent_path "$AGENT_CANON_CLI_TARGET_DIR" cli-target)"
  if [ "$BUILD_TARGET_DIR" != "$CLI_TARGET_DIR" ]; then
    echo "AGENT_CANON_TOOL_REBUILD=fail reason=target-alias-mismatch" >&2
    exit 1
  fi
fi

# shellcheck source=tools/lib/agent_canon_source_identity.sh
source "$SCRIPT_DIR/lib/agent_canon_source_identity.sh"

agent_canon_source_root() {
  if [ -f "$ROOT_DIR/$PREFIX/rust/agent-canon/Cargo.toml" ]; then
    printf '%s\n' "$ROOT_DIR/$PREFIX"
    return
  fi
  if [ -f "$ROOT_DIR/rust/agent-canon/Cargo.toml" ]; then
    printf '%s\n' "$ROOT_DIR"
    return
  fi
  printf '%s\n' ""
}

source_commit() {
  agent_canon_source_identity "$ROOT_DIR" "$PREFIX" "$1"
}

installed_commit() {
  local state_file="$1"
  awk -F= '$1 == "agent_canon_source_commit" {print $2; exit}' "$state_file" 2>/dev/null || true
}

rust_sources_newer_than_binary() {
  local source_root="$1"
  local binary="$2"
  if [ ! -x "$binary" ]; then
    return 0
  fi
  find "$source_root/rust/agent-canon" \
    \( -name '*.rs' -o -name 'Cargo.toml' -o -name 'Cargo.lock' \) \
    -newer "$binary" -print -quit
}

maybe_link_usr_local() {
  echo "AGENT_CANON_TOOL_REBUILD_USR_LOCAL=skipped_parent_bounded"
}

rebuild_rust_cli() {
  local source_root
  local manifest
  local source_sha
  local state_dir
  local state_file
  local installed_sha
  local build_binary
  local install_binary
  local source_newer
  local source_sha_after

  source_root="$(agent_canon_source_root)"
  if [ -z "$source_root" ]; then
    echo "AGENT_CANON_TOOL_REBUILD_RUST=skipped_missing_rust_manifest"
    return
  fi
  source_root="$(resolve_parent_path "$source_root" source-root)"
  if ! command -v cargo >/dev/null 2>&1; then
    echo "AGENT_CANON_TOOL_REBUILD_RUST=skipped_missing_cargo"
    echo "AGENT_CANON_TOOL_REBUILD_NEXT=rebuild_in_devcontainer_or_install_rust_toolchain"
    return
  fi

  manifest="$source_root/rust/agent-canon/Cargo.toml"
  source_sha="$(source_commit "$source_root")"
  state_dir="$TOOLS_HOME/agent-canon"
  state_file="$state_dir/.build-state"
  install_binary="$state_dir/bin/agent-canon"
  installed_sha="$(installed_commit "$state_file")"
  source_newer="$(rust_sources_newer_than_binary "$source_root" "$install_binary")"
  if [ "$FORCE_REBUILD" != "1" ] && [ -x "$install_binary" ] && [ "$installed_sha" = "$source_sha" ] && [ -z "$source_newer" ]; then
    echo "AGENT_CANON_TOOL_REBUILD_RUST=already_current"
    return
  fi

  CARGO_HOME="$(
    python3 "$BOUNDARY_SCRIPT" ensure-dir \
      --root "$PARENT_ROOT_DIR" \
      --candidate "$CARGO_HOME" \
      --purpose agent-canon-tool-rebuild-cargo-home
  )"
  BUILD_TARGET_DIR="$(
    python3 "$BOUNDARY_SCRIPT" ensure-dir \
      --root "$PARENT_ROOT_DIR" \
      --candidate "$BUILD_TARGET_DIR" \
      --purpose agent-canon-tool-rebuild-cargo-target
  )"
  CARGO_HOME="$CARGO_HOME" \
    CARGO_TARGET_DIR="$BUILD_TARGET_DIR" \
    cargo build --release --manifest-path "$manifest"
  source_sha_after="$(source_commit "$source_root")"
  if [ "$source_sha" != "$source_sha_after" ]; then
    echo "AgentCanon source identity changed during build: $source_sha!=$source_sha_after" >&2
    return 1
  fi
  build_binary="$BUILD_TARGET_DIR/release/agent-canon"
  if [ ! -x "$build_binary" ]; then
    echo "AgentCanon cargo build produced no executable under the parent root" >&2
    return 1
  fi
  state_dir="$(
    python3 "$BOUNDARY_SCRIPT" ensure-dir \
      --root "$PARENT_ROOT_DIR" \
      --candidate "$state_dir" \
      --purpose agent-canon-tool-rebuild-state
  )"
  python3 "$BOUNDARY_SCRIPT" ensure-dir \
    --root "$PARENT_ROOT_DIR" \
    --candidate "$state_dir/bin" \
    --purpose agent-canon-tool-rebuild-bin >/dev/null
  python3 "$BOUNDARY_SCRIPT" ensure-dir \
    --root "$PARENT_ROOT_DIR" \
    --candidate "$TOOLS_HOME/bin" \
    --purpose agent-canon-tool-rebuild-tools-bin >/dev/null
  python3 "$BOUNDARY_SCRIPT" copy \
    --root "$PARENT_ROOT_DIR" \
    --source "$build_binary" \
    --candidate "$install_binary" \
    --preserve-mode \
    --purpose agent-canon-tool-rebuild-install >/dev/null
  python3 "$BOUNDARY_SCRIPT" replace-symlink \
    --root "$PARENT_ROOT_DIR" \
    --target "$install_binary" \
    --candidate "$TOOLS_HOME/bin/agent-canon" \
    --purpose agent-canon-tool-rebuild-link >/dev/null
  {
    printf 'agent_canon_source_root=%s\n' "$source_root"
    printf 'agent_canon_source_commit=%s\n' "$source_sha"
  } | python3 "$BOUNDARY_SCRIPT" write \
    --root "$PARENT_ROOT_DIR" \
    --candidate "$state_file" \
    --purpose agent-canon-tool-rebuild-state >/dev/null
  maybe_link_usr_local "$TOOLS_HOME/bin/agent-canon"
  "$TOOLS_HOME/bin/agent-canon" --version >/dev/null
  echo "AGENT_CANON_TOOL_REBUILD_RUST=rebuilt"
}

main() {
  echo "AGENT_CANON_TOOL_REBUILD_ROOT=$ROOT_DIR"
  echo "AGENT_CANON_TOOL_REBUILD_TOOLS_HOME=$TOOLS_HOME"
  echo "AGENT_CANON_TOOL_REBUILD_CARGO_HOME=$CARGO_HOME"
  rebuild_rust_cli
  echo "AGENT_CANON_TOOL_REBUILD=pass"
}

main "$@"
