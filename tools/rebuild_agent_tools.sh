#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Rebuilds local compiled AgentCanon tools after AgentCanon source updates.
# upstream design ../CONTAINER_OPERATIONS.md compiled tool cache and devcontainer boundary.
# upstream design ../documents/rust-agent-tool-migration.md Rust CLI migration and rebuild policy.
# upstream implementation ./install_llama_cpp.sh rebuilds llama.cpp when a local source checkout exists.
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
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"
TOOLS_HOME="${AGENT_CANON_TOOLS_HOME:-${HOME}/.tools}"
FORCE_REBUILD="${AGENT_CANON_FORCE_TOOL_REBUILD:-0}"

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
  local source_root="$1"
  git -C "$source_root" rev-parse HEAD 2>/dev/null || printf '%s\n' "unknown"
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
  local binary="$1"
  if [ "${AGENT_CANON_SKIP_USR_LOCAL_LINK:-0}" = "1" ]; then
    echo "AGENT_CANON_TOOL_REBUILD_USR_LOCAL=skipped_by_env"
    return
  fi
  if [ "$(id -u)" -eq 0 ]; then
    ln -sf "$binary" /usr/local/bin/agent-canon
    echo "AGENT_CANON_TOOL_REBUILD_USR_LOCAL=linked"
    return
  fi
  if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo ln -sf "$binary" /usr/local/bin/agent-canon
    echo "AGENT_CANON_TOOL_REBUILD_USR_LOCAL=linked"
    return
  fi
  echo "AGENT_CANON_TOOL_REBUILD_USR_LOCAL=skipped_no_privilege"
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

  source_root="$(agent_canon_source_root)"
  if [ -z "$source_root" ]; then
    echo "AGENT_CANON_TOOL_REBUILD_RUST=skipped_missing_rust_manifest"
    return
  fi
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

  cargo build --release --manifest-path "$manifest"
  build_binary="$source_root/rust/agent-canon/target/release/agent-canon"
  install -d -m 755 "$state_dir/bin" "$TOOLS_HOME/bin"
  install -m 755 "$build_binary" "$install_binary"
  ln -sf "$install_binary" "$TOOLS_HOME/bin/agent-canon"
  {
    printf 'agent_canon_source_root=%s\n' "$source_root"
    printf 'agent_canon_source_commit=%s\n' "$source_sha"
  } >"$state_file"
  maybe_link_usr_local "$TOOLS_HOME/bin/agent-canon"
  "$TOOLS_HOME/bin/agent-canon" --version >/dev/null
  echo "AGENT_CANON_TOOL_REBUILD_RUST=rebuilt"
}

rebuild_llama_cpp() {
  local source_root
  local installer
  local rebuild_args

  source_root="$(agent_canon_source_root)"
  if [ -z "$source_root" ]; then
    echo "AGENT_CANON_LLAMA_CPP=skipped_missing_agent_canon_source"
    return
  fi
  installer="$source_root/tools/install_llama_cpp.sh"
  if [ ! -f "$installer" ]; then
    echo "AGENT_CANON_LLAMA_CPP=skipped_missing_installer"
    return
  fi
  rebuild_args=(--skip-missing-source)
  if [ "${AGENT_CANON_REBUILD_LLAMA_CPP:-1}" = "1" ]; then
    rebuild_args+=(--force)
  fi
  AGENT_CANON_TOOLS_HOME="$TOOLS_HOME" bash "$installer" "${rebuild_args[@]}"
}

main() {
  echo "AGENT_CANON_TOOL_REBUILD_ROOT=$ROOT_DIR"
  echo "AGENT_CANON_TOOL_REBUILD_TOOLS_HOME=$TOOLS_HOME"
  rebuild_rust_cli
  rebuild_llama_cpp
  echo "AGENT_CANON_TOOL_REBUILD=pass"
}

main "$@"
