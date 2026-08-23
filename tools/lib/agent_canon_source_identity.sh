#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Resolves the selected AgentCanon source identity and validates active-source receipts for shell producers.
# upstream design ../../documents/design/devcontainer/parent-dependency-manifest-followup.md active-source dependency lifecycle and receipt contract.
# upstream design ../../documents/design/rust-agent-tool-migration.md compiled CLI provenance format.
# downstream implementation ../../bootstrap/container/entrypoint.sh container CLI publication.
# downstream implementation ../../tests/agent_tools/test_devcontainer_dependencies.py identity-focused regression fixtures.
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

  python3 - "$receipt_path" "$expected_identity" <<'PY'
import json
import sys

receipt_path, expected_identity = sys.argv[1:]
try:
    with open(receipt_path, encoding="utf-8") as stream:
        payload = json.load(stream)
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"AgentCanon source identity receipt is unavailable: {receipt_path}: {exc}")
observed_identity = payload.get("source_identity")
if observed_identity != expected_identity:
    raise SystemExit(
        "AgentCanon receipt source identity mismatch: "
        f"{observed_identity}!={expected_identity}"
    )
PY
}
