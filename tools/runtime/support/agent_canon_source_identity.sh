#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Resolves the selected AgentCanon source identity and validates active-source receipts for shell producers.
# upstream design ../../../documents/runtime/bootstrap-runtime.md active standalone source and runtime boundary.
# upstream design ../../../documents/design/rust-agent-tool-migration.md compiled CLI provenance format.
# downstream implementation ../../../bootstrap/container/lifecycle/entrypoint.sh container CLI publication.
# downstream test ../../../tests/agent_tools/test_environment_dependencies_cli.py identity and validator command oracles.
# @dependency-end

agent_canon_source_identity() {
  local repository_root="$1"
  local source_prefix="$2"
  local source_root="$3"
  local source_sha
  local provider_sha
  local vendor_root

  [ -n "$repository_root" ] && [ -n "$source_prefix" ] && [ -n "$source_root" ] || {
    echo "AgentCanon source identity requires repository, prefix, and source-root arguments" >&2
    return 1
  }
  if [ ! -f "$source_root/.git" ] && [ ! -d "$source_root/.git" ]; then
    echo "AgentCanon source-root Git metadata is unavailable: $source_root" >&2
    return 1
  fi
  if ! source_sha="$(git -C "$source_root" rev-parse --verify HEAD 2>/dev/null)"; then
    echo "AgentCanon source-root identity is unavailable: $source_root" >&2
    return 1
  fi
  vendor_root="$repository_root/$source_prefix"
  if [ "$source_prefix" != "." ] && [ "$source_prefix" != "./" ] \
    && [ -d "$vendor_root" ] \
    && [ "$(cd "$vendor_root" && pwd -P)" = "$(cd "$source_root" && pwd -P)" ]; then
    if ! provider_sha="$(git -C "$repository_root" rev-parse --verify "HEAD:$source_prefix" 2>/dev/null)"; then
      echo "AgentCanon parent gitlink identity is unavailable: $source_prefix" >&2
      return 1
    fi
    if [ "$provider_sha" != "$source_sha" ]; then
      echo "AgentCanon provider identity mismatch: $provider_sha!=$source_sha" >&2
      return 1
    fi
    printf '%s\n' "$provider_sha"
    return 0
  fi
  printf '%s\n' "$source_sha"
}

agent_canon_receipt_matches_identity() {
  local receipt_path="$1"
  local expected_identity="$2"

  "${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-agent-canon}}" runtime-paths receipt-identity \
    --input "$receipt_path" --expected-identity "$expected_identity" || return 1
}
