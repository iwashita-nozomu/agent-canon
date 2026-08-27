#!/usr/bin/env bash
# @dependency-start
# contract agent-runtime
# responsibility Owns the host-only Docker/Git adapter for the shared AgentCanon
# container. AgentCanon Python is invoked only through docker exec.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md
# downstream implementation ../../tools/agent_tools/bootstrap_runtime.py
# @dependency-end

set -euo pipefail

# This file deliberately contains no Python fallback. Keeping the adapter in
# POSIX shell makes a fresh checkout usable on hosts that have neither
# ``tomllib`` nor ``tomli`` installed. These are bootstrap-critical constants;
# structured policy remains container-side TOML/JSON.
AGENT_CANON_CONTAINER_CPUS=2
AGENT_CANON_CONTAINER_MEMORY=4g
AGENT_CANON_CONTAINER_PIDS=512
AGENT_CANON_CONTAINER_NETWORK=none
AGENT_CANON_RUNTIME_DESTINATION=/var/lib/agent-canon/runtime
AGENT_CANON_PRIVATE_LOG_DESTINATION=/var/lib/agent-canon/private-log
AGENT_CANON_MOUNT_REGISTRY_DESTINATION=/var/lib/agent-canon/mount-registry.toml
AGENT_CANON_SOURCE_SYNC_DESTINATION=/var/lib/agent-canon/source-sync.json
AGENT_CANON_HEALTH_ATTEMPTS=120
AGENT_CANON_PRIVATE_LOG_ROOT=

_agent_canon_json_error() {
  local code=$1 detail=$2
  printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"error","code":"%s","detail":"%s"}\n' \
    "${code//\\/\\\\}" "${detail//\\/\\\\}" >&2
  return 2
}

_agent_canon_usage() {
  cat <<'USAGE'
usage: bootstrap.sh [--repository-root PATH] --control-parent-root PATH
                    [--runtime-root PATH] [--manifest PATH] OPERATION [OPTIONS]

OPERATION: install | update | start | status | stop | rollback | uninstall |
           sync | scheduler | target | tool | template | codex | eval | task | gc

The host adapter requires Docker and Git only. AgentCanon Python and Rust
tools execute in the resident network-disabled container.
USAGE
}

_agent_canon_operation_usage() {
  local operation=$1
  cat <<USAGE
usage: bootstrap.sh $operation [OPTIONS]

AgentCanon $operation operation. Use bootstrap.sh --help for the complete
host adapter command list.
USAGE
}

_agent_canon_sha256() {
  sha256sum "$1" | awk '{print $1}'
}

_agent_canon_json_escape() {
  local value=$1
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  value=${value//$'\n'/\\n}
  value=${value//$'\r'/\\r}
  value=${value//$'\t'/\\t}
  printf '%s' "$value"
}

_agent_canon_source_sync_write() {
  local status=$1 code=$2 source_root=$3 source_head=$4 source_tree=$5
  local remote=$6 remote_url=$7 branch=$8 updated_at=$9 failure=${10:-}
  [[ "$status" == success || "$status" == failed ]] || return 64
  [[ "$code" =~ ^[a-z][a-z0-9_]*$ ]] || return 64
  if [[ "$status" == success ]]; then
    [[ -z "$failure" ]] || return 64
  else
    [[ "$failure" =~ ^[a-z][a-z0-9_]*$ ]] || return 64
  fi
  [[ "$source_root" == /* && "$source_root" != *$'\n'* && "$source_root" != *$'\r'* ]] || return 64
  [[ "$source_head" == unknown || "$source_head" =~ ^[0-9a-f]{40}$ ]] || return 64
  [[ "$source_tree" == unknown || "$source_tree" =~ ^[0-9a-f]{40}$ ]] || return 64
  [[ "$remote" =~ ^[A-Za-z0-9_.-]+$ ]] || return 64
  [[ "$branch" =~ ^[A-Za-z0-9._/-]+$ ]] || return 64
  [[ "$remote_url" == unknown ||
     ( -n "$remote_url" && "$remote_url" != *$'\n'* && "$remote_url" != *$'\r'* ) ]] || return 64
  [[ "$updated_at" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || return 64

  local state_root=$AGENT_CANON_RUNTIME_ROOT state_path tmp
  [[ ! -L "$state_root" && ! -L "$state_root/source-sync.json" ]] || return 65
  mkdir -p -- "$state_root" || return 66
  tmp=$(mktemp "$state_root/.source-sync.json.XXXXXX") || return 66
  local escaped_root escaped_remote_url escaped_failure
  escaped_root=$(_agent_canon_json_escape "$source_root")
  escaped_remote_url=$(_agent_canon_json_escape "$remote_url")
  escaped_failure=$(_agent_canon_json_escape "$failure")
  state_path="$state_root/source-sync.json"
  if ! {
    printf '{"schema":"agent-canon.source-sync.v1","status":"%s","code":"%s","source_root":"%s","source_head":"%s","source_tree":"%s","remote":"%s","remote_url":"%s","branch":"%s","updated_at":"%s"' \
      "$status" "$code" "$escaped_root" "$source_head" "$source_tree" "$remote" \
      "$escaped_remote_url" "$branch" "$updated_at"
    if [[ "$status" == failed ]]; then
      printf ',"failure":"%s"' "$escaped_failure"
    fi
    printf '}\n'
  } > "$tmp"; then
    rm -f -- "$tmp"
    return 66
  fi
  if ! chmod 600 -- "$tmp"; then
    rm -f -- "$tmp"
    return 66
  fi
  # Test hooks may stop this transition after the complete temporary record is
  # written.  The destination is deliberately untouched until the rename.
  if [[ "${AGENT_CANON_TEST_INTERRUPT_STATE_WRITE:-0}" == 1 ||
        "${AGENT_CANON_TEST_INTERRUPT_SOURCE_SYNC_WRITE:-0}" == 1 ]]; then
    rm -f -- "$tmp"
    return 99
  fi
  if ! mv -f -- "$tmp" "$state_path"; then
    rm -f -- "$tmp"
    return 66
  fi
  return 0
}

_agent_canon_source_sync_json() {
  local state_path="$AGENT_CANON_RUNTIME_ROOT/source-sync.json" state
  if [[ ! -f "$state_path" || -L "$state_path" ]]; then
    printf 'null'
    return 0
  fi
  state=$(<"$state_path") || return 1
  [[ "$state" == \{*\} ]] || return 1
  printf '%s' "$state"
}

_agent_canon_ensure_source_sync_state() {
  local state_path="$AGENT_CANON_RUNTIME_ROOT/source-sync.json"
  if [[ -e "$state_path" || -L "$state_path" ]]; then
    [[ -f "$state_path" && ! -L "$state_path" ]] ||
      _agent_canon_json_error source_sync_state_invalid \
        "source-sync state must be a regular file"
    _agent_canon_source_sync_json >/dev/null ||
      _agent_canon_json_error source_sync_state_invalid \
        "source-sync state is not a JSON object"
    chmod 600 -- "$state_path" ||
      _agent_canon_json_error source_sync_state_invalid \
        "source-sync state permissions could not be restricted"
    return 0
  fi
  local source_head=unknown source_tree=unknown
  source_head=$(git -C "$AGENT_CANON_REPOSITORY_ROOT" rev-parse --verify HEAD 2>/dev/null) || :
  source_tree=$(git -C "$AGENT_CANON_REPOSITORY_ROOT" rev-parse --verify HEAD^{tree} 2>/dev/null) || :
  [[ "$source_head" =~ ^[0-9a-f]{40}$ ]] || source_head=unknown
  [[ "$source_tree" =~ ^[0-9a-f]{40}$ ]] || source_tree=unknown
  _agent_canon_source_sync_write success not_run "$AGENT_CANON_REPOSITORY_ROOT" \
    "$source_head" "$source_tree" origin unknown main \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" ||
    _agent_canon_json_error source_sync_state_write_failed \
      "initial source-sync state could not be atomically published"
}

_agent_canon_source_sync_failure() {
  local code=$1 detail=$2 write_rc=0
  _agent_canon_source_sync_write failed "$code" \
    "${AGENT_CANON_SYNC_SOURCE_ROOT:-$AGENT_CANON_REPOSITORY_ROOT}" \
    "${AGENT_CANON_SYNC_SOURCE_HEAD:-unknown}" \
    "${AGENT_CANON_SYNC_SOURCE_TREE:-unknown}" \
    "${AGENT_CANON_SYNC_REMOTE:-origin}" \
    "${AGENT_CANON_SYNC_REMOTE_URL:-unknown}" \
    "${AGENT_CANON_SYNC_BRANCH:-main}" \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$code" || write_rc=$?
  if ((write_rc != 0)); then
    _agent_canon_json_error source_sync_state_write_failed \
      "source-sync failure state could not be atomically published"
    return 2
  fi
  _agent_canon_json_error "$code" "$detail"
}

_agent_canon_sync_operation() (
  # The source-sync transaction is host-only, so keep its result-state
  # transition here and never ask the resident Python controller to publish a
  # second source-sync record.
  set +e
  local install_root=${AGENT_CANON_REPOSITORY_ROOT:-} remote=origin branch=main
  local sync_index=0 sync_before sync_after candidate_commit staging_root sync_rc=0
  local source_head=unknown source_tree=unknown remote_url=unknown
  AGENT_CANON_SYNC_SOURCE_ROOT=${AGENT_CANON_REPOSITORY_ROOT:-/}
  AGENT_CANON_SYNC_SOURCE_HEAD=unknown
  AGENT_CANON_SYNC_SOURCE_TREE=unknown
  AGENT_CANON_SYNC_REMOTE=$remote
  AGENT_CANON_SYNC_REMOTE_URL=$remote_url
  AGENT_CANON_SYNC_BRANCH=$branch

  while ((sync_index < ${#command_args[@]})); do
    case "${command_args[sync_index]}" in
      sync) ;;
      --install-root)
        ((sync_index += 1))
        if ((sync_index >= ${#command_args[@]})); then
          _agent_canon_source_sync_failure argument_missing "--install-root requires a value"
          exit 2
        fi
        install_root=${command_args[sync_index]}
        ;;
      --remote)
        ((sync_index += 1))
        if ((sync_index >= ${#command_args[@]})); then
          _agent_canon_source_sync_failure argument_missing "--remote requires a value"
          exit 2
        fi
        remote=${command_args[sync_index]}
        ;;
      --branch)
        ((sync_index += 1))
        if ((sync_index >= ${#command_args[@]})); then
          _agent_canon_source_sync_failure argument_missing "--branch requires a value"
          exit 2
        fi
        branch=${command_args[sync_index]}
        ;;
      *)
        _agent_canon_source_sync_failure argument_invalid "unsupported source-sync argument"
        exit 2
        ;;
    esac
    ((sync_index += 1))
  done
  AGENT_CANON_SYNC_REMOTE=$remote
  AGENT_CANON_SYNC_BRANCH=$branch
  [[ "$remote" =~ ^[A-Za-z0-9_.-]+$ ]] || {
    _agent_canon_source_sync_failure argument_invalid "source-sync remote is invalid"
    exit 2
  }
  [[ "$branch" =~ ^[A-Za-z0-9._/-]+$ ]] || {
    _agent_canon_source_sync_failure argument_invalid "source-sync branch is invalid"
    exit 2
  }
  if ! install_root=$(CDPATH= cd -- "$install_root" && pwd -P); then
    _agent_canon_source_sync_failure install_root_invalid "source-sync install root is not a directory"
    exit 2
  fi
  AGENT_CANON_SYNC_SOURCE_ROOT=$install_root

  if ! source_head=$(git -C "$install_root" rev-parse --verify HEAD 2>/dev/null); then
    _agent_canon_source_sync_failure source_sync_git_failed "source checkout HEAD is unavailable"
    exit 2
  fi
  if ! source_tree=$(git -C "$install_root" rev-parse --verify HEAD^{tree} 2>/dev/null); then
    AGENT_CANON_SYNC_SOURCE_HEAD=$source_head
    _agent_canon_source_sync_failure source_sync_git_failed "source checkout tree is unavailable"
    exit 2
  fi
  AGENT_CANON_SYNC_SOURCE_HEAD=$source_head
  AGENT_CANON_SYNC_SOURCE_TREE=$source_tree
  sync_before=$source_head
  if ! remote_url=$(git -C "$install_root" remote get-url "$remote" 2>/dev/null); then
    _agent_canon_source_sync_failure source_remote_unavailable "source-sync remote URL is unavailable"
    exit 2
  fi
  AGENT_CANON_SYNC_REMOTE_URL=$remote_url
  if ! git -C "$install_root" fetch "$remote" "$branch"; then
    _agent_canon_source_sync_failure source_remote_unavailable "source-sync fetch failed"
    exit 2
  fi
  if ! sync_after=$(git -C "$install_root" rev-parse --verify "$remote/$branch" 2>/dev/null); then
    _agent_canon_source_sync_failure source_remote_unavailable "fetched source branch is unavailable"
    exit 2
  fi
  [[ "$sync_after" =~ ^[0-9a-f]{40}$ ]] || {
    _agent_canon_source_sync_failure source_sync_git_failed "fetched source branch identity is invalid"
    exit 2
  }
  if [[ "$sync_before" == "$sync_after" ]]; then
    if ! _agent_canon_source_sync_write success up_to_date "$install_root" \
      "$source_head" "$source_tree" "$remote" "$remote_url" "$branch" \
      "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"; then
      _agent_canon_json_error source_sync_state_write_failed \
        "source-sync success state could not be atomically published"
      exit 2
    fi
    printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"sync","code":"up_to_date","changed":false}\n'
    exit 0
  fi

  candidate_commit=$sync_after
  staging_root="$AGENT_CANON_RUNTIME_ROOT/source-staging/agent-canon"
  if [[ -e "$staging_root" || -L "$staging_root" ]]; then
    rm -rf -- "$staging_root"
  fi
  if ! mkdir -p "$(dirname "$staging_root")"; then
    _agent_canon_source_sync_failure source_sync_staging_failed "source-sync staging directory could not be created"
    exit 2
  fi
  if ! git clone --no-hardlinks "$install_root" "$staging_root"; then
    rm -rf -- "$staging_root"
    _agent_canon_source_sync_failure source_sync_clone_failed "source-sync candidate clone failed"
    exit 2
  fi
  if ! git -C "$staging_root" checkout --detach "$candidate_commit" >/dev/null; then
    rm -rf -- "$staging_root"
    _agent_canon_source_sync_failure source_sync_git_failed "source-sync candidate checkout failed"
    exit 2
  fi
  if AGENT_CANON_SUPPRESS_GLOBAL_LINKS=1 bootstrap_host_entrypoint "$staging_root" \
    --control-parent-root "$AGENT_CANON_CONTROL_ROOT" \
    --runtime-root "$AGENT_CANON_RUNTIME_ROOT" update; then
    :
  else
    sync_rc=$?
    rm -rf -- "$staging_root"
    _agent_canon_source_sync_failure source_sync_candidate_failed \
      "source-sync candidate runtime update failed"
    exit "$sync_rc"
  fi
  if ! git -C "$install_root" merge --ff-only "$remote/$branch"; then
    if ! bootstrap_host_entrypoint "$install_root" \
      --control-parent-root "$AGENT_CANON_CONTROL_ROOT" \
      --runtime-root "$AGENT_CANON_RUNTIME_ROOT" rollback; then
      rm -rf -- "$staging_root"
      _agent_canon_source_sync_failure sync_rollback_failed \
        "source-sync live merge and resident rollback both failed"
      exit 2
    fi
    rm -rf -- "$staging_root"
    _agent_canon_source_sync_failure sync_live_merge_failed \
      "source-sync live source fast-forward failed; resident was restored"
    exit 2
  fi
  if ! source_head=$(git -C "$install_root" rev-parse --verify HEAD 2>/dev/null); then
    _agent_canon_source_sync_failure source_sync_git_failed "merged source checkout HEAD is unavailable"
    exit 2
  fi
  if ! source_tree=$(git -C "$install_root" rev-parse --verify HEAD^{tree} 2>/dev/null); then
    AGENT_CANON_SYNC_SOURCE_HEAD=$source_head
    _agent_canon_source_sync_failure source_sync_git_failed "merged source checkout tree is unavailable"
    exit 2
  fi
  AGENT_CANON_SYNC_SOURCE_HEAD=$source_head
  AGENT_CANON_SYNC_SOURCE_TREE=$source_tree
  # Projection is a live-source operation. The candidate checkout may build
  # and replace the resident, but it must never leave links pointing into the
  # ignored staging tree.
  AGENT_CANON_REPOSITORY_ROOT=$install_root
  sync_rc=0
  _agent_canon_install_global_links || sync_rc=$?
  if ((sync_rc != 0)); then
    if ! bootstrap_host_entrypoint "$install_root" \
      --control-parent-root "$AGENT_CANON_CONTROL_ROOT" \
      --runtime-root "$AGENT_CANON_RUNTIME_ROOT" rollback; then
      rm -rf -- "$staging_root"
      _agent_canon_source_sync_failure sync_rollback_failed \
        "source-sync live link projection and resident rollback both failed"
      exit 2
    fi
    rm -rf -- "$staging_root"
    _agent_canon_source_sync_failure sync_global_links_failed \
      "source-sync live link projection failed; resident was restored"
    exit "$sync_rc"
  fi
  rm -rf -- "$staging_root"
  if ! source_head=$(git -C "$install_root" rev-parse --verify HEAD 2>/dev/null); then
    _agent_canon_source_sync_failure source_sync_git_failed "updated source checkout HEAD is unavailable"
    exit 2
  fi
  if ! source_tree=$(git -C "$install_root" rev-parse --verify HEAD^{tree} 2>/dev/null); then
    AGENT_CANON_SYNC_SOURCE_HEAD=$source_head
    _agent_canon_source_sync_failure source_sync_git_failed "updated source checkout tree is unavailable"
    exit 2
  fi
  AGENT_CANON_SYNC_SOURCE_HEAD=$source_head
  AGENT_CANON_SYNC_SOURCE_TREE=$source_tree
  if ! _agent_canon_source_sync_write success updated "$install_root" \
    "$source_head" "$source_tree" "$remote" "$remote_url" "$branch" \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"; then
    _agent_canon_json_error source_sync_state_write_failed \
      "source-sync updated state could not be atomically published"
    exit 2
  fi
  printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"sync","code":"updated","commit":"%s"}\n' \
    "$candidate_commit"
  exit 0
)

_agent_canon_control_digest() {
  printf '%s' "$AGENT_CANON_CONTROL_ROOT" | sha256sum | awk '{print $1}'
}

_agent_canon_validate_new_path() {
  local path=$1 field=$2 current=/ remaining component
  [[ "$path" == /* ]] ||
    _agent_canon_json_error path_invalid "$field must be absolute"
  remaining=${path#/}
  while [[ -n "$remaining" ]]; do
    if [[ "$remaining" == */* ]]; then
      component=${remaining%%/*}
      remaining=${remaining#*/}
    else
      component=$remaining
      remaining=
    fi
    [[ -n "$component" ]] || continue
    current="$current$component"
    if [[ -L "$current" ]]; then
      _agent_canon_json_error symlink_path_rejected "$field contains a symlink: $current"
    fi
    if [[ -e "$current" && ! -d "$current" ]]; then
      _agent_canon_json_error path_not_directory "$field component is not a directory: $current"
    fi
    current="$current/"
  done
}

_agent_canon_validate_roots() {
  local control runtime default_runtime legacy_runtime
  if ! control=$(realpath -e -- "$AGENT_CANON_CONTROL_ROOT" 2>/dev/null); then
    control=
  fi
  [[ -n "$control" && -d "$control" ]] || {
    _agent_canon_json_error control_root_invalid "control parent root must be an existing directory"
  }
  AGENT_CANON_CONTROL_ROOT=$control
  default_runtime="$AGENT_CANON_REPOSITORY_ROOT/.runtime"
  AGENT_CANON_PRIVATE_LOG_ROOT="$(dirname -- "$AGENT_CANON_REPOSITORY_ROOT")/agent-canon-log"
  _agent_canon_validate_new_path "$default_runtime" "default runtime root"
  _agent_canon_validate_new_path "$AGENT_CANON_PRIVATE_LOG_ROOT" "private log root"
  runtime=$(realpath -m -- "$AGENT_CANON_RUNTIME_ROOT")
  legacy_runtime=$(realpath -m -- "$AGENT_CANON_CONTROL_ROOT/workspace/agent-canon-runtime/host")
  if [[ "$runtime" == "$legacy_runtime" ]]; then
    # The historical default is migration input only.  New state belongs to
    # the source-owned runtime and must never be created under workspace/.
    runtime=$default_runtime
  fi
  if [[ "$runtime" != "$default_runtime" ]]; then
    case "$runtime" in
      "$control"/*) ;;
      *) _agent_canon_json_error runtime_root_escape "explicit runtime root must be beneath control parent root" ;;
    esac
  fi
  AGENT_CANON_RUNTIME_ROOT=$runtime
  export AGENT_CANON_CONTROL_ROOT AGENT_CANON_RUNTIME_ROOT AGENT_CANON_PRIVATE_LOG_ROOT
}

_agent_canon_target_digest() {
  local source=$1 line digest mounted_source destination mode
  while IFS=$'\t' read -r line digest mounted_source destination mode; do
    [[ "$line" == target ]] || continue
    if [[ "$mounted_source" == "$source" ]]; then
      printf '%s\n' "$digest"
      return 0
    fi
  done < "$AGENT_CANON_STATE_ROOT/mounts.tsv"
  return 1
}

_agent_canon_rewrite_target_args() {
  local -a original=("$@")
  local -a rewritten=() digest root
  local index=0
  while ((index < ${#original[@]})); do
    if [[ "${original[index]}" == --root && $((index + 1)) -lt ${#original[@]} ]]; then
      root=${original[index+1]}
      if digest=$(_agent_canon_target_digest "$root"); then
        rewritten+=(--root "/targets/$digest")
        AGENT_CANON_TARGET_DIGEST=$digest
        export AGENT_CANON_TARGET_DIGEST
        index=$((index + 2))
        continue
      fi
    fi
    rewritten+=("${original[index]}")
    index=$((index + 1))
  done
  command_args=("${rewritten[@]}")
}

_agent_canon_extract_exec_target_digest() {
  local -a original=("${command_args[@]}")
  local -a rewritten=()
  local digest= index=0 token found=0
  while ((index < ${#original[@]})); do
    token=${original[index]}
    if [[ "$token" == -- ]]; then
      rewritten+=("${original[@]:index}")
      break
    fi
    if [[ "$token" == --target-digest ]]; then
      ((found == 0)) || _agent_canon_json_error argument_duplicate "exec target digest was provided more than once"
      ((index + 1 < ${#original[@]})) || _agent_canon_json_error argument_missing "--target-digest requires a value"
      digest=${original[index+1]}
      [[ "$digest" =~ ^[A-Za-z0-9_.-]{1,128}$ ]] ||
        _agent_canon_json_error argument_invalid "exec target digest is invalid"
      rewritten+=(--target-digest "$digest")
      found=1
      index=$((index + 2))
      continue
    fi
    if [[ "$token" == --target-digest=* ]]; then
      ((found == 0)) || _agent_canon_json_error argument_duplicate "exec target digest was provided more than once"
      digest=${token#--target-digest=}
      [[ "$digest" =~ ^[A-Za-z0-9_.-]{1,128}$ ]] ||
        _agent_canon_json_error argument_invalid "exec target digest is invalid"
      rewritten+=(--target-digest "$digest")
      found=1
      index=$((index + 1))
      continue
    fi
    rewritten+=("$token")
    index=$((index + 1))
  done
  ((found == 1)) || _agent_canon_json_error argument_missing "structured exec requires --target-digest"
  local kind mounted_digest mounted_source mounted_destination mounted_mode
  while IFS=$'\t' read -r kind mounted_digest mounted_source mounted_destination mounted_mode; do
    if [[ "$kind" == target && "$mounted_digest" == "$digest" ]]; then
      [[ "$mounted_source" = /* && -d "$mounted_source" && ! -L "$mounted_source" &&
         "$mounted_destination" == "/targets/$digest" && "$mounted_mode" == read-only ]] ||
        _agent_canon_json_error mount_manifest_invalid "exec target digest maps to an invalid mount"
      AGENT_CANON_TARGET_DIGEST=$digest
      export AGENT_CANON_TARGET_DIGEST
      command_args=("${rewritten[@]}")
      return 0
    fi
  done < "$AGENT_CANON_STATE_ROOT/mounts.tsv"
  _agent_canon_json_error target_not_registered "exec target digest is absent from the strict mount registry"
}

_agent_canon_exec_is_structured_request() {
  local index=1 token
  while ((index < ${#command_args[@]})); do
    token=${command_args[index]}
    [[ "$token" == -- ]] && return 1
    [[ "$token" == --request-json || "$token" == --request-json=* ]] && return 0
    index=$((index + 1))
  done
  return 1
}

_agent_canon_validate_private_log_mount() {
  local container=$1 source destination writable
  local found=0
  while IFS=$'\t' read -r source destination writable; do
    [[ "$destination" == "$AGENT_CANON_PRIVATE_LOG_DESTINATION" ]] || continue
    ((found == 0)) || _agent_canon_json_error mount_manifest_invalid "private log mount is duplicated"
    [[ "$writable" == false && "$source" == "$AGENT_CANON_PRIVATE_LOG_ROOT" ]] ||
      _agent_canon_json_error mount_manifest_invalid "private log mount differs from the declared source"
    found=1
  done < <("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{range .Mounts}}{{printf "%s\t%s\t%t\n" .Source .Destination .RW}}{{end}}' \
    "$container")
  ((found == 1)) || _agent_canon_json_error mount_manifest_invalid "private log mount is absent"
}

_agent_canon_prepare_host_runtime() {
  AGENT_CANON_STATE_ROOT="$AGENT_CANON_RUNTIME_ROOT/container-state"
  export AGENT_CANON_STATE_ROOT
  [[ ! -L "$AGENT_CANON_RUNTIME_ROOT/host-state" ]] ||
    _agent_canon_json_error active_image_invalid "host-owned image state directory must not be a symlink"
  mkdir -p "$AGENT_CANON_RUNTIME_ROOT" \
    "$AGENT_CANON_RUNTIME_ROOT/host-state" \
    "$AGENT_CANON_STATE_ROOT/container-runtime" \
    "$AGENT_CANON_STATE_ROOT/receipts" \
    "$AGENT_CANON_STATE_ROOT/tasks" \
    "$AGENT_CANON_STATE_ROOT/generations" \
    "$AGENT_CANON_STATE_ROOT/spool" \
    "$AGENT_CANON_STATE_ROOT/archive" \
    "$AGENT_CANON_STATE_ROOT/cache" \
    "$AGENT_CANON_STATE_ROOT/codex-home" \
    "$AGENT_CANON_PRIVATE_LOG_ROOT"
  chmod 700 "$AGENT_CANON_RUNTIME_ROOT" "$AGENT_CANON_RUNTIME_ROOT/host-state" "$AGENT_CANON_STATE_ROOT"
  chmod 700 "$AGENT_CANON_PRIVATE_LOG_ROOT"
  chmod 1777 "$AGENT_CANON_STATE_ROOT/container-runtime"
  _agent_canon_ensure_source_sync_state
  [[ -e "$AGENT_CANON_STATE_ROOT/mounts.toml" ]] || : > "$AGENT_CANON_STATE_ROOT/mounts.toml"
  [[ -e "$AGENT_CANON_STATE_ROOT/mounts.tsv" ]] || : > "$AGENT_CANON_STATE_ROOT/mounts.tsv"
}

_agent_canon_container_exec() {
  local container=$1
  shift
  local image_id container_id source_head
  image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect --format '{{.Id}}' "$AGENT_CANON_IMAGE_REF")
  container_id=$("$AGENT_CANON_DOCKER_CMD" container inspect --format '{{.Id}}' "$container")
  source_head=$(git -C "$AGENT_CANON_REPOSITORY_ROOT" rev-parse --verify HEAD)
  local -a extra_env=()
  [[ -n "${AGENT_CANON_RESTORE_IMAGE_ID:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_RESTORE_IMAGE_ID=$AGENT_CANON_RESTORE_IMAGE_ID")
  [[ -n "${AGENT_CANON_CURRENT_IMAGE_ID:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_CURRENT_IMAGE_ID=$AGENT_CANON_CURRENT_IMAGE_ID")
  [[ -n "${AGENT_CANON_CURRENT_IMAGE_REF:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_CURRENT_IMAGE_REF=$AGENT_CANON_CURRENT_IMAGE_REF")
  [[ -n "${AGENT_CANON_RESTORE_IMAGE_REF:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_RESTORE_IMAGE_REF=$AGENT_CANON_RESTORE_IMAGE_REF")
  [[ -n "${AGENT_CANON_PREVIOUS_IMAGE_ID:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_PREVIOUS_IMAGE_ID=$AGENT_CANON_PREVIOUS_IMAGE_ID")
  [[ -n "${AGENT_CANON_PREVIOUS_IMAGE_REF:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_PREVIOUS_IMAGE_REF=$AGENT_CANON_PREVIOUS_IMAGE_REF")
  [[ -n "${AGENT_CANON_RESTORE_TARGETS_FILE:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_RESTORE_TARGETS_FILE=$AGENT_CANON_RESTORE_TARGETS_FILE")
  [[ -n "${AGENT_CANON_REPOSITORY_ROOT:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_HOST_INSTALL_ROOT=$AGENT_CANON_REPOSITORY_ROOT")
  [[ -n "${AGENT_CANON_TARGET_HOST_ROOT:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_TARGET_HOST_ROOT=$AGENT_CANON_TARGET_HOST_ROOT")
  [[ -n "${AGENT_CANON_TARGET_CONTAINER_ROOT:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_TARGET_CONTAINER_ROOT=$AGENT_CANON_TARGET_CONTAINER_ROOT")
  [[ -n "${AGENT_CANON_TARGET_DIGEST:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_TARGET_DIGEST=$AGENT_CANON_TARGET_DIGEST")
  [[ -n "${AGENT_CANON_PRIVATE_LOG_ROOT:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_PRIVATE_LOG_ROOT=$AGENT_CANON_PRIVATE_LOG_ROOT")
  "$AGENT_CANON_DOCKER_CMD" exec \
    --workdir "$AGENT_CANON_RUNTIME_DESTINATION" \
    --env "AGENT_CANON_CONTAINER_CONTROL=1" \
    --env "AGENT_CANON_IMAGE_REF=$AGENT_CANON_IMAGE_REF" \
    --env "AGENT_CANON_CONTROL_ROOT_DIGEST=$(_agent_canon_control_digest)" \
    --env "AGENT_CANON_CONTAINER_NAME=$(_agent_canon_container_name)" \
    --env "AGENT_CANON_IMAGE_OWNED=1" \
    --env "AGENT_CANON_IMAGE_ID=$image_id" \
    --env "AGENT_CANON_CONTAINER_ID=$container_id" \
    --env "AGENT_CANON_SOURCE_HEAD=$source_head" \
    "${extra_env[@]}" \
    "$container" "$@"
}

_agent_canon_scheduler() {
  local action=${1:-status}
  local service_dir=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
  local service_path=$service_dir/agent-canon-sync.service
  local timer_path=$service_dir/agent-canon-sync.timer
  case "$action" in
    enable)
      mkdir -p "$service_dir"
      local service_text timer_text
      service_text=$(<"$AGENT_CANON_REPOSITORY_ROOT/bootstrap/systemd/user/agent-canon-sync.service.in")
      timer_text=$(<"$AGENT_CANON_REPOSITORY_ROOT/bootstrap/systemd/user/agent-canon-sync.timer.in")
      service_text=${service_text//@BOOTSTRAP@/$AGENT_CANON_REPOSITORY_ROOT/bootstrap.sh}
      service_text=${service_text//@CONTROL_ROOT@/$AGENT_CANON_CONTROL_ROOT}
      service_text=${service_text//@RUNTIME_ROOT@/$AGENT_CANON_RUNTIME_ROOT}
      service_text=${service_text//@INSTALL_ROOT@/$AGENT_CANON_REPOSITORY_ROOT}
      service_text=${service_text//@REMOTE@/origin}
      service_text=${service_text//@BRANCH@/main}
      timer_text=${timer_text//@ON_BOOT@/300}
      timer_text=${timer_text//@INTERVAL@/900}
      printf '%s\n' "$service_text" > "$service_path"
      printf '%s\n' "$timer_text" > "$timer_path"
      systemctl --user daemon-reload
      systemctl --user enable --now agent-canon-sync.timer
      printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"scheduler","code":"scheduler_enabled"}\n'
      ;;
    disable)
      systemctl --user disable --now agent-canon-sync.timer
      printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"scheduler","code":"scheduler_disabled"}\n'
      ;;
    status)
      systemctl --user show agent-canon-sync.timer --property=ActiveState,UnitFileState
      ;;
    uninstall)
      if ! systemctl --user disable --now agent-canon-sync.timer 2>/dev/null; then
        :
      fi
      rm -f -- "$service_path" "$timer_path"
      if ! systemctl --user daemon-reload 2>/dev/null; then
        :
      fi
      printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"scheduler","code":"scheduler_uninstalled"}\n'
      ;;
    *)
      _agent_canon_json_error unsupported_operation "unsupported scheduler operation: $action"
      ;;
  esac
}

_agent_canon_image() {
  local requested_ref=${1:-}
  if [[ -n "$requested_ref" ]]; then
    AGENT_CANON_IMAGE_REF=$requested_ref
    "$AGENT_CANON_DOCKER_CMD" pull "$AGENT_CANON_IMAGE_REF"
    return
  fi
  local source_head manifest_digest control_digest
  source_head=$(git -C "$AGENT_CANON_REPOSITORY_ROOT" rev-parse --verify HEAD) || \
    _agent_canon_json_error source_snapshot_failed "AgentCanon source is not a Git checkout"
  manifest_digest=$(_agent_canon_sha256 "$AGENT_CANON_REPOSITORY_ROOT/bootstrap/manifest.toml")
  control_digest=$(_agent_canon_control_digest)
  AGENT_CANON_IMAGE_REF="agent-canon-tools:${control_digest:0:16}-${manifest_digest:0:16}-${source_head:0:16}"
  if "$AGENT_CANON_DOCKER_CMD" image inspect "$AGENT_CANON_IMAGE_REF" >/dev/null 2>&1 &&
     [[ "${AGENT_CANON_FORCE_BUILD:-0}" != 1 ]]; then
    return
  fi
  if [[ "${AGENT_CANON_ALLOW_BUILD:-0}" != 1 ]]; then
    _agent_canon_json_error image_missing "AgentCanon tool image is not installed"
  fi
  if [[ "${AGENT_CANON_FORCE_BUILD:-0}" == 1 ]] || \
     ! "$AGENT_CANON_DOCKER_CMD" image inspect "$AGENT_CANON_IMAGE_REF" >/dev/null 2>&1; then
    "$AGENT_CANON_DOCKER_CMD" build \
      --file "$AGENT_CANON_REPOSITORY_ROOT/bootstrap/container/Dockerfile" \
      --tag "$AGENT_CANON_IMAGE_REF" \
      --label io.agent-canon.runtime=shared-v1 \
      --label "io.agent-canon.control-root-digest=$control_digest" \
      --label "io.agent-canon.source-revision=$source_head" \
      "$AGENT_CANON_REPOSITORY_ROOT"
  fi
}

_agent_canon_write_active_image() {
  local image_ref=$1 image_id=$2
  [[ "$image_ref" =~ ^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,255}$ &&
     "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] ||
    _agent_canon_json_error active_image_invalid "active image identity is invalid"
  local path="$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" temporary
  temporary=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/host-state/.active-image.XXXXXX")
  {
    printf 'schema\tagent-canon.active-image.v1\n'
    printf 'image-ref\t%s\n' "$image_ref"
    printf 'image-id\t%s\n' "$image_id"
  } > "$temporary"
  chmod 600 "$temporary"
  mv -f -- "$temporary" "$path"
  AGENT_CANON_IMAGE_REF=$image_ref
  AGENT_CANON_ACTIVE_IMAGE_ID=$image_id
  AGENT_CANON_EXPECTED_IMAGE_ID=$image_id
  export AGENT_CANON_IMAGE_REF AGENT_CANON_ACTIVE_IMAGE_ID AGENT_CANON_EXPECTED_IMAGE_ID
}

_agent_canon_read_active_image() {
  local path="$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv"
  [[ -f "$path" && ! -L "$path" ]] ||
    _agent_canon_json_error active_image_missing "active resident image state is missing"
  local key value schema= image_ref= image_id=
  local schema_count=0 ref_count=0 id_count=0
  while IFS=$'\t' read -r key value; do
    [[ -n "$key" && -n "$value" && "$value" != *$'\t'* && "$value" != *$'\n'* && "$value" != *$'\r'* ]] ||
      _agent_canon_json_error active_image_invalid "active image state contains an invalid row"
    case "$key" in
      schema) schema=$value; schema_count=$((schema_count + 1)) ;;
      image-ref) image_ref=$value; ref_count=$((ref_count + 1)) ;;
      image-id) image_id=$value; id_count=$((id_count + 1)) ;;
      *) _agent_canon_json_error active_image_invalid "active image state contains an unknown key: $key" ;;
    esac
  done < "$path"
  [[ "$schema_count" -eq 1 && "$schema" == agent-canon.active-image.v1 &&
     "$ref_count" -eq 1 && "$id_count" -eq 1 ]] ||
    _agent_canon_json_error active_image_invalid "active image state fields are incomplete"
  [[ "$image_ref" =~ ^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,255}$ &&
     "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] ||
    _agent_canon_json_error active_image_invalid "active image identity is invalid"
  AGENT_CANON_IMAGE_REF=$image_ref
  AGENT_CANON_ACTIVE_IMAGE_ID=$image_id
  AGENT_CANON_EXPECTED_IMAGE_ID=$image_id
  export AGENT_CANON_IMAGE_REF AGENT_CANON_ACTIVE_IMAGE_ID AGENT_CANON_EXPECTED_IMAGE_ID
}

_agent_canon_use_active_image() {
  local container=${1:-}
  if [[ -f "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" ]]; then
    _agent_canon_read_active_image
    return 0
  fi
  if [[ -n "$container" ]] && "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
    _agent_canon_migrate_active_image "$container"
    return 0
  fi
  _agent_canon_json_error active_image_missing "active resident image state is missing"
}

_agent_canon_migrate_active_image() {
  local container=$1 image_ref image_id
  if ! image_ref=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.Config.Image}}' "$container" 2>/dev/null); then
    _agent_canon_json_error active_image_migration_failed "resident image reference readback failed"
  fi
  if ! image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
    --format '{{.Id}}' "$image_ref" 2>/dev/null); then
    _agent_canon_json_error active_image_migration_failed "resident image ID readback failed"
  fi
  AGENT_CANON_IMAGE_REF=$image_ref
  AGENT_CANON_EXPECTED_IMAGE_ID=$image_id
  export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID
  # Full owner/security/mount validation is the migration gate.  The exact
  # Config.Image and immutable ID are adopted only after that readback.
  _agent_canon_validate_existing_container "$container"
  _agent_canon_write_active_image "$image_ref" "$image_id"
}

_agent_canon_record_active_container() {
  local container=$1 image_ref image_id
  if ! image_ref=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.Config.Image}}' "$container" 2>/dev/null); then
    _agent_canon_json_error active_image_readback_failed "resident image reference readback failed"
  fi
  if ! image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
    --format '{{.Id}}' "$image_ref" 2>/dev/null); then
    _agent_canon_json_error active_image_readback_failed "resident image ID readback failed"
  fi
  _agent_canon_write_active_image "$image_ref" "$image_id"
}

_agent_canon_write_rollback_plan() {
  local image_id=$1 image_ref=$2 plan="$AGENT_CANON_STATE_ROOT/rollback-plan.tsv"
  [[ "$image_id" == sha256:* && -n "$image_ref" ]] ||
    _agent_canon_json_error rollback_plan_invalid "previous image identity is incomplete"
  local rollback_ref="agent-canon-tools:$(_agent_canon_control_digest | cut -c1-16)-rollback-${image_id#sha256:}"
  rollback_ref=${rollback_ref:0:128}
  if ! "$AGENT_CANON_DOCKER_CMD" tag "$image_id" "$rollback_ref"; then
    _agent_canon_json_error rollback_plan_invalid "previous image could not be retained under rollback tag"
  fi
  {
    printf 'schema\tagent-canon.rollback-plan.v1\n'
    printf 'image-id\t%s\n' "$image_id"
    printf 'image-ref\t%s\n' "$rollback_ref"
    printf 'mount\tmount\t%s\t%s\tfalse\n' "$AGENT_CANON_STATE_ROOT" "$AGENT_CANON_RUNTIME_DESTINATION"
    printf 'mount\tmount\t%s\t%s\ttrue\n' "$AGENT_CANON_RUNTIME_ROOT/source-sync.json" "$AGENT_CANON_SOURCE_SYNC_DESTINATION"
    printf 'mount\tmount\t%s\t%s\ttrue\n' "$AGENT_CANON_PRIVATE_LOG_ROOT" "$AGENT_CANON_PRIVATE_LOG_DESTINATION"
    printf 'mount\tmount\t%s\t%s\ttrue\n' "$AGENT_CANON_STATE_ROOT/mounts.toml" "$AGENT_CANON_MOUNT_REGISTRY_DESTINATION"
    if [[ -f "$AGENT_CANON_STATE_ROOT/mounts.tsv" && ! -L "$AGENT_CANON_STATE_ROOT/mounts.tsv" ]]; then
      local kind digest source destination mode
      while IFS=$'\t' read -r kind digest source destination mode; do
        [[ -z "$kind" ]] && continue
        [[ "$kind" == target && "$destination" == "/targets/$digest" && "$mode" == read-only ]] ||
          _agent_canon_json_error rollback_plan_invalid "target mount manifest is invalid"
        printf 'mount\tmount\t%s\t%s\ttrue\n' "$source" "$destination"
      done < "$AGENT_CANON_STATE_ROOT/mounts.tsv"
    fi
  } > "$plan"
}

_agent_canon_read_rollback_plan() {
  local plan="$AGENT_CANON_STATE_ROOT/rollback-plan.tsv"
  [[ -f "$plan" && ! -L "$plan" ]] ||
    _agent_canon_json_error rollback_unavailable "rollback plan is missing"
  local key value source destination ro
  local schema_seen=0 image_seen=0 ref_seen=0
  local previous_mounts="$AGENT_CANON_STATE_ROOT/rollback-mounts.tsv"
  AGENT_CANON_ROLLBACK_IMAGE_ID=
  AGENT_CANON_ROLLBACK_IMAGE_REF=
  : > "$previous_mounts"
  while IFS=$'\t' read -r key value source destination ro; do
    case "$key" in
      schema)
        [[ "$value" == agent-canon.rollback-plan.v1 && -z "$source$destination$ro" ]] ||
          _agent_canon_json_error rollback_plan_invalid "rollback plan schema is invalid"
        schema_seen=$((schema_seen + 1)) ;;
      image-id)
        [[ "$value" == sha256:* && -z "$source$destination$ro" ]] ||
          _agent_canon_json_error rollback_plan_invalid "rollback plan image ID is invalid"
        AGENT_CANON_ROLLBACK_IMAGE_ID=$value; image_seen=$((image_seen + 1)) ;;
      image-ref)
        [[ -n "$value" && -z "$source$destination$ro" ]] ||
          _agent_canon_json_error rollback_plan_invalid "rollback plan image reference is invalid"
        AGENT_CANON_ROLLBACK_IMAGE_REF=$value; ref_seen=$((ref_seen + 1)) ;;
      mount)
        [[ "$value" == mount && -n "$source" && "$source" = /* && ! -L "$source" &&
           ( -d "$source" || ("$destination" == "$AGENT_CANON_SOURCE_SYNC_DESTINATION" && -f "$source") ) &&
           -n "$destination" && ("$ro" == true || "$ro" == false) ]] ||
          _agent_canon_json_error rollback_plan_invalid "rollback plan mount is invalid"
        case "$destination" in
          /targets/*)
            digest=${destination#/targets/}
            [[ "$digest" =~ ^[A-Za-z0-9_.-]{1,128}$ && "$value" == mount ]] ||
              _agent_canon_json_error rollback_plan_invalid "rollback target destination is invalid"
            printf 'target\t%s\t%s\t%s\tread-only\n' "$digest" "$source" "$destination" >> "$previous_mounts" ;;
          /var/lib/agent-canon/*) ;;
          *) _agent_canon_json_error rollback_plan_invalid "rollback destination is invalid" ;;
        esac ;;
      *) _agent_canon_json_error rollback_plan_invalid "rollback plan contains an unknown key: $key" ;;
    esac
  done < "$plan"
  [[ $schema_seen -eq 1 && $image_seen -eq 1 && $ref_seen -eq 1 ]] ||
    _agent_canon_json_error rollback_plan_invalid "rollback plan is incomplete"
  AGENT_CANON_ROLLBACK_MOUNTS_FILE=$previous_mounts
  export AGENT_CANON_ROLLBACK_MOUNTS_FILE
}

_agent_canon_validate_existing_container() {
  local container=$1
  local mount_manifest=${2:-${AGENT_CANON_ROLLBACK_MOUNTS_FILE:-$AGENT_CANON_STATE_ROOT/mounts.tsv}}
  local include_pending=${3:-1}
  local observed_runtime observed_control observed_image observed_image_id observed_network
  local observed_rootfs observed_capdrop observed_security observed_cpus
  local observed_memory observed_pids observed_mounts expected_mounts mount_manifest
  local require_source_sync=${4:-1}
  if ! observed_runtime=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{index .Config.Labels "io.agent-canon.runtime"}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident container inspect failed"
  fi
  observed_control=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{index .Config.Labels "io.agent-canon.control-root-digest"}}' "$container")
  observed_image=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.Config.Image}}' "$container")
  observed_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
    --format '{{.Id}}' "$observed_image")
  observed_network=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.HostConfig.NetworkMode}}' "$container")
  observed_rootfs=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.HostConfig.ReadonlyRootfs}}' "$container")
  observed_capdrop=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{join .HostConfig.CapDrop ","}}' "$container")
  observed_security=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{join .HostConfig.SecurityOpt ","}}' "$container")
  observed_cpus=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.HostConfig.NanoCpus}}' "$container")
  observed_memory=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.HostConfig.Memory}}' "$container")
  observed_pids=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.HostConfig.PidsLimit}}' "$container")
  if [[ "$observed_runtime" != shared-v1 ||
        "$observed_control" != "$(_agent_canon_control_digest)" ||
        "$observed_image" != "$AGENT_CANON_IMAGE_REF" ||
        ( -n "${AGENT_CANON_EXPECTED_IMAGE_ID:-}" && "$observed_image_id" != "$AGENT_CANON_EXPECTED_IMAGE_ID" ) ||
        "$observed_network" != "$AGENT_CANON_CONTAINER_NETWORK" ||
        "$observed_rootfs" != true ||
        "$observed_capdrop" != ALL ||
        "$observed_security" != no-new-privileges ||
        "$observed_cpus" != 2000000000 ||
        "$observed_memory" != 4294967296 ||
        "$observed_pids" != 512 ]]; then
    _agent_canon_json_error container_ownership_mismatch "named resident has unexpected owner, image, mount, or security configuration"
  fi
  expected_mounts=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.expected-mounts.XXXXXX")
  observed_mounts=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.observed-mounts.XXXXXX")
  printf '%s\t%s\ttrue\n' "$AGENT_CANON_STATE_ROOT" "$AGENT_CANON_RUNTIME_DESTINATION" > "$expected_mounts"
  if [[ "$require_source_sync" == 1 ]]; then
    printf '%s\t%s\tfalse\n' "$AGENT_CANON_RUNTIME_ROOT/source-sync.json" "$AGENT_CANON_SOURCE_SYNC_DESTINATION" >> "$expected_mounts"
  fi
  printf '%s\t%s\tfalse\n' "$AGENT_CANON_PRIVATE_LOG_ROOT" "$AGENT_CANON_PRIVATE_LOG_DESTINATION" >> "$expected_mounts"
  printf '%s\t%s\tfalse\n' "$AGENT_CANON_STATE_ROOT/mounts.toml" "$AGENT_CANON_MOUNT_REGISTRY_DESTINATION" >> "$expected_mounts"
  if [[ -f "$mount_manifest" && ! -L "$mount_manifest" ]]; then
    local kind digest source destination mode
    while IFS=$'\t' read -r kind digest source destination mode; do
      [[ -z "$kind" ]] && continue
      [[ "$kind" == target && "$digest" =~ ^[A-Za-z0-9_.-]{1,128}$ && "$source" = /* && -d "$source" && ! -L "$source" && "$destination" == "/targets/$digest" && "$mode" == read-only ]] ||
        _agent_canon_json_error mount_manifest_invalid "target mount manifest is invalid during readback"
      printf '%s\t%s\tfalse\n' "$source" "$destination" >> "$expected_mounts"
    done < "$mount_manifest"
  fi
  if [[ "$include_pending" == 1 && -n "${AGENT_CANON_TARGET_PENDING_SOURCE:-}" ]]; then
    printf '%s\t%s\tfalse\n' "$AGENT_CANON_TARGET_PENDING_SOURCE" \
      "/targets/$AGENT_CANON_TARGET_PENDING_DIGEST" >> "$expected_mounts"
  fi
  "$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{range .Mounts}}{{printf "%s\t%s\t%t\n" .Source .Destination .RW}}{{end}}' \
    "$container" | sed '/^$/d' | sort > "$observed_mounts"
  sort -o "$expected_mounts" "$expected_mounts"
  if ! diff -u "$expected_mounts" "$observed_mounts" >/dev/null; then
    rm -f -- "$expected_mounts" "$observed_mounts"
    _agent_canon_json_error container_ownership_mismatch "resident bind mount set differs from the expected complete manifest"
  fi
  rm -f -- "$expected_mounts" "$observed_mounts"
}

_agent_canon_container_name() {
  local control_digest
  control_digest=$(printf '%s' "$AGENT_CANON_CONTROL_ROOT" | sha256sum | awk '{print $1}')
  printf 'agent-canon-tools-%s\n' "${control_digest:0:16}"
}

_agent_canon_ensure_container() {
  local container=$(_agent_canon_container_name)
  local -a target_mount_args=()
  local target_source target_digest target_destination target_mode
  local target_manifest="${AGENT_CANON_ROLLBACK_MOUNTS_FILE:-$AGENT_CANON_STATE_ROOT/mounts.tsv}"
  while IFS=$'\t' read -r target_kind target_digest target_source target_destination target_mode; do
    [[ -n "$target_kind" ]] || continue
    [[ "$target_kind" == target && "$target_digest" =~ ^[A-Za-z0-9_.-]{1,128}$ ]] ||
      _agent_canon_json_error mount_manifest_invalid "invalid target mount record"
    [[ "$target_source" = /* && -d "$target_source" && ! -L "$target_source" ]] ||
      _agent_canon_json_error mount_manifest_invalid "target mount source is not a regular directory"
    [[ "$target_source" != "$AGENT_CANON_CONTROL_ROOT" && "$target_source" != "$(realpath -e -- "$HOME")" ]] ||
      _agent_canon_json_error mount_manifest_invalid "broad control or home mount is forbidden"
    [[ "$target_destination" == "/targets/$target_digest" && "$target_mode" == read-only ]] ||
      _agent_canon_json_error mount_manifest_invalid "target mount destination or mode is invalid"
    target_mount_args+=(--mount "type=bind,src=$target_source,dst=$target_destination,readonly")
  done < "$target_manifest"
  if [[ -n "${AGENT_CANON_TARGET_PENDING_SOURCE:-}" ]]; then
    target_mount_args+=(
      --mount "type=bind,src=$AGENT_CANON_TARGET_PENDING_SOURCE,dst=/targets/$AGENT_CANON_TARGET_PENDING_DIGEST,readonly"
    )
  fi
  if "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
    _agent_canon_validate_existing_container "$container"
  else
    "$AGENT_CANON_DOCKER_CMD" create \
      --name "$container" \
      --read-only \
      --cap-drop ALL \
      --security-opt no-new-privileges \
      --network "$AGENT_CANON_CONTAINER_NETWORK" \
      --cpus "$AGENT_CANON_CONTAINER_CPUS" \
      --memory "$AGENT_CANON_CONTAINER_MEMORY" \
      --pids-limit "$AGENT_CANON_CONTAINER_PIDS" \
      --tmpfs /tmp \
      --label io.agent-canon.runtime=shared-v1 \
      --label "io.agent-canon.control-root-digest=$(_agent_canon_control_digest)" \
      --mount "type=bind,src=$AGENT_CANON_STATE_ROOT,dst=$AGENT_CANON_RUNTIME_DESTINATION" \
      --mount "type=bind,src=$AGENT_CANON_RUNTIME_ROOT/source-sync.json,dst=$AGENT_CANON_SOURCE_SYNC_DESTINATION,readonly" \
      --mount "type=bind,src=$AGENT_CANON_PRIVATE_LOG_ROOT,dst=$AGENT_CANON_PRIVATE_LOG_DESTINATION,readonly" \
      --mount "type=bind,src=$AGENT_CANON_STATE_ROOT/mounts.toml,dst=$AGENT_CANON_MOUNT_REGISTRY_DESTINATION,readonly" \
      "${target_mount_args[@]}" \
      "$AGENT_CANON_IMAGE_REF" >/dev/null
    _agent_canon_validate_existing_container "$container"
  fi
  local running
  running=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.State.Running}}' "$container" 2>/dev/null || printf false)
  if [[ "$running" != true ]]; then
    "$AGENT_CANON_DOCKER_CMD" start "$container" >/dev/null
  fi
  local attempts=0 health
  while ((attempts < AGENT_CANON_HEALTH_ATTEMPTS)); do
    health=$("$AGENT_CANON_DOCKER_CMD" container inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}starting{{end}}' \
      "$container" 2>/dev/null || printf missing)
    [[ "$health" == healthy ]] && { printf '%s\n' "$container"; return; }
    [[ "$health" == missing ]] && _agent_canon_json_error runtime_unavailable "resident container disappeared"
    sleep 1
    attempts=$((attempts + 1))
  done
  _agent_canon_json_error container_unhealthy "resident container did not become healthy"
}

_agent_canon_run_controller() {
  local container=$1
  shift
  local output_file error_file rc=0
  output_file=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.bootstrap.stdout.XXXXXX")
  error_file=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.bootstrap.stderr.XXXXXX")
  _agent_canon_container_exec "$container" \
    python3 /usr/local/share/agent-canon/runtime/tools/agent_tools/bootstrap_runtime.py \
    --container-control \
    --repository-root /usr/local/share/agent-canon/runtime \
    --control-parent-root /var/lib/agent-canon \
    --runtime-root /var/lib/agent-canon/runtime \
    "$@" >"$output_file" 2>"$error_file" || rc=$?
  cat "$output_file"
  cat "$error_file" >&2
  rm -f -- "$output_file" "$error_file"
  return "$rc"
}

_agent_canon_restore_candidate_failure() {
  local container=$1 old_image_id=$2 candidate_image_id=$3
  local restore_output restore_error restore_rc=0
  local recovery_errors=()
  AGENT_CANON_RESTORE_IMAGE_ID=$old_image_id
  export AGENT_CANON_RESTORE_IMAGE_ID
  restore_output=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.bootstrap.restore.stdout.XXXXXX")
  restore_error=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.bootstrap.restore.stderr.XXXXXX")
  if _agent_canon_container_exec "$container" \
    python3 /usr/local/share/agent-canon/runtime/tools/agent_tools/bootstrap_runtime.py \
    --container-control \
    --repository-root /usr/local/share/agent-canon/runtime \
    --control-parent-root /var/lib/agent-canon \
    --runtime-root /var/lib/agent-canon/runtime \
    restore >"$restore_output" 2>"$restore_error"; then
    :
  else
    restore_rc=$?
    recovery_errors+=("state_restore_exit=$restore_rc")
  fi
  rm -f -- "$restore_output" "$restore_error"
  unset AGENT_CANON_RESTORE_IMAGE_ID
  if ! "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$container" >/dev/null 2>&1; then
    recovery_errors+=("candidate_stop_failed")
  fi
  if ! "$AGENT_CANON_DOCKER_CMD" rm "$container" >/dev/null 2>&1; then
    recovery_errors+=("candidate_remove_failed")
  fi
  AGENT_CANON_IMAGE_REF=$old_image_id
  AGENT_CANON_EXPECTED_IMAGE_ID=$old_image_id
  export AGENT_CANON_IMAGE_REF
  export AGENT_CANON_EXPECTED_IMAGE_ID
  local restored
  if ! restored=$(_agent_canon_ensure_container); then
    recovery_errors+=("previous_container_start_failed")
  elif ! _agent_canon_run_controller "$restored" start >/dev/null; then
    recovery_errors+=("previous_state_start_failed")
  fi
  if [[ -n "$candidate_image_id" && "$candidate_image_id" != "$old_image_id" ]]; then
    if ! "$AGENT_CANON_DOCKER_CMD" image rm "$candidate_image_id" >/dev/null 2>&1; then
      recovery_errors+=("candidate_image_remove_failed")
    fi
  fi
  if ((${#recovery_errors[@]})); then
    _agent_canon_json_error rollback_failed "previous resident restoration failed: ${recovery_errors[*]}"
  fi
  return 0
}

_agent_canon_replace_resident_locked() {
  local candidate_image_ref=$1 candidate_image_id=$2
  local old_image_id old_image_ref old_container candidate restored rc
  if ! candidate_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect --format '{{.Id}}' "$candidate_image_ref"); then
    _agent_canon_json_error candidate_image_missing "candidate resident image disappeared before replacement"
    return 2
  fi
  old_container=$(_agent_canon_container_name)
  old_image_ref=
  old_image_id=
  AGENT_CANON_IMAGE_REF=$candidate_image_ref
  AGENT_CANON_EXPECTED_IMAGE_ID=$candidate_image_id
  export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID

  # This readback happens after the replacement lock is acquired.  A build
  # may have completed while another update owned the resident, so the
  # resident state—not the caller's pre-lock snapshot—is authoritative.
  if [[ -f "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" ]] ||
     "$AGENT_CANON_DOCKER_CMD" container inspect "$old_container" >/dev/null 2>&1; then
    if ! _agent_canon_use_active_image "$old_container"; then
      _agent_canon_json_error replacement_readback_failed "active resident image could not be re-read after lock acquisition"
      return 2
    fi
    old_image_ref=$AGENT_CANON_IMAGE_REF
    old_image_id=$AGENT_CANON_ACTIVE_IMAGE_ID
    if [[ -n "$old_image_id" && "$old_image_id" == "$candidate_image_id" &&
          "$old_image_ref" == "$candidate_image_ref" &&
          -n "$candidate_image_id" ]] &&
       "$AGENT_CANON_DOCKER_CMD" container inspect "$old_container" >/dev/null 2>&1; then
      # The first updater already completed the transaction.  Revalidate the
      # exact resident and health path, then converge without stop/rm/create.
      AGENT_CANON_IMAGE_REF=$candidate_image_ref
      AGENT_CANON_EXPECTED_IMAGE_ID=$candidate_image_id
      export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID
      if ! candidate=$(_agent_canon_ensure_container); then
        _agent_canon_json_error candidate_ensure_failed "existing candidate resident could not be revalidated"
        return 2
      fi
      if ! _agent_canon_record_active_container "$candidate"; then
        _agent_canon_json_error active_image_write_failed "active candidate image state could not be updated"
        return 2
      fi
      printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"update","code":"up_to_date","changed":false}\n'
      return 0
    fi
    AGENT_CANON_IMAGE_REF=$old_image_ref
    AGENT_CANON_EXPECTED_IMAGE_ID=$old_image_id
    export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID
    printf '%s\n' "$old_image_id" > "$AGENT_CANON_STATE_ROOT/previous-image-id"
    AGENT_CANON_PREVIOUS_IMAGE_REF=$old_image_ref
    export AGENT_CANON_PREVIOUS_IMAGE_REF
    if "$AGENT_CANON_DOCKER_CMD" container inspect "$old_container" >/dev/null 2>&1; then
      if ! _agent_canon_validate_existing_container "$old_container" "$AGENT_CANON_STATE_ROOT/mounts.tsv" 1 0; then
        _agent_canon_json_error replacement_readback_failed "old resident mount readback failed before replacement"
        return 2
      fi
      if ! _agent_canon_write_rollback_plan "$old_image_id" "$old_image_ref"; then
        _agent_canon_json_error rollback_plan_invalid "old resident rollback plan could not be written"
        return 2
      fi
    fi
  else
    unset AGENT_CANON_EXPECTED_IMAGE_ID AGENT_CANON_ACTIVE_IMAGE_ID
  fi

  AGENT_CANON_IMAGE_REF=$candidate_image_ref
  AGENT_CANON_EXPECTED_IMAGE_ID=$candidate_image_id
  AGENT_CANON_PREVIOUS_IMAGE_ID=$old_image_id
  export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID AGENT_CANON_PREVIOUS_IMAGE_ID
  if [[ -n "$old_image_id" ]] &&
     "$AGENT_CANON_DOCKER_CMD" container inspect "$old_container" >/dev/null 2>&1; then
    if ! "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$old_container" >/dev/null; then
      _agent_canon_json_error replacement_stop_failed "old resident could not be stopped"
      return 2
    fi
    if ! "$AGENT_CANON_DOCKER_CMD" rm "$old_container" >/dev/null; then
      _agent_canon_json_error replacement_remove_failed "old resident could not be removed"
      return 2
    fi
  fi
  if ! candidate=$(_agent_canon_ensure_container); then
    if "$AGENT_CANON_DOCKER_CMD" container inspect "$(_agent_canon_container_name)" >/dev/null 2>&1; then
      if ! "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$(_agent_canon_container_name)" >/dev/null 2>&1; then
        _agent_canon_json_error rollback_failed "candidate container stop failed after health failure"
        return 2
      fi
      if ! "$AGENT_CANON_DOCKER_CMD" rm "$(_agent_canon_container_name)" >/dev/null 2>&1; then
        _agent_canon_json_error rollback_failed "candidate container removal failed after health failure"
        return 2
      fi
    fi
    if [[ -n "${candidate_image_id:-}" && "$candidate_image_id" != "$old_image_id" ]]; then
      if ! "$AGENT_CANON_DOCKER_CMD" image rm "$candidate_image_id" >/dev/null 2>&1; then
        _agent_canon_json_error rollback_failed "candidate image removal failed after health failure"
        return 2
      fi
    fi
    if [[ -n "$old_image_id" ]]; then
      AGENT_CANON_IMAGE_REF=$old_image_id
      export AGENT_CANON_IMAGE_REF
      if ! restored=$(_agent_canon_ensure_container); then
        _agent_canon_json_error rollback_failed "previous resident could not be restarted"
        return 2
      fi
      if ! _agent_canon_run_controller "$restored" start >/dev/null; then
        _agent_canon_json_error rollback_failed "previous state could not be restored"
        return 2
      fi
    fi
    _agent_canon_json_error candidate_unhealthy "candidate resident container failed health readback"
    return 2
  fi
  rc=0
  if _agent_canon_run_controller "$candidate" update; then
    :
  else
    rc=$?
  fi
  if ((rc == 0)) && [[ "${AGENT_CANON_SUPPRESS_GLOBAL_LINKS:-0}" != 1 ]]; then
    if _agent_canon_install_global_links; then
      :
    else
      rc=$?
    fi
  fi
  if ((rc == 0)); then
    if _agent_canon_record_active_container "$candidate"; then
      :
    else
      rc=$?
    fi
  fi
  if ((rc != 0)) && [[ -n "$old_image_id" ]]; then
    if ! _agent_canon_restore_candidate_failure "$candidate" "$old_image_id" "$candidate_image_id"; then
      _agent_canon_json_error rollback_failed "candidate failure recovery was incomplete"
      return 2
    fi
  fi
  unset AGENT_CANON_PREVIOUS_IMAGE_ID AGENT_CANON_PREVIOUS_IMAGE_REF
  return "$rc"
}

_agent_canon_replace_resident() {
  local candidate_image_ref=$1 candidate_image_id=$2
  local lock_path="$AGENT_CANON_RUNTIME_ROOT/host-state/replacement.lock"
  local lock_fd rc unlock_rc
  if [[ -z "$candidate_image_ref" || -z "$candidate_image_id" ]]; then
    _agent_canon_json_error replacement_identity_missing "candidate resident identity is incomplete"
    return 2
  fi
  if [[ -L "$lock_path" ]]; then
    _agent_canon_json_error replacement_lock_invalid "resident replacement lock is a symlink"
    return 2
  fi
  if ! command -v flock >/dev/null 2>&1; then
    _agent_canon_json_error replacement_lock_unavailable "flock is required for resident replacement"
    return 2
  fi
  if ! exec {lock_fd}>"$lock_path"; then
    _agent_canon_json_error replacement_lock_unavailable "resident replacement lock could not be opened"
    return 2
  fi
  if ! flock -x "$lock_fd"; then
    exec {lock_fd}>&-
    _agent_canon_json_error replacement_lock_unavailable "resident replacement lock could not be acquired"
    return 2
  fi
  # Keep errexit active inside the transaction.  Calling the function as an
  # if-condition would disable errexit for every command in that function.
  set +e
  (
    set -e
    _agent_canon_replace_resident_locked "$candidate_image_ref" "$candidate_image_id"
  )
  rc=$?
  set -e
  unlock_rc=0
  flock -u "$lock_fd" || unlock_rc=$?
  exec {lock_fd}>&-
  if ((rc == 0 && unlock_rc != 0)); then
    _agent_canon_json_error replacement_lock_release_failed "resident replacement lock could not be released"
    return 2
  fi
  return "$rc"
}

_agent_canon_private_feedback_identity() {
  local container=$1 remote=$2 mode=${3:-source} response normalized branch
  local -a identity_args=(source-identity --mode "$mode" --remote "$remote")
  [[ -n "$container" && -n "$remote" ]] ||
    _agent_canon_json_error source_repository_identity_unavailable "resident identity operation requires a container and source remote"
  [[ "$mode" == source || "$mode" == remote ]] ||
    _agent_canon_json_error source_repository_identity_unavailable "identity mode is invalid"
  if [[ "$mode" == source && -n "${AGENT_CANON_SOURCE_REPOSITORY_ID:-}" ]]; then
    identity_args+=(--repository-id "$AGENT_CANON_SOURCE_REPOSITORY_ID")
  fi
  response=$(_agent_canon_run_controller "$container" "${identity_args[@]}") ||
    _agent_canon_json_error source_repository_identity_unavailable "resident identity operation failed"
  normalized=$(printf '%s\n' "$response" | sed -n 's/.*"normalized_remote":"\([^"]*\)".*/\1/p' | tail -n 1)
  branch=$(printf '%s\n' "$response" | sed -n 's/.*"stable_branch":"\([^"]*\)".*/\1/p' | tail -n 1)
  [[ -n "$normalized" && "$normalized" != *$'\t'* && "$normalized" != *$'\n'* ]] ||
    _agent_canon_json_error source_repository_identity_unavailable "resident identity operation returned an invalid stable branch"
  if [[ "$mode" == source ]]; then
    [[ "$branch" =~ ^logs/[a-z0-9][a-z0-9.-]{0,127}$ ]] ||
      _agent_canon_json_error source_repository_identity_unavailable "resident identity operation returned an invalid stable branch"
    printf '%s\t%s\n' "$normalized" "$branch"
  else
    printf '%s\n' "$normalized"
  fi
}

_agent_canon_private_feedback_raw_pending() {
  local spool=$1 raw="$1/raw"
  [[ -d "$raw" && ! -L "$raw" ]] || return 1
  find "$raw" -type f -print -quit | grep -q .
}

_agent_canon_private_feedback_cleanup_clone() {
  local log_root=$1 original_head=$2
  local -a touched=("${@:3}")
  if [[ -n "$original_head" && -d "$log_root/.git" ]]; then
    git -C "$log_root" reset --hard "$original_head" >/dev/null 2>&1 || true
    if ((${#touched[@]})); then
      git -C "$log_root" clean -fd -- "${touched[@]}" >/dev/null 2>&1 || true
    fi
  fi
}

_agent_canon_private_feedback_sync() {
  # The request is written by the resident into the one writable exchange
  # mount.  Only this host-side shell adapter may open the private log
  # checkout or use Git credentials/network access.
  local container=${1:-}
  local spool="$AGENT_CANON_STATE_ROOT/spool/private-feedback"
  local request="$spool/sync-request.json"
  [[ -f "$request" && ! -L "$request" ]] || return 0
  local request_body
  request_body=$(<"$request")
  request_body=${request_body%$'\n'}
  if ! printf '%s\n' "$request_body" | grep -Eq '^\{"execution_plane":"agentcanon_tool_container","operation":"sync","requested_at":"[^"]+","schema":"agent-canon\.private-feedback-sync-request\.v1","source_commit":"([0-9a-f]{40,64}|unknown)"\}$'; then
    _agent_canon_json_error private_feedback_sync_request_invalid "private feedback sync request is invalid"
  fi

  local log_root="$AGENT_CANON_PRIVATE_LOG_ROOT"
  local remote=${AGENT_CANON_LOG_REMOTE:-git@github.com:iwashita-nozomu/agent-canon-log.git}
  local source_remote=${AGENT_CANON_SOURCE_REPOSITORY_REMOTE:-}
  local source_remote_name=${AGENT_CANON_SOURCE_REPOSITORY_REMOTE_NAME:-origin}
  local branch configured current expected remote_head remote_tree
  local source_identity remote_normalized configured_normalized
  local -a copied=()
  local -a touched=()
  local source relative target
  local -a pending_files=() raw_files=()

  [[ -n "$container" ]] ||
    _agent_canon_json_error source_repository_identity_unavailable "resident identity operation requires a container"
  if [[ -z "$source_remote" ]]; then
    if ! source_remote=$(git -C "$AGENT_CANON_REPOSITORY_ROOT" remote get-url "$source_remote_name" 2>/dev/null); then
      _agent_canon_json_error source_repository_identity_unavailable "source repository remote is unavailable"
    fi
  fi

  if [[ -L "$log_root" || ( -e "$log_root" && ! -d "$log_root" ) ]]; then
    _agent_canon_json_error private_log_invalid "private log checkout path is not a regular directory"
  fi
  source_identity=$(_agent_canon_private_feedback_identity "$container" "$source_remote" source)
  if [[ -d "$log_root/.git" && ! -L "$log_root/.git" ]]; then
    if ! configured=$(git -C "$log_root" config --get remote.origin.url 2>/dev/null); then
      _agent_canon_json_error private_log_invalid "private log checkout has no origin remote"
    fi
  else
    configured=$remote
  fi
  remote_normalized=$(_agent_canon_private_feedback_identity "$container" "$remote" remote)
  configured_normalized=$(_agent_canon_private_feedback_identity "$container" "$configured" remote)
  [[ "$remote_normalized" == "$configured_normalized" ]] ||
    _agent_canon_json_error private_log_remote_mismatch "private log origin differs from the configured archive repository"
  if [[ ! -e "$log_root" ]]; then
    mkdir -p "$(dirname -- "$log_root")"
    if ! git clone --no-tags "$remote" "$log_root" >/dev/null 2>&1; then
      _agent_canon_json_error private_feedback_sync_failed "private log clone failed"
    fi
  elif [[ ! -d "$log_root/.git" ]]; then
    if [[ -n "$(find "$log_root" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
      _agent_canon_json_error private_log_invalid "private log path is not an empty checkout directory"
    fi
    rmdir -- "$log_root"
    if ! git clone --no-tags "$remote" "$log_root" >/dev/null 2>&1; then
      _agent_canon_json_error private_feedback_sync_failed "private log clone failed"
    fi
  fi
  chmod 700 "$log_root"
  if [[ -n "$(git -C "$log_root" status --porcelain=v1 --untracked-files=all)" ]]; then
    _agent_canon_json_error private_log_dirty "private log checkout has retained local changes"
  fi
  branch=${source_identity#*$'\t'}
  current=$(git -C "$log_root" branch --show-current 2>/dev/null || true)
  if ! git -C "$log_root" fetch --no-tags origin "$branch" >/dev/null 2>&1; then
    :
  fi
  if [[ "$current" != "$branch" ]]; then
    if git -C "$log_root" rev-parse --verify "origin/$branch" >/dev/null 2>&1; then
      git -C "$log_root" switch --track -c "$branch" "origin/$branch" >/dev/null 2>&1 ||
        _agent_canon_json_error private_log_branch_invalid "private log stable branch could not be selected"
    elif git -C "$log_root" rev-parse --verify origin/main >/dev/null 2>&1; then
      git -C "$log_root" switch -c "$branch" origin/main >/dev/null 2>&1 ||
        _agent_canon_json_error private_log_branch_invalid "private log stable branch could not be created"
    else
      git -C "$log_root" switch -c "$branch" >/dev/null 2>&1 ||
        _agent_canon_json_error private_log_branch_invalid "private log stable branch could not be created"
    fi
  fi
  current=$(git -C "$log_root" branch --show-current 2>/dev/null || true)
  [[ "$current" == "$branch" ]] ||
    _agent_canon_json_error private_log_branch_invalid "private log checkout is not on the source-qualified stable branch"
  local original_head
  original_head=$(git -C "$log_root" rev-parse --verify HEAD 2>/dev/null || true)
  expected=$(git -C "$log_root" rev-parse --verify "origin/$branch" 2>/dev/null || true)
  if [[ -n "$(git -C "$log_root" status --porcelain=v1 --untracked-files=all)" ]]; then
    _agent_canon_json_error private_log_dirty "private log checkout changed after stable branch fetch"
  fi
  if [[ -n "$expected" ]] && ! git -C "$log_root" merge --ff-only "origin/$branch" >/dev/null 2>&1; then
    _agent_canon_json_error private_feedback_sync_conflict "private log stable branch diverged from its remote"
  fi
  current=$(git -C "$log_root" rev-parse --verify HEAD 2>/dev/null || true)

  if _agent_canon_private_feedback_raw_pending "$spool"; then
    local annex_info trusted uuid_count
    if ! git -C "$log_root" annex version >/dev/null 2>&1 ||
       ! annex_info=$(git -C "$log_root" annex info --json 2>/dev/null); then
      _agent_canon_json_error private_feedback_annex_required "raw feedback requires a git-annex special remote"
    fi
    trusted=${annex_info#*\"trusted repositories\":}
    trusted=${trusted#\[}
    trusted=${trusted%%\]*}
    uuid_count=$(printf '%s' "$trusted" | grep -o '"uuid"' | wc -l | tr -d ' ')
    ((uuid_count > 1)) ||
      _agent_canon_json_error private_feedback_annex_required "raw feedback requires a git-annex special remote"
  fi

  mapfile -d '' pending_files < <(find "$spool" -type f ! -path "$spool/raw/*" ! -name sync-request.json -print0)
  for source in "${pending_files[@]}"; do
    relative=${source#"$spool"/}
    target="$log_root/$relative"
    [[ "$relative" != /* && "$relative" != *$'\t'* && "$relative" != *$'\n'* && "$relative" != *"../"* ]] || {
      _agent_canon_private_feedback_cleanup_clone "$log_root" "$original_head" "${touched[@]}"
      _agent_canon_json_error private_feedback_path_invalid "private feedback path is invalid"
    }
    mkdir -p "$(dirname -- "$target")"
    if [[ -e "$target" || -L "$target" ]]; then
      if [[ -L "$target" ]] || ! cmp -s -- "$source" "$target"; then
        _agent_canon_private_feedback_cleanup_clone "$log_root" "$original_head" "${touched[@]}"
        _agent_canon_json_error private_feedback_content_conflict "private log target differs from the pending spool"
      fi
    else
      cp -- "$source" "$target" || {
        _agent_canon_private_feedback_cleanup_clone "$log_root" "$original_head" "${touched[@]}"
        _agent_canon_json_error private_feedback_copy_failed "private feedback could not be copied"
      }
    fi
    copied+=("$relative")
    touched+=("$relative")
  done
  if _agent_canon_private_feedback_raw_pending "$spool"; then
    while IFS= read -r -d '' source; do
      relative=${source#"$spool"/}
      target="$log_root/$relative"
      mkdir -p "$(dirname -- "$target")"
      if [[ -e "$target" || -L "$target" ]]; then
        if [[ ! -L "$target" ]] && ! cmp -s -- "$source" "$target"; then
          _agent_canon_private_feedback_cleanup_clone "$log_root" "$original_head" "${touched[@]}"
          _agent_canon_json_error private_feedback_content_conflict "private raw target differs from the pending spool"
        fi
      else
        cp -- "$source" "$target" || {
          _agent_canon_private_feedback_cleanup_clone "$log_root" "$original_head" "${touched[@]}"
          _agent_canon_json_error private_feedback_copy_failed "private raw feedback could not be copied"
        }
      fi
      raw_files+=("$relative")
      copied+=("$relative")
      touched+=("$relative")
    done < <(find "$spool/raw" -type f -print0)
    if ! git -C "$log_root" annex add -- "${raw_files[@]}" >/dev/null 2>&1 ||
       ! git -C "$log_root" annex sync --no-content >/dev/null 2>&1; then
      _agent_canon_private_feedback_cleanup_clone "$log_root" "$original_head" "${touched[@]}"
      _agent_canon_json_error private_feedback_annex_failed "private raw feedback could not be staged"
    fi
  fi
  if ((${#copied[@]})); then
    if ((${#pending_files[@]})); then
      git -C "$log_root" add -- "${copied[@]}" >/dev/null 2>&1 || {
        _agent_canon_private_feedback_cleanup_clone "$log_root" "$original_head" "${touched[@]}"
        _agent_canon_json_error private_feedback_stage_failed "private feedback could not be staged"
      }
    fi
    if ! git -C "$log_root" diff --cached --quiet; then
      git -C "$log_root" -c user.name='AgentCanon Log Archive' \
        -c user.email='agent-canon-log@example.invalid' \
        commit -m 'Append private feedback and knowledge' >/dev/null 2>&1 || {
          _agent_canon_private_feedback_cleanup_clone "$log_root" "$original_head" "${touched[@]}"
          _agent_canon_json_error private_feedback_commit_failed "private feedback could not be committed"
        }
    fi
  fi
  current=$(git -C "$log_root" rev-parse --verify HEAD 2>/dev/null || true)
  if [[ "$current" != "$expected" ]]; then
    if ! git -C "$log_root" push origin "HEAD:refs/heads/$branch" >/dev/null 2>&1; then
      _agent_canon_private_feedback_cleanup_clone "$log_root" "$original_head" "${touched[@]}"
      _agent_canon_json_error private_feedback_sync_conflict "private log remote changed; pending spool retained"
    fi
  fi
  if ! git -C "$log_root" fetch --no-tags origin "$branch" >/dev/null 2>&1; then
    _agent_canon_json_error private_feedback_readback_failed "private log remote readback failed"
  fi
  remote_head=$(git -C "$log_root" rev-parse --verify "origin/$branch" 2>/dev/null || true)
  remote_tree=$(git -C "$log_root" rev-parse --verify "origin/$branch^{tree}" 2>/dev/null || true)
  [[ -n "$remote_head" && -n "$remote_tree" && ( ! ${#copied[@]} -gt 0 || "$remote_head" == "$current" ) ]] ||
    _agent_canon_json_error private_feedback_readback_failed "private log remote head readback differs"
  for relative in "${copied[@]}"; do
    rm -f -- "$spool/$relative"
  done
  while IFS= read -r -d '' source; do
    [[ "$source" == "$spool" ]] || rmdir -- "$source" 2>/dev/null || true
  done < <(find "$spool" -depth -type d -print0)
  rm -f -- "$request"
  printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"archive","code":"synced","execution_plane":"host_archive_adapter","clone":"%s","branch":"%s","commit":"%s","tree":"%s","copied":"%s"}\n' \
    "$log_root" "$branch" "$remote_head" "$remote_tree" "${#copied[@]}"
}

_agent_canon_archive_eval_sync() {
  local run_id=$1
  local spool="$AGENT_CANON_STATE_ROOT/spool/$run_id"
  local request="$spool/sync-request.tsv"
  [[ -f "$request" && ! -L "$request" ]] ||
    _agent_canon_json_error eval_sync_request_missing "eval sync request is unavailable"
  local key value schema= operation= plane= requested_run= target_digest= source_root=
  local schema_count=0 operation_count=0 plane_count=0 run_count=0 target_count=0 source_count=0
  while IFS=$'\t' read -r key value; do
    [[ -n "$key" && -n "$value" && "$value" != *$'\t'* && "$value" != *$'\n'* && "$value" != *$'\r'* ]] ||
      _agent_canon_json_error eval_sync_request_invalid "eval sync request contains an invalid row"
    case "$key" in
      schema) schema=$value; schema_count=$((schema_count + 1)) ;;
      operation) operation=$value; operation_count=$((operation_count + 1)) ;;
      execution-plane) plane=$value; plane_count=$((plane_count + 1)) ;;
      run-id) requested_run=$value; run_count=$((run_count + 1)) ;;
      target-digest) target_digest=$value; target_count=$((target_count + 1)) ;;
      source-root) source_root=$value; source_count=$((source_count + 1)) ;;
      *) _agent_canon_json_error eval_sync_request_invalid "eval sync request contains an unknown key: $key" ;;
    esac
  done < "$request"
  [[ "$schema_count" -eq 1 && "$schema" == agent-canon.eval-sync-request.v1 &&
     "$operation_count" -eq 1 && "$operation" == sync &&
     "$plane_count" -eq 1 && "$plane" == agentcanon_tool_container &&
     "$run_count" -eq 1 && "$requested_run" == "$run_id" &&
     "$target_count" -eq 1 && "$source_count" -eq 1 ]] ||
    _agent_canon_json_error eval_sync_request_invalid "eval sync request fields are invalid"
  [[ "$run_id" =~ ^[A-Za-z0-9_.-]{1,128}$ &&
     "$target_digest" =~ ^[A-Za-z0-9_.-]{0,128}$ && "$source_root" = /* ]] ||
    _agent_canon_json_error eval_sync_request_invalid "eval sync request values are invalid"

  # The resident sees /targets/<digest>. Resolve that opaque path only through
  # the host-owned mount manifest; never accept an arbitrary container path.
  local mounted_digest mounted_source mounted_destination mounted_mode resolved_source=
  while IFS=$'\t' read -r key mounted_digest mounted_source mounted_destination mounted_mode; do
    if [[ "$key" == target && "$mounted_digest" == "$target_digest" ]]; then
      [[ "$mounted_source" = /* && -d "$mounted_source" && ! -L "$mounted_source" &&
         "$mounted_destination" == "/targets/$target_digest" && "$mounted_mode" == read-only ]] ||
        _agent_canon_json_error eval_sync_request_invalid "selected target mount is invalid"
      resolved_source=$mounted_source
      break
    fi
  done < "$AGENT_CANON_STATE_ROOT/mounts.tsv"
  [[ -n "$resolved_source" && -d "$resolved_source" && ! -L "$resolved_source" ]] || {
    printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"eval_sync","code":"host_adapter_deferred","execution_plane":"host_archive_adapter"}\n'
    return 0
  }
  if ! command -v python3 >/dev/null 2>&1; then
    printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"eval_sync","code":"host_adapter_deferred","execution_plane":"host_archive_adapter"}\n'
    return 0
  fi
  local adapter_rc=0
  python3 "$AGENT_CANON_REPOSITORY_ROOT/tools/agent_tools/runtime_log_archive_git.py" \
    --source-root "$resolved_source" \
    --canon-root "$AGENT_CANON_REPOSITORY_ROOT" \
    --archive-root "$AGENT_CANON_PRIVATE_LOG_ROOT" \
    --runtime-root "$AGENT_CANON_STATE_ROOT" \
    --remote "${AGENT_CANON_LOG_REMOTE:-git@github.com:iwashita-nozomu/agent-canon-log.git}" \
    archive-eval --spool-root "$spool" --run-id "$run_id" || adapter_rc=$?
  if ((adapter_rc == 0)); then
    rm -f -- "$request"
  fi
  return "$adapter_rc"
}

_agent_canon_remove_global_links() {
  local home_root
  home_root=$(realpath -e -- "$HOME")
  [[ "$AGENT_CANON_CONTROL_ROOT" == "$home_root" ]] || return 0
  local manifest="$AGENT_CANON_STATE_ROOT/global-links.tsv"
  [[ -f "$manifest" && ! -L "$manifest" ]] || return 0
  local key target source mode digest resolved config_tmp
  local failures=()
  while IFS=$'\t' read -r key target source mode digest; do
    case "$key" in
      schema)
        [[ "$target" == agent-canon.global-links.v1 && -z "$source$mode$digest" ]] ||
          _agent_canon_json_error global_links_manifest_invalid "global link manifest schema is invalid" ;;
      link)
        [[ -L "$target" && -n "$source" && -z "$mode$digest" ]] || continue
        resolved=$(readlink -f -- "$target" 2>/dev/null || printf '')
        if [[ "$resolved" == "$source" ]]; then
          if ! rm -f -- "$target"; then failures+=("$target"); fi
        fi ;;
      config)
        [[ "$target" == "$home_root/.codex/config.toml" && -L "$target" && -f "$source" && -n "$mode" && "$digest" =~ ^[0-9a-f]{64}$ ]] || continue
        resolved=$(readlink -f -- "$target" 2>/dev/null || printf '')
        if [[ "$resolved" == "$source" ]]; then
          if ! config_tmp=$(mktemp "$home_root/.codex/.config.toml.restore.XXXXXX"); then
            failures+=("$target")
          elif ! cp --preserve=mode,timestamps -- "$source" "$config_tmp" ||
               ! chmod "$mode" "$config_tmp" ||
               ! mv -f -- "$config_tmp" "$target"; then
            rm -f -- "$config_tmp"
            failures+=("$target")
          fi
        fi ;;
      *) _agent_canon_json_error global_links_manifest_invalid "global link manifest contains an unknown key: $key" ;;
    esac
  done < "$manifest"
  if ((${#failures[@]})); then
    _agent_canon_json_error uninstall_links_failed "owned global link cleanup failed: ${failures[*]}"
  fi
}

_agent_canon_install_global_links() {
  local home_root
  home_root=$(realpath -e -- "$HOME")
  [[ "$AGENT_CANON_CONTROL_ROOT" == "$home_root" ]] || return 0
  local source_root="$AGENT_CANON_REPOSITORY_ROOT/.codex/personal"
  local skill_source_root="$AGENT_CANON_REPOSITORY_ROOT/agents/skills"
  local manifest="$AGENT_CANON_STATE_ROOT/global-links.tsv"
  local config_target="$home_root/.codex/config.toml"
  local config_source="$source_root/config.toml"
  local link source resolved mode digest
  local failures=()
  mkdir -p "$home_root/.agents/skills" "$home_root/.codex/agents" "$source_root"
  : > "$manifest"
  printf 'schema\tagent-canon.global-links.v1\n' >> "$manifest"
  if [[ -e "$config_target" || -L "$config_target" ]]; then
    resolved=$(readlink -f -- "$config_target" 2>/dev/null || printf '')
    if [[ -L "$config_target" && "$resolved" == "$config_source" ]]; then
      mode=$(stat -c '%a' -- "$config_source")
    elif [[ -L "$config_target" ]]; then
      failures+=("$config_target")
    elif [[ -f "$config_target" ]]; then
      if [[ -e "$config_source" && ! -f "$config_source" ]]; then
        failures+=("$config_target")
      else
        if ! cp --preserve=mode,timestamps -- "$config_target" "$config_source"; then
          failures+=("$config_target")
        fi
        mode=$(stat -c '%a' -- "$config_target")
        rm -f -- "$config_target"
        ln -s -- "$config_source" "$config_target"
      fi
    else
      failures+=("$config_target")
    fi
  else
    if [[ ! -f "$config_source" ]]; then
      printf '# AgentCanon personal Codex configuration.\n' > "$config_source"
      chmod 600 "$config_source"
    fi
    mode=$(stat -c '%a' -- "$config_source")
    ln -s -- "$config_source" "$config_target"
  fi
  if [[ -L "$config_target" && "$(readlink -f -- "$config_target")" == "$config_source" ]]; then
    digest=$(_agent_canon_sha256 "$config_source")
    printf 'config\t%s\t%s\t%s\t%s\n' "$config_target" "$config_source" "$mode" "$digest" >> "$manifest"
  fi
  for source in "$skill_source_root"/*; do
    [[ -d "$source" && ! -L "$source" ]] || continue
    link="$home_root/.agents/skills/${source##*/}"
    if [[ -L "$link" ]]; then
      resolved=$(readlink -f -- "$link" 2>/dev/null || printf '')
      [[ "$resolved" == "$(realpath -e -- "$source")" ]] || { failures+=("$link"); continue; }
    elif [[ -e "$link" ]]; then
      failures+=("$link")
      continue
    else
      ln -s -- "$source" "$link"
    fi
    printf 'link\t%s\t%s\n' "$link" "$source" >> "$manifest"
  done
  for source in "$AGENT_CANON_REPOSITORY_ROOT/.codex/agents"/*.toml; do
    [[ -f "$source" && ! -L "$source" ]] || continue
    link="$home_root/.codex/agents/${source##*/}"
    if [[ -L "$link" ]]; then
      resolved=$(readlink -f -- "$link" 2>/dev/null || printf '')
      [[ "$resolved" == "$(realpath -e -- "$source")" ]] || { failures+=("$link"); continue; }
    elif [[ -e "$link" ]]; then
      failures+=("$link")
      continue
    else
      ln -s -- "$source" "$link"
    fi
    printf 'link\t%s\t%s\n' "$link" "$source" >> "$manifest"
  done
  if ((${#failures[@]})); then
    _agent_canon_json_error global_link_collision "global link install preserved collisions: ${failures[*]}"
  fi
}

bootstrap_host_entrypoint() {
  local repository_root=$1
  shift
  local repository_request=$repository_root
  AGENT_CANON_REPOSITORY_ROOT=
  AGENT_CANON_CONTROL_ROOT=
  AGENT_CANON_CONTROL_ROOT_REQUEST=
  AGENT_CANON_RUNTIME_ROOT=
  AGENT_CANON_RUNTIME_REQUEST=
  AGENT_CANON_MANIFEST=
  AGENT_CANON_IMAGE_REF=
  AGENT_CANON_ACTIVE_IMAGE_ID=
  AGENT_CANON_EXPECTED_IMAGE_ID=
  local -a command_args=()
  local help_scope=
  while (($#)); do
    if [[ "$1" == -- ]]; then
      command_args+=("$@")
      break
    fi
    case "$1" in
      --repository-root) [[ $# -ge 2 ]] || _agent_canon_json_error argument_missing "$1"; repository_request=$2; shift 2 ;;
      --control-parent-root) [[ $# -ge 2 ]] || _agent_canon_json_error argument_missing "$1"; AGENT_CANON_CONTROL_ROOT_REQUEST=$2; shift 2 ;;
      --runtime-root) [[ $# -ge 2 ]] || _agent_canon_json_error argument_missing "$1"; AGENT_CANON_RUNTIME_REQUEST=$2; AGENT_CANON_RUNTIME_ROOT=$2; shift 2 ;;
      --manifest) [[ $# -ge 2 ]] || _agent_canon_json_error argument_missing "$1"; AGENT_CANON_MANIFEST=$2; shift 2 ;;
      --help|-h)
        if ((${#command_args[@]} == 0)); then
          help_scope=top
        elif [[ -z "$help_scope" ]]; then
          help_scope=operation
        fi
        command_args+=("$1")
        shift
        ;;
      *) command_args+=("$1"); shift ;;
    esac
  done
  if [[ -n "$help_scope" ]]; then
    if [[ "$help_scope" == top || ${#command_args[@]} -eq 0 ]]; then
      _agent_canon_usage
      return 0
    fi
    case "${command_args[0]}" in
      install|update|start|status|stop|rollback|uninstall|sync|scheduler|target|tool|template|codex|eval|task|gc|exec)
        _agent_canon_operation_usage "${command_args[0]}"
        return 0
        ;;
      *)
        _agent_canon_usage
        return 0
        ;;
    esac
  fi
  if ! AGENT_CANON_REPOSITORY_ROOT=$(CDPATH= cd -- "$repository_request" && pwd -P); then
    _agent_canon_json_error repository_root_invalid "repository root is not an existing directory"
  fi
  if [[ -n "${AGENT_CANON_CONTROL_ROOT_REQUEST:-}" ]]; then
    if ! AGENT_CANON_CONTROL_ROOT=$(CDPATH= cd -- "$AGENT_CANON_CONTROL_ROOT_REQUEST" && pwd -P); then
      _agent_canon_json_error control_root_invalid "control parent root is not an existing directory"
    fi
  fi
  [[ -n "$AGENT_CANON_CONTROL_ROOT" ]] || _agent_canon_json_error control_root_required "--control-parent-root is required"
  [[ -n "$AGENT_CANON_RUNTIME_ROOT" ]] || AGENT_CANON_RUNTIME_ROOT="$AGENT_CANON_REPOSITORY_ROOT/.runtime"
  _agent_canon_validate_roots
  AGENT_CANON_DOCKER_CMD=${AGENT_CANON_DOCKER:-docker}
  export AGENT_CANON_REPOSITORY_ROOT AGENT_CANON_CONTROL_ROOT AGENT_CANON_RUNTIME_ROOT
  [[ ${#command_args[@]} -gt 0 ]] || { _agent_canon_usage >&2; return 64; }
  if ! command -v "$AGENT_CANON_DOCKER_CMD" >/dev/null 2>&1 &&
     [[ ! -x "$AGENT_CANON_DOCKER_CMD" ]]; then
    _agent_canon_json_error runtime_unavailable "Docker executable is unavailable"
  fi
  _agent_canon_prepare_host_runtime
  local operation=${command_args[0]} image_ref=
  local index
  for index in "${!command_args[@]}"; do
    if [[ "${command_args[index]}" == --image-ref && $((index + 1)) -lt ${#command_args[@]} ]]; then
      image_ref=${command_args[index+1]}
    fi
  done
  case "$operation" in
    status)
      local container=$(_agent_canon_container_name)
      local running health
      if [[ -f "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" ]] ||
         "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
        _agent_canon_use_active_image "$container"
        if "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
          _agent_canon_validate_existing_container "$container"
        fi
      fi
      running=$("$AGENT_CANON_DOCKER_CMD" container inspect --format '{{.State.Running}}' "$container" 2>/dev/null || printf false)
      health=$("$AGENT_CANON_DOCKER_CMD" container inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$container" 2>/dev/null || printf absent)
      running=${running//$'\n'/}
      health=${health//$'\n'/}
      local source_sync_json
      if ! source_sync_json=$(_agent_canon_source_sync_json); then
        _agent_canon_json_error source_sync_state_invalid \
          "source-sync state is not a JSON object"
      fi
      printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"status","container":{"name":"%s","running":%s,"health":"%s"},"runtime_root":"%s","source_sync":%s}\n' \
        "$container" "$running" "$health" "$AGENT_CANON_RUNTIME_ROOT" "$source_sync_json"
      return 0
      ;;
    stop)
      local container=$(_agent_canon_container_name) current_ref
      if "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
        _agent_canon_use_active_image "$container"
        current_ref=$AGENT_CANON_IMAGE_REF
        _agent_canon_validate_existing_container "$container"
        if ! _agent_canon_run_controller "$container" stop >/dev/null; then
          _agent_canon_json_error stop_state_transition_failed "resident state could not enter stopped state"
        fi
        if ! "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$container" >/dev/null; then
          AGENT_CANON_CONTAINER_ID="$("$AGENT_CANON_DOCKER_CMD" container inspect --format '{{.Id}}' "$container")"
          _agent_canon_run_controller "$container" start >/dev/null ||
            _agent_canon_json_error stop_recovery_failed "failed to restore ready state after Docker stop failure"
          _agent_canon_json_error stop_failed "Docker could not stop the resident container"
        fi
        if ! "$AGENT_CANON_DOCKER_CMD" rm "$container" >/dev/null; then
          _agent_canon_json_error stop_remove_failed "Docker could not remove the stopped resident container"
        fi
      fi
      printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"stop","code":"stopped","container":"%s"}\n' "$container"
      return 0
      ;;
    uninstall)
      local container=$(_agent_canon_container_name)
      local image_ref image_owner state_root
      image_ref=
      if "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
        _agent_canon_use_active_image "$container"
        image_ref=$AGENT_CANON_IMAGE_REF
        if ! image_ref=$("$AGENT_CANON_DOCKER_CMD" container inspect \
          --format '{{.Config.Image}}' "$container" 2>/dev/null); then
          image_ref=
        fi
        if [[ -n "${AGENT_CANON_ACTIVE_IMAGE_ID:-}" ]]; then
          _agent_canon_validate_existing_container "$container"
        fi
        "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$container" >/dev/null
        "$AGENT_CANON_DOCKER_CMD" rm "$container" >/dev/null
      elif [[ -f "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" ]]; then
        _agent_canon_read_active_image
        image_ref=$AGENT_CANON_IMAGE_REF
      fi
      if ! image_owner=$("$AGENT_CANON_DOCKER_CMD" image inspect \
        --format '{{index .Config.Labels "io.agent-canon.control-root-digest"}}' \
        "$image_ref" 2>/dev/null); then
        image_owner=
      fi
      if [[ "$image_owner" == "$(_agent_canon_control_digest)" ]]; then
        if ! "$AGENT_CANON_DOCKER_CMD" image rm "$image_ref" >/dev/null; then
          _agent_canon_json_error uninstall_image_remove_failed "Docker could not remove the owned image"
        fi
      fi
      if _agent_canon_remove_global_links; then
        :
      else
        local link_cleanup_rc=$?
        return "$link_cleanup_rc"
      fi
      state_root="$AGENT_CANON_RUNTIME_ROOT/container-state"
      if [[ -d "$state_root" && ! -L "$state_root" ]]; then
        rm -rf -- "$state_root"
      fi
      if [[ -d "$AGENT_CANON_RUNTIME_ROOT/host-state" && ! -L "$AGENT_CANON_RUNTIME_ROOT/host-state" ]]; then
        rm -rf -- "$AGENT_CANON_RUNTIME_ROOT/host-state"
      fi
      printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"uninstall","code":"owned_resources_released","container":"%s"}\n' "$container"
      return 0
      ;;
    scheduler)
      _agent_canon_scheduler "${command_args[1]:-status}"
      return
      ;;
    install)
      AGENT_CANON_ALLOW_BUILD=1
      export AGENT_CANON_ALLOW_BUILD
      _agent_canon_image "$image_ref"
      local container install_image_id
      install_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
        --format '{{.Id}}' "$AGENT_CANON_IMAGE_REF")
      AGENT_CANON_EXPECTED_IMAGE_ID=$install_image_id
      export AGENT_CANON_EXPECTED_IMAGE_ID
      container=$(_agent_canon_ensure_container)
      local install_rc=0
      _agent_canon_run_controller "$container" install || install_rc=$?
      if ((install_rc != 0)); then
        return "$install_rc"
      fi
      _agent_canon_record_active_container "$container"
      if [[ "${AGENT_CANON_SUPPRESS_GLOBAL_LINKS:-0}" != 1 ]]; then
        _agent_canon_install_global_links
        return $?
      fi
      return 0
      ;;
    update)
      AGENT_CANON_ALLOW_BUILD=1
      AGENT_CANON_FORCE_BUILD=1
      export AGENT_CANON_ALLOW_BUILD AGENT_CANON_FORCE_BUILD
      _agent_canon_image "$image_ref"
      local candidate_image_ref candidate_image_id
      candidate_image_ref=$AGENT_CANON_IMAGE_REF
      if ! candidate_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
        --format '{{.Id}}' "$AGENT_CANON_IMAGE_REF"); then
        _agent_canon_json_error candidate_image_missing "candidate resident image could not be inspected"
        return 2
      fi
      _agent_canon_replace_resident "$candidate_image_ref" "$candidate_image_id"
      return $?
      ;;
    rollback)
      local rollback_image_id rollback_image_ref current_image_ref current_image_id rollback_container rollback_candidate rollback_rc=0
      local current_mounts_backup
      rollback_container=$(_agent_canon_container_name)
      _agent_canon_read_rollback_plan
      [[ -f "$AGENT_CANON_STATE_ROOT/mounts.tsv" && ! -L "$AGENT_CANON_STATE_ROOT/mounts.tsv" ]] ||
        _agent_canon_json_error rollback_target_manifest_missing "current target mount manifest is unavailable"
      # Keep the recovery manifest under the state mount.  The resident sees
      # container-state at /var/lib/agent-canon/runtime; files made in the
      # outer runtime directory are not available to its state-only restore.
      current_mounts_backup=$(mktemp "$AGENT_CANON_STATE_ROOT/.rollback-current-mounts.XXXXXX")
      cp -- "$AGENT_CANON_STATE_ROOT/mounts.tsv" "$current_mounts_backup"
      rollback_image_id=$AGENT_CANON_ROLLBACK_IMAGE_ID
      rollback_image_ref=$AGENT_CANON_ROLLBACK_IMAGE_REF
      _agent_canon_use_active_image "$rollback_container"
      current_image_ref=$AGENT_CANON_IMAGE_REF
      current_image_id=$AGENT_CANON_ACTIVE_IMAGE_ID
      if [[ -n "$current_image_id" ]]; then
        AGENT_CANON_IMAGE_REF=$current_image_ref
        export AGENT_CANON_IMAGE_REF
        # The resident that is about to be stopped must match the currently
        # active mount generation.  AGENT_CANON_ROLLBACK_MOUNTS_FILE points at
        # the previous plan after it was read, so pass the live manifest
        # explicitly and never validate the current container against the
        # rollback mounts.
        _agent_canon_validate_existing_container "$rollback_container" \
          "$AGENT_CANON_STATE_ROOT/mounts.tsv"
        if ! "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$rollback_container" >/dev/null; then
          _agent_canon_json_error rollback_failed "current resident could not be stopped"
        fi
        if ! "$AGENT_CANON_DOCKER_CMD" rm "$rollback_container" >/dev/null; then
          _agent_canon_json_error rollback_failed "current resident could not be removed"
        fi
      fi
      [[ -n "$current_image_id" ]] ||
        _agent_canon_json_error rollback_unavailable "current resident is missing"
      AGENT_CANON_IMAGE_REF=$rollback_image_id
      AGENT_CANON_EXPECTED_IMAGE_ID=$rollback_image_id
      export AGENT_CANON_IMAGE_REF
      export AGENT_CANON_EXPECTED_IMAGE_ID
      if ! rollback_candidate=$(_agent_canon_ensure_container); then
        _agent_canon_json_error rollback_failed "previous resident could not be started"
      fi
      # Apply the previous target set and generation pointers only after the
      # host has created the previous image.  This state-only transition is
      # atomic under the resident lock and is followed by complete mount
      # readback against the newly written live manifest.
      AGENT_CANON_CURRENT_IMAGE_ID=$current_image_id
      AGENT_CANON_CURRENT_IMAGE_REF=$current_image_ref
      AGENT_CANON_RESTORE_IMAGE_ID=$rollback_image_id
      AGENT_CANON_RESTORE_IMAGE_REF=$rollback_image_ref
      export AGENT_CANON_CURRENT_IMAGE_ID AGENT_CANON_CURRENT_IMAGE_REF AGENT_CANON_RESTORE_IMAGE_ID AGENT_CANON_RESTORE_IMAGE_REF
      if ! _agent_canon_run_controller "$rollback_candidate" rollback >/dev/null; then
        unset AGENT_CANON_CURRENT_IMAGE_ID AGENT_CANON_CURRENT_IMAGE_REF AGENT_CANON_RESTORE_IMAGE_ID AGENT_CANON_RESTORE_IMAGE_REF
        AGENT_CANON_ROLLBACK_MOUNTS_FILE="$AGENT_CANON_STATE_ROOT/mounts.tsv"
        AGENT_CANON_RESTORE_TARGETS_FILE="$AGENT_CANON_RUNTIME_DESTINATION/${current_mounts_backup##*/}"
        AGENT_CANON_CURRENT_IMAGE_ID=$current_image_id
        export AGENT_CANON_ROLLBACK_MOUNTS_FILE
        export AGENT_CANON_RESTORE_TARGETS_FILE AGENT_CANON_CURRENT_IMAGE_ID
        if ! _agent_canon_restore_candidate_failure "$rollback_candidate" "$current_image_id" "$rollback_image_id"; then
          _agent_canon_json_error rollback_failed "rollback state transition and current resident restoration failed"
        fi
        unset AGENT_CANON_ROLLBACK_MOUNTS_FILE AGENT_CANON_RESTORE_TARGETS_FILE
        rm -f -- "$current_mounts_backup"
        _agent_canon_json_error rollback_failed "rollback state transition failed after previous resident creation"
      fi
      unset AGENT_CANON_CURRENT_IMAGE_ID AGENT_CANON_CURRENT_IMAGE_REF AGENT_CANON_RESTORE_IMAGE_ID AGENT_CANON_RESTORE_IMAGE_REF
      AGENT_CANON_IMAGE_REF=$rollback_image_id
      export AGENT_CANON_IMAGE_REF
      if ! _agent_canon_validate_existing_container "$rollback_candidate" \
        "$AGENT_CANON_STATE_ROOT/mounts.tsv"; then
        AGENT_CANON_ROLLBACK_MOUNTS_FILE="$current_mounts_backup"
        AGENT_CANON_RESTORE_TARGETS_FILE="$AGENT_CANON_RUNTIME_DESTINATION/${current_mounts_backup##*/}"
        AGENT_CANON_CURRENT_IMAGE_ID=$current_image_id
        export AGENT_CANON_ROLLBACK_MOUNTS_FILE
        export AGENT_CANON_RESTORE_TARGETS_FILE AGENT_CANON_CURRENT_IMAGE_ID
        if ! _agent_canon_restore_candidate_failure "$rollback_candidate" "$current_image_id" "$rollback_image_id"; then
          _agent_canon_json_error rollback_failed "rollback mount readback and current resident restoration failed"
        fi
        unset AGENT_CANON_ROLLBACK_MOUNTS_FILE AGENT_CANON_RESTORE_TARGETS_FILE
        rm -f -- "$current_mounts_backup"
        _agent_canon_json_error rollback_failed "rollback resident mount readback failed"
      fi
      if ! _agent_canon_run_controller "$rollback_candidate" start >/dev/null; then
        rollback_rc=1
      fi
      if ((rollback_rc == 0)); then
        _agent_canon_record_active_container "$rollback_candidate" || rollback_rc=$?
      fi
      if ((rollback_rc != 0)); then
        if [[ -n "$current_image_id" ]]; then
          AGENT_CANON_IMAGE_REF=$current_image_id
          AGENT_CANON_ROLLBACK_MOUNTS_FILE="$current_mounts_backup"
          AGENT_CANON_RESTORE_TARGETS_FILE="$AGENT_CANON_RUNTIME_DESTINATION/${current_mounts_backup##*/}"
          AGENT_CANON_CURRENT_IMAGE_ID=$current_image_id
          export AGENT_CANON_IMAGE_REF
          export AGENT_CANON_ROLLBACK_MOUNTS_FILE AGENT_CANON_RESTORE_TARGETS_FILE AGENT_CANON_CURRENT_IMAGE_ID
          if ! _agent_canon_restore_candidate_failure "$rollback_candidate" "$current_image_id" "$rollback_image_id"; then
            _agent_canon_json_error rollback_failed "previous and current resident restoration failed"
          fi
        else
          _agent_canon_json_error rollback_failed "previous resident state restoration failed"
        fi
      fi
      # The resident rewrites rollback-plan.tsv for the opposite generation;
      # retaining it makes target-only rollback reversible without a second
      # rollback protocol.
      rm -f -- "$AGENT_CANON_STATE_ROOT/rollback-mounts.tsv"
      rm -f -- "$current_mounts_backup"
      unset AGENT_CANON_ROLLBACK_MOUNTS_FILE AGENT_CANON_RESTORE_TARGETS_FILE AGENT_CANON_CURRENT_IMAGE_ID AGENT_CANON_CURRENT_IMAGE_REF
      printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"rollback","code":"previous_generation_restored"}\n'
      return 0
      ;;
    target)
      local target_action=${command_args[1]:-} target_host_root target_digest target_container_root
      if [[ "$target_action" != add && "$target_action" != remove ]]; then
        _agent_canon_json_error unsupported_operation "unsupported target operation: $target_action"
      fi
      local target_arg_index=0
      while ((target_arg_index < ${#command_args[@]})); do
        if [[ "${command_args[target_arg_index]}" == --root && $((target_arg_index + 1)) -lt ${#command_args[@]} ]]; then
          target_host_root=${command_args[target_arg_index+1]}
          break
        fi
        target_arg_index=$((target_arg_index + 1))
      done
      target_host_root=$(realpath -e -- "$target_host_root")
      [[ -d "$target_host_root" && ! -L "$target_host_root" ]] ||
        _agent_canon_json_error target_root_invalid "target root must be a regular directory"
      target_digest=$(printf '%s' "$target_host_root" | sha256sum | awk '{print $1}')
      target_container_root="/targets/$target_digest"
      _agent_canon_use_active_image "$(_agent_canon_container_name)"
      local target_current_image target_current_image_id target_candidate target_rc=0
      target_current_image=$AGENT_CANON_IMAGE_REF
      target_current_image_id=$AGENT_CANON_ACTIVE_IMAGE_ID
      if [[ "$target_action" == add ]]; then
        if ! _agent_canon_target_digest "$target_host_root" >/dev/null; then
          AGENT_CANON_TARGET_PENDING_SOURCE=$target_host_root
          AGENT_CANON_TARGET_PENDING_DIGEST=$target_digest
          export AGENT_CANON_TARGET_PENDING_SOURCE AGENT_CANON_TARGET_PENDING_DIGEST
        fi
      fi
      if [[ -n "$target_current_image" ]]; then
        AGENT_CANON_IMAGE_REF=$target_current_image
        export AGENT_CANON_IMAGE_REF
        # Validate the resident against its active generation before adding a
        # pending target mount.  The pending mount belongs only to the new
        # container created after the old resident is removed.
        _agent_canon_validate_existing_container "$(_agent_canon_container_name)" \
          "$AGENT_CANON_STATE_ROOT/mounts.tsv" 0
        "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$(_agent_canon_container_name)" >/dev/null
        "$AGENT_CANON_DOCKER_CMD" rm "$(_agent_canon_container_name)" >/dev/null
      fi
      target_candidate=$(_agent_canon_ensure_container)
      command_args=("target" "$target_action" --root "$target_container_root" --mode read-only)
      AGENT_CANON_TARGET_HOST_ROOT=$target_host_root
      AGENT_CANON_TARGET_CONTAINER_ROOT=$target_container_root
      AGENT_CANON_TARGET_DIGEST=$target_digest
      export AGENT_CANON_TARGET_HOST_ROOT AGENT_CANON_TARGET_CONTAINER_ROOT AGENT_CANON_TARGET_DIGEST
      _agent_canon_run_controller "$target_candidate" "${command_args[@]}" || target_rc=$?
      if ((target_rc != 0)) && [[ -n "$target_current_image_id" ]]; then
        unset AGENT_CANON_TARGET_PENDING_SOURCE AGENT_CANON_TARGET_PENDING_DIGEST
        if ! _agent_canon_restore_candidate_failure "$target_candidate" "$target_current_image_id" "$target_current_image_id"; then
          _agent_canon_json_error rollback_failed "target mount replacement recovery was incomplete"
        fi
      fi
      if [[ "$target_action" == remove && $target_rc -eq 0 ]]; then
        "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$(_agent_canon_container_name)" >/dev/null
        "$AGENT_CANON_DOCKER_CMD" rm "$(_agent_canon_container_name)" >/dev/null
        target_candidate=$(_agent_canon_ensure_container)
        _agent_canon_run_controller "$target_candidate" start >/dev/null || target_rc=$?
      fi
      unset AGENT_CANON_TARGET_PENDING_SOURCE AGENT_CANON_TARGET_PENDING_DIGEST
      unset AGENT_CANON_TARGET_HOST_ROOT AGENT_CANON_TARGET_CONTAINER_ROOT
      unset AGENT_CANON_TARGET_DIGEST
      return "$target_rc"
      ;;
    codex)
      local codex_action=${command_args[1]:-} codex_project=${AGENT_CANON_PROJECT_ROOT:-}
      local codex_index=1
      while ((codex_index < ${#command_args[@]})); do
        if [[ "${command_args[codex_index]}" == --project-root &&
              $((codex_index + 1)) -lt ${#command_args[@]} ]]; then
          codex_project=${command_args[codex_index+1]}
          codex_index=$((codex_index + 1))
        fi
        codex_index=$((codex_index + 1))
      done
      [[ -n "${command_args[1]:-}" || -n "$codex_project" ]] ||
        _agent_canon_json_error argument_missing "codex requires prepare or launch"
      if [[ -z "$codex_action" && -n "$codex_project" ]]; then
        codex_action=launch
      fi
      [[ "$codex_action" == prepare || "$codex_action" == launch ]] ||
        _agent_canon_json_error unsupported_operation "unsupported codex operation: $codex_action"
      if [[ "$codex_action" == launch ]]; then
        [[ -n "$codex_project" ]] ||
          _agent_canon_json_error argument_missing "codex launch requires --project-root"
        if ! codex_project=$(realpath -e -- "$codex_project" 2>/dev/null); then
          _agent_canon_json_error codex_project_invalid "Codex project root does not exist"
        fi
        [[ -d "$codex_project" && ! -L "$codex_project" ]] ||
          _agent_canon_json_error codex_project_invalid "Codex project root must be a regular directory"
      fi
      _agent_canon_use_active_image "$(_agent_canon_container_name)"
      local codex_container codex_prepare_rc=0
      codex_container=$(_agent_canon_ensure_container)
      _agent_canon_run_controller "$codex_container" codex prepare || codex_prepare_rc=$?
      ((codex_prepare_rc == 0)) || return "$codex_prepare_rc"
      if [[ "$codex_action" == prepare ]]; then
        return 0
      fi
      local codex_executable=${AGENT_CANON_CODEX:-codex}
      if [[ "$codex_executable" != */* ]]; then
        codex_executable=$(command -v "$codex_executable" 2>/dev/null || printf '')
      fi
      [[ -x "$codex_executable" ]] ||
        _agent_canon_json_error codex_unavailable "Codex executable is unavailable"
      local codex_session_root="$AGENT_CANON_STATE_ROOT/codex-home/sessions"
      mkdir -p "$codex_session_root"
      chmod 700 "$codex_session_root"
      local codex_rc=0 feedback_rc=0
      CODEX_HOME="$AGENT_CANON_STATE_ROOT/codex-home" \
      AGENT_CANON_CONTROL_PARENT_ROOT="$AGENT_CANON_CONTROL_ROOT" \
      AGENT_CANON_RUNTIME_ROOT="$AGENT_CANON_RUNTIME_ROOT" \
      AGENT_CANON_SESSION_RUNTIME_ROOT="$AGENT_CANON_STATE_ROOT" \
      AGENT_CANON_CODEX_SESSION_ROOT="$codex_session_root" \
      AGENT_CANON_PROJECT_ROOT="$codex_project" \
        "$codex_executable" --project-root "$codex_project" || codex_rc=$?
      ((codex_rc == 0)) || return "$codex_rc"
      _agent_canon_private_feedback_sync "$codex_container" || feedback_rc=$?
      return "$feedback_rc"
      ;;
    eval)
      if [[ "${command_args[1]:-}" == sync ]]; then
        local eval_run_id=${command_args[3]:-} eval_index=2
        while ((eval_index < ${#command_args[@]})); do
          if [[ "${command_args[eval_index]}" == --run-id &&
                $((eval_index + 1)) -lt ${#command_args[@]} ]]; then
            eval_run_id=${command_args[eval_index+1]}
            eval_index=$((eval_index + 1))
          fi
          eval_index=$((eval_index + 1))
        done
        [[ "$eval_run_id" =~ ^[A-Za-z0-9_.-]{1,128}$ ]] ||
          _agent_canon_json_error argument_missing "eval sync requires a valid --run-id"
        _agent_canon_use_active_image "$(_agent_canon_container_name)"
        local eval_container eval_prepare_rc=0
        eval_container=$(_agent_canon_ensure_container)
        _agent_canon_run_controller "$eval_container" eval sync --run-id "$eval_run_id" || eval_prepare_rc=$?
        ((eval_prepare_rc == 0)) || return "$eval_prepare_rc"
        _agent_canon_archive_eval_sync "$eval_run_id"
        return $?
      fi
      ;;&
    install|update|start|stop|rollback|uninstall|target|tool|template|task|gc|eval|exec)
      if [[ "$operation" != install && "$operation" != update ]]; then
        _agent_canon_use_active_image "$(_agent_canon_container_name)"
      fi
      local container
      container=$(_agent_canon_ensure_container)
      if [[ "$operation" == exec ]] && _agent_canon_exec_is_structured_request; then
        _agent_canon_extract_exec_target_digest
        _agent_canon_validate_private_log_mount "$container"
      elif [[ "$operation" == tool || "$operation" == template || "$operation" == eval || "$operation" == exec ]]; then
        _agent_canon_rewrite_target_args "${command_args[@]}"
      fi
      local output_file error_file rc
      output_file=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.bootstrap.stdout.XXXXXX")
      error_file=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.bootstrap.stderr.XXXXXX")
      rc=0
      _agent_canon_container_exec "$container" \
        python3 /usr/local/share/agent-canon/runtime/tools/agent_tools/bootstrap_runtime.py \
        --container-control \
        --repository-root /usr/local/share/agent-canon/runtime \
        --control-parent-root /var/lib/agent-canon \
        --runtime-root /var/lib/agent-canon/runtime \
        "${command_args[@]}" >"$output_file" 2>"$error_file" || rc=$?
      cat "$output_file"
      cat "$error_file" >&2
      rm -f -- "$output_file" "$error_file"
      if ((rc == 0)) && [[ "$operation" == exec || "$operation" == tool ]]; then
        _agent_canon_private_feedback_sync "$container" || rc=$?
      fi
      return "$rc"
      ;;
    sync)
      _agent_canon_sync_operation
      return $?
      ;;
    *)
      _agent_canon_json_error unsupported_operation "unsupported bootstrap operation: $operation"
      ;;
  esac
}
