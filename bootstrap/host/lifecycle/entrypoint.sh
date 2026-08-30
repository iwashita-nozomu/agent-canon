#!/usr/bin/env bash
# @dependency-start
# contract agent-runtime
# responsibility Owns the host-only Docker/Git adapter for the shared AgentCanon container. AgentCanon Python is invoked only through docker exec.
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md shared host/container bootstrap contract
# downstream implementation ../../../tools/runtime/container/bootstrap_runtime.py container-side runtime implementation
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
AGENT_CANON_VOLUME_DESTINATION=/var/lib/agent-canon
AGENT_CANON_LEGACY_STATE_DESTINATION=/var/lib/agent-canon-legacy-state
AGENT_CANON_RUNTIME_DESTINATION=/var/lib/agent-canon/runtime
AGENT_CANON_EXCHANGE_DESTINATION=/var/lib/agent-canon/runtime/container-runtime
AGENT_CANON_SPOOL_DESTINATION=/var/lib/agent-canon/runtime/spool
AGENT_CANON_ARCHIVE_DESTINATION=/var/lib/agent-canon/runtime/archive
AGENT_CANON_CACHE_DESTINATION=/var/lib/agent-canon/runtime/cache
AGENT_CANON_CODEX_HOME_DESTINATION=/var/lib/agent-canon/runtime/codex-home
AGENT_CANON_PRIVATE_LOG_DESTINATION=/var/lib/agent-canon/private-log
AGENT_CANON_MOUNT_REGISTRY_DESTINATION=/var/lib/agent-canon/mount-registry.toml
AGENT_CANON_HOST_MOUNTS_DESTINATION=/var/lib/agent-canon/host-mounts.tsv
AGENT_CANON_SOURCE_SYNC_DESTINATION=/var/lib/agent-canon/source-sync.json
AGENT_CANON_HEALTH_ATTEMPTS=120
AGENT_CANON_PRIVATE_LOG_ROOT=
AGENT_CANON_TARGET_PRUNE_DIGESTS=
AGENT_CANON_STATE_VOLUME_NAME=
AGENT_CANON_STATE_VOLUME_CREATED_HERE=0
AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT=
AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT=
AGENT_CANON_CANDIDATE_CONTAINER_ID=
AGENT_CANON_CANDIDATE_CONTAINER_CREATED_HERE=0
AGENT_CANON_ACTIVATION_COMMIT_RECEIPT=
AGENT_CANON_PROJECTION_LAYOUT=

_agent_canon_caller_user() {
  local caller_uid caller_gid
  caller_uid=$(id -u)
  caller_gid=$(id -g)
  printf '%s:%s' "$caller_uid" "$caller_gid"
}

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
  [[ "$source_root" == /* && "$source_root" != *$'\n'* && "$source_root" != *$'\r'* &&
     "$source_root" != *$'\t'* ]] || return 64
  [[ "$source_root" != *'"'* && "$source_root" != *'\'* ]] || return 64
  [[ "$source_head" == unknown || "$source_head" =~ ^[0-9a-f]{40}$ ]] || return 64
  [[ "$source_tree" == unknown || "$source_tree" =~ ^[0-9a-f]{40}$ ]] || return 64
  [[ "$remote" =~ ^[A-Za-z0-9_.-]+$ ]] || return 64
  [[ "$branch" =~ ^[A-Za-z0-9._/-]+$ ]] || return 64
  [[ "$remote_url" == unknown ||
     ( -n "$remote_url" && "$remote_url" != *$'\n'* && "$remote_url" != *$'\r'* &&
       "$remote_url" != *$'\t'* &&
       "$remote_url" != *'"'* && "$remote_url" != *'\'* ) ]] || return 64
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
  [[ "$state" != *$'\n'* && "$state" != *$'\r'* ]] || return 1
  local record_re='^\{"schema":"agent-canon.source-sync.v1","status":"(success|failed)","code":"([a-z][a-z0-9_]*)","source_root":"([^"]*)","source_head":"(unknown|[0-9a-f]{40})","source_tree":"(unknown|[0-9a-f]{40})","remote":"([A-Za-z0-9_.-]+)","remote_url":"([^"]+)","branch":"([A-Za-z0-9._/-]+)","updated_at":"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z)"(,"failure":"([a-z][a-z0-9_]*)")?\}$'
  [[ "$state" =~ $record_re ]] || return 1
  local status=${BASH_REMATCH[1]} source_root=${BASH_REMATCH[3]}
  local source_head=${BASH_REMATCH[4]} source_tree=${BASH_REMATCH[5]}
  local remote=${BASH_REMATCH[6]} remote_url=${BASH_REMATCH[7]}
  local branch=${BASH_REMATCH[8]} updated_at=${BASH_REMATCH[9]}
  local failure=${BASH_REMATCH[11]:-}
  [[ "$source_root" == /* ]] || return 1
  [[ "$source_root" != *'\'* && "$source_root" != *$'\t'* &&
     "$remote_url" != *'\'* && "$remote_url" != *$'\t'* ]] || return 1
  [[ "$status" == success && -z "$failure" ||
     "$status" == failed && -n "$failure" ]] || return 1
  printf '%s' "$state"
}

_agent_canon_ensure_source_sync_state() {
  local state_path="$AGENT_CANON_RUNTIME_ROOT/source-sync.json"
  if [[ -e "$state_path" || -L "$state_path" ]]; then
    [[ -f "$state_path" && ! -L "$state_path" ]] ||
      _agent_canon_json_error source_sync_state_invalid \
        "source-sync state must be a regular file"
    chmod 600 -- "$state_path" ||
      _agent_canon_json_error source_sync_state_invalid \
        "source-sync state permissions could not be restricted"
    return 0
  fi
  local source_head=${AGENT_CANON_SYNC_INITIAL_HEAD:-unknown}
  local source_tree=${AGENT_CANON_SYNC_INITIAL_TREE:-unknown}
  local source_remote=${AGENT_CANON_SYNC_INITIAL_REMOTE:-origin}
  local source_remote_url=${AGENT_CANON_SYNC_INITIAL_REMOTE_URL:-unknown}
  source_head=$(git -C "$AGENT_CANON_REPOSITORY_ROOT" rev-parse --verify HEAD 2>/dev/null) || :
  source_tree=$(git -C "$AGENT_CANON_REPOSITORY_ROOT" rev-parse --verify HEAD^{tree} 2>/dev/null) || :
  [[ "$source_head" =~ ^[0-9a-f]{40}$ ]] || source_head=unknown
  [[ "$source_tree" =~ ^[0-9a-f]{40}$ ]] || source_tree=unknown
  _agent_canon_source_sync_write success not_run "$AGENT_CANON_REPOSITORY_ROOT" \
    "$source_head" "$source_tree" "$source_remote" "$source_remote_url" \
    "${AGENT_CANON_SYNC_INITIAL_BRANCH:-main}" \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" ||
    _agent_canon_json_error source_sync_state_write_failed \
      "initial source-sync state could not be atomically published"
}

_agent_canon_sync_request_metadata() {
  local install_request=${AGENT_CANON_REPOSITORY_ROOT:-} remote=origin branch=main
  local sync_index=1 token install_root git_root remote_url source_head source_tree
  while ((sync_index < ${#command_args[@]})); do
    token=${command_args[sync_index]}
    case "$token" in
      sync) ;;
      --install-root=*)
        install_request=${token#--install-root=}
        ;;
      --install-root)
        ((sync_index += 1))
        if ((sync_index >= ${#command_args[@]})); then
          _agent_canon_json_error argument_missing "--install-root requires a value"
          return 2
        fi
        install_request=${command_args[sync_index]}
        ;;
      --remote=*) remote=${token#--remote=} ;;
      --remote)
        ((sync_index += 1))
        if ((sync_index >= ${#command_args[@]})); then
          _agent_canon_json_error argument_missing "--remote requires a value"
          return 2
        fi
        remote=${command_args[sync_index]}
        ;;
      --branch=*) branch=${token#--branch=} ;;
      --branch)
        ((sync_index += 1))
        if ((sync_index >= ${#command_args[@]})); then
          _agent_canon_json_error argument_missing "--branch requires a value"
          return 2
        fi
        branch=${command_args[sync_index]}
        ;;
      *)
        _agent_canon_json_error argument_invalid "unsupported source-sync argument"
        return 2
        ;;
    esac
    ((sync_index += 1))
  done
  [[ "$remote" =~ ^[A-Za-z0-9_.-]+$ ]] || {
    _agent_canon_json_error argument_invalid "source-sync remote is invalid"
    return 2
  }
  [[ "$branch" =~ ^[A-Za-z0-9._/-]+$ ]] || {
    _agent_canon_json_error argument_invalid "source-sync branch is invalid"
    return 2
  }
  if ! install_root=$(realpath -e -- "$install_request" 2>/dev/null); then
    _agent_canon_json_error install_root_invalid "source-sync install root is not a directory"
    return 2
  fi
  [[ -d "$install_root" && ! -L "$install_root" ]] || {
    _agent_canon_json_error install_root_invalid "source-sync install root must be a regular directory"
    return 2
  }
  if ! git_root=$(git -C "$install_root" rev-parse --show-toplevel 2>/dev/null); then
    _agent_canon_json_error install_root_not_git "source-sync install root is not a Git checkout"
    return 2
  fi
  if ! git_root=$(realpath -e -- "$git_root" 2>/dev/null); then
    _agent_canon_json_error install_root_not_git "source-sync Git root is unavailable"
    return 2
  fi
  if ! remote_url=$(git -C "$git_root" remote get-url "$remote" 2>/dev/null); then
    _agent_canon_json_error source_remote_unavailable "source-sync remote URL is unavailable"
    return 2
  fi
  [[ -n "$remote_url" && "$remote_url" != *$'\n'* && "$remote_url" != *$'\r'* ]] || {
    _agent_canon_json_error source_remote_unavailable "source-sync remote URL is invalid"
    return 2
  }
  if ! source_head=$(git -C "$git_root" rev-parse --verify HEAD 2>/dev/null) ||
     ! source_tree=$(git -C "$git_root" rev-parse --verify HEAD^{tree} 2>/dev/null) ||
     [[ ! "$source_head" =~ ^[0-9a-f]{40}$ || ! "$source_tree" =~ ^[0-9a-f]{40}$ ]]; then
    _agent_canon_json_error source_sync_git_failed "source-sync Git identity is incomplete"
    return 2
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$git_root" "$remote" "$branch" "$remote_url" "$source_head" "$source_tree"
}

_agent_canon_source_sync_failure() {
  local code=$1 detail=$2 write_rc=0
  if [[ "${AGENT_CANON_SYNC_SKIP_STATE:-0}" != 1 ]]; then
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
  fi
  _agent_canon_json_error "$code" "$detail"
}

_agent_canon_install_source_admission() (
  # Install consumes the caller's checkout.  SourceSync refreshes the exact
  # remote-tracking ref and admits only an exact commit match; it never
  # changes the caller's branch, worktree, or generated runtime state.
  set +e
  AGENT_CANON_SYNC_SKIP_STATE=1
  local install_root=${1:-$AGENT_CANON_REPOSITORY_ROOT}
  local remote=origin branch=main
  local remote_url source_head source_tree remote_head
  AGENT_CANON_SYNC_SOURCE_ROOT=$install_root
  AGENT_CANON_SYNC_REMOTE=$remote
  AGENT_CANON_SYNC_BRANCH=$branch
  AGENT_CANON_SYNC_REMOTE_URL=unknown
  AGENT_CANON_SYNC_SOURCE_HEAD=unknown
  AGENT_CANON_SYNC_SOURCE_TREE=unknown

  if ! source_head=$(git -C "$install_root" rev-parse --verify HEAD 2>/dev/null); then
    _agent_canon_source_sync_failure source_sync_git_failed "source checkout HEAD is unavailable"
    exit 2
  fi
  if ! remote_url=$(git -C "$install_root" remote get-url "$remote" 2>/dev/null); then
    _agent_canon_source_sync_failure source_remote_unavailable "source-sync remote URL is unavailable"
    exit 2
  fi
  AGENT_CANON_SYNC_REMOTE_URL=$remote_url
  if ! git -C "$install_root" fetch "$remote" "+refs/heads/$branch:refs/remotes/$remote/$branch"; then
    _agent_canon_source_sync_failure source_remote_unavailable "source-sync fetch failed"
    exit 2
  fi
  if ! remote_head=$(git -C "$install_root" rev-parse --verify "refs/remotes/$remote/$branch" 2>/dev/null); then
    _agent_canon_source_sync_failure source_remote_unavailable "fetched source branch is unavailable"
    exit 2
  fi
  [[ "$source_head" =~ ^[0-9a-f]{40}$ && "$remote_head" =~ ^[0-9a-f]{40}$ ]] || {
    AGENT_CANON_SYNC_SOURCE_HEAD=$source_head
    _agent_canon_source_sync_failure source_sync_git_failed "source commit identity is invalid"
    exit 2
  }
  [[ "$source_head" == "$remote_head" ]] || {
    AGENT_CANON_SYNC_SOURCE_HEAD=$source_head
    _agent_canon_source_sync_failure source_sync_commit_mismatch \
      "source HEAD does not match refs/remotes/origin/main"
    exit 2
  }
  # Tree identity is receipt telemetry only.  It is deliberately not part of
  # install admission, so an unavailable tree never blocks reconstruction.
  source_tree=$(git -C "$install_root" rev-parse --verify HEAD^{tree} 2>/dev/null) || source_tree=unknown
  AGENT_CANON_SYNC_SOURCE_HEAD=$source_head
  AGENT_CANON_SYNC_SOURCE_TREE=$source_tree
  printf 'up_to_date\t%s\t%s\t%s\n' "$source_head" "$source_tree" "$remote_url"
  exit 0
)

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
      --install-root=*) install_root=${command_args[sync_index]#--install-root=} ;;
      --install-root)
        ((sync_index += 1))
        if ((sync_index >= ${#command_args[@]})); then
          _agent_canon_source_sync_failure argument_missing "--install-root requires a value"
          exit 2
        fi
        install_root=${command_args[sync_index]}
        ;;
      --remote=*) remote=${command_args[sync_index]#--remote=} ;;
      --remote)
        ((sync_index += 1))
        if ((sync_index >= ${#command_args[@]})); then
          _agent_canon_source_sync_failure argument_missing "--remote requires a value"
          exit 2
        fi
        remote=${command_args[sync_index]}
        ;;
      --branch=*) branch=${command_args[sync_index]#--branch=} ;;
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
  if ! git -C "$install_root" fetch "$remote" "+refs/heads/$branch:refs/remotes/$remote/$branch"; then
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

_agent_canon_prune_stale_target_manifest() {
  local manifest=${1:-$AGENT_CANON_STATE_ROOT/mounts.tsv}
  local temporary raw kind digest source destination mode
  local previous_pruned=${AGENT_CANON_TARGET_PRUNE_DIGESTS:-}
  local -a stale=()
  AGENT_CANON_TARGET_PRUNE_DIGESTS=
  [[ -f "$manifest" && ! -L "$manifest" ]] || return 0
  if ! temporary=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.mounts.tsv.XXXXXX"); then
    _agent_canon_json_error mount_manifest_write_failed \
      "target mount manifest could not be staged for stale-entry cleanup"
    return 2
  fi
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    IFS=$'\t' read -r kind digest source destination mode <<<"$raw"
    if [[ "$kind" == target &&
          "$digest" =~ ^[A-Za-z0-9_.-]{1,128}$ &&
          "$source" = /* &&
          "$destination" == "/targets/$digest" &&
          "$mode" == read-only &&
          ( ! -d "$source" || -L "$source" ) ]]; then
      stale+=("$digest")
      continue
    fi
    printf '%s\n' "$raw" >> "$temporary"
  done < "$manifest"
  if ((${#stale[@]} == 0)); then
    rm -f -- "$temporary"
    AGENT_CANON_TARGET_PRUNE_DIGESTS=$previous_pruned
    return 0
  fi
  if ! mv -f -- "$temporary" "$manifest"; then
    rm -f -- "$temporary"
    _agent_canon_json_error mount_manifest_write_failed \
      "stale target entries could not be removed from the mount manifest"
    return 2
  fi
  AGENT_CANON_TARGET_PRUNE_DIGESTS=$(IFS=,; printf '%s' "${stale[*]}")
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
  local state_volume="${AGENT_CANON_STATE_VOLUME_NAME:-agent-canon-runtime-$(_agent_canon_control_digest)}"
  while IFS=$'\t' read -r source destination writable; do
    if [[ "$source" == "volume:$state_volume" &&
          "$destination" == "$AGENT_CANON_VOLUME_DESTINATION" &&
          "$writable" == true ]]; then
      found=$((found + 1))
    fi
  done < <("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{range .Mounts}}{{if eq .Type "volume"}}{{printf "volume:%s\t%s\t%t\n" .Name .Destination .RW}}{{else}}{{printf "%s\t%s\t%t\n" .Source .Destination .RW}}{{end}}{{end}}' \
    "$container")
  if ((found == 1)); then
    return 0
  fi
  _agent_canon_json_error mount_manifest_invalid "resident volume mount is absent"
}

_agent_canon_prepare_host_runtime() {
  AGENT_CANON_STATE_ROOT="$AGENT_CANON_RUNTIME_ROOT/container-state"
  AGENT_CANON_STATE_VOLUME_NAME="agent-canon-runtime-$(_agent_canon_control_digest)"
  AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT="$AGENT_CANON_RUNTIME_ROOT/host-state/state-volume-created.tsv"
  AGENT_CANON_ACTIVATION_COMMIT_RECEIPT="$AGENT_CANON_RUNTIME_ROOT/host-state/activation-committed.tsv"
  AGENT_CANON_INITIAL_MOUNTS_TOML_EXISTS=0
  AGENT_CANON_INITIAL_MOUNTS_TSV_EXISTS=0
  [[ -e "$AGENT_CANON_STATE_ROOT/mounts.toml" ]] && AGENT_CANON_INITIAL_MOUNTS_TOML_EXISTS=1
  [[ -e "$AGENT_CANON_STATE_ROOT/mounts.tsv" ]] && AGENT_CANON_INITIAL_MOUNTS_TSV_EXISTS=1
  export AGENT_CANON_STATE_ROOT
  export AGENT_CANON_STATE_VOLUME_NAME AGENT_CANON_INITIAL_MOUNTS_TOML_EXISTS \
    AGENT_CANON_INITIAL_MOUNTS_TSV_EXISTS
  AGENT_CANON_STATE_VOLUME_CREATED_HERE=0
  if _agent_canon_state_volume_creation_receipt_matches "$AGENT_CANON_STATE_VOLUME_NAME"; then
    AGENT_CANON_STATE_VOLUME_CREATED_HERE=1
  elif [[ -e "$AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT" &&
          ! -L "$AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT" ]]; then
    if ! rm -f -- "$AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT" ||
       [[ -e "$AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT" ||
          -L "$AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT" ]]; then
      _agent_canon_json_error rollback_failed \
        "stale state-volume creation receipt could not be released"
    fi
  fi
  AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT="$AGENT_CANON_RUNTIME_ROOT/host-state/candidate-container.tsv"
  export AGENT_CANON_STATE_VOLUME_CREATED_HERE AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT \
    AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT AGENT_CANON_ACTIVATION_COMMIT_RECEIPT
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

_agent_canon_drop_legacy_controller_state() {
  local path relative backup_root backup_path cleanup_rc
  local -a paths=(
    "$AGENT_CANON_STATE_ROOT/state.json"
    "$AGENT_CANON_STATE_ROOT/owner.json"
    "$AGENT_CANON_STATE_ROOT/receipts"
    "$AGENT_CANON_STATE_ROOT/generations"
    "$AGENT_CANON_STATE_ROOT/tasks"
  )
  # Validate the complete set and stage every existing member before the
  # first deletion.  The receipt directory is part of this rollback unit.
  for path in "${paths[@]}"; do
    [[ ! -L "$path" ]] ||
      _agent_canon_json_error controller_state_projection_invalid \
        "legacy controller state is a symlink: $path"
    if [[ -d "$path" ]]; then
      [[ -z "$(find "$path" -type l -print -quit)" ]] ||
        _agent_canon_json_error controller_state_projection_invalid \
          "legacy controller state contains a symlink: $path"
    fi
  done
  backup_root=$(mktemp -d "$AGENT_CANON_RUNTIME_ROOT/.legacy-controller-drop.XXXXXX") ||
    _agent_canon_json_error controller_state_projection_failed \
      "legacy controller state backup could not be created"
  for path in "${paths[@]}"; do
    [[ -e "$path" ]] || continue
    relative=${path#"$AGENT_CANON_STATE_ROOT"/}
    backup_path="$backup_root/$relative"
    mkdir -p -- "$(dirname -- "$backup_path")" || {
      rm -rf -- "$backup_root"
      _agent_canon_json_error controller_state_projection_failed \
        "legacy controller state backup directory could not be created"
    }
    if ! cp -a -- "$path" "$backup_path"; then
      rm -rf -- "$backup_root"
      _agent_canon_json_error controller_state_projection_failed \
        "legacy controller state backup could not be copied"
    fi
    if [[ -d "$path" ]]; then
      [[ -d "$backup_path" && ! -L "$backup_path" ]] || {
        rm -rf -- "$backup_root"
        _agent_canon_json_error controller_state_projection_failed \
          "legacy controller state backup readback was invalid"
      }
    else
      [[ -f "$backup_path" && ! -L "$backup_path" ]] || {
        rm -rf -- "$backup_root"
        _agent_canon_json_error controller_state_projection_failed \
          "legacy controller state backup readback was invalid"
      }
    fi
  done
  cleanup_legacy_controller_state() {
    cleanup_rc=${1:-$?}
    if ((cleanup_rc != 0)); then
      for path in "${paths[@]}"; do
        if [[ -d "$path" && ! -L "$path" ]]; then
          rm -rf -- "$path"
        elif [[ -e "$path" || -L "$path" ]]; then
          rm -f -- "$path"
        fi
      done
      for path in "${paths[@]}"; do
        relative=${path#"$AGENT_CANON_STATE_ROOT"/}
        backup_path="$backup_root/$relative"
        [[ -e "$backup_path" && ! -L "$backup_path" ]] || continue
        cp -a -- "$backup_path" "$path" || cleanup_rc=2
      done
    fi
    rm -rf -- "$backup_root"
    return "$cleanup_rc"
  }
  for path in \
    "$AGENT_CANON_STATE_ROOT/state.json" \
    "$AGENT_CANON_STATE_ROOT/owner.json" \
    "$AGENT_CANON_STATE_ROOT/receipts" \
    "$AGENT_CANON_STATE_ROOT/generations" \
    "$AGENT_CANON_STATE_ROOT/tasks"; do
    if [[ -d "$path" ]]; then
      rm -rf -- "$path" || { cleanup_legacy_controller_state 2; return 2; }
    elif [[ -e "$path" ]]; then
      rm -f -- "$path" || { cleanup_legacy_controller_state 2; return 2; }
    fi
    relative=${path#"$AGENT_CANON_STATE_ROOT"/}
    if [[ "${AGENT_CANON_TEST_DROP_LEGACY_FAIL_AFTER:-}" == "$relative" ]]; then
      cleanup_legacy_controller_state 2
      return 2
    fi
  done
  cleanup_legacy_controller_state 0
}

_agent_canon_path_digest() {
  local path=$1
  [[ -e "$path" && ! -L "$path" ]] || return 1
  if [[ -f "$path" ]]; then
    _agent_canon_sha256 "$path"
    return
  fi
  [[ -d "$path" ]] || return 1
  [[ -z "$(find "$path" -type l -print -quit)" ]] || return 1
  (cd "$path" && find . -type f -exec sha256sum {} + | LC_ALL=C sort | sha256sum | awk '{print $1}')
}

_agent_canon_validate_codex_home() {
  local path=$1 allowed link relative_link target expected invalid
  allowed="$AGENT_CANON_REPOSITORY_ROOT/.codex"
  [[ -d "$path" && ! -L "$path" && -d "$allowed" && ! -L "$allowed" ]] || return 1
  invalid=$(find "$path" -type l -print | while IFS= read -r link; do
    relative_link=${link#"$path"/}
    case "$relative_link" in
      config.toml|agents/*|hooks/*|skills/*) ;;
      *) printf 'invalid\n'; continue ;;
    esac
    case "$relative_link" in
      *//*|../*|*/../*|*/..|./*|*/./*|.) printf 'invalid\n'; continue ;;
      config.toml) expected="$allowed/config.toml" ;;
      agents/*|hooks/*) expected="$allowed/$relative_link" ;;
      skills/*) expected="$allowed/personal/skills/${relative_link#skills/}" ;;
    esac
    target=$(readlink -f "$link" 2>/dev/null || true)
    [[ "$target" != *$'\n'* && "$target" != *$'\r'* && "$target" != *$'\t'* ]] || {
      printf 'invalid\n'
      continue
    }
    case "$target" in
      "$expected") [ -e "$target" ] || printf 'invalid\n' ;;
      *) printf 'invalid\n' ;;
    esac
  done)
  [[ -z "$invalid" ]]
}

_agent_canon_codex_digest() {
  local path=$1 link mode
  _agent_canon_validate_codex_home "$path" || return 1
  (
    cd "$path"
    {
      find . -type f -print | LC_ALL=C sort | while IFS= read -r link; do
        mode=$(stat -c '%a' -- "$link") || exit 1
        printf 'file\t%s\t%s\t%s\n' "$link" "$mode" \
          "$(sha256sum -- "$link" | awk '{print $1}')"
      done
      find . -type l -print | LC_ALL=C sort | while IFS= read -r link; do
        printf 'link\t%s\t%s\n' "$link" "$(readlink -- "$link")"
      done
    } | sha256sum | awk '{print $1}'
  )
}

_agent_canon_state_volume_labels_match() {
  local volume="${1:-$AGENT_CANON_STATE_VOLUME_NAME}"
  local volume_id label_runtime label_control label_state expected
  expected=$(_agent_canon_control_digest)
  volume_id=$("$AGENT_CANON_DOCKER_CMD" volume inspect --format '{{.Name}}' "$volume" 2>/dev/null) || return 1
  label_runtime=$("$AGENT_CANON_DOCKER_CMD" volume inspect \
    --format '{{index .Labels "io.agent-canon.runtime"}}' "$volume" 2>/dev/null) || return 1
  label_control=$("$AGENT_CANON_DOCKER_CMD" volume inspect \
    --format '{{index .Labels "io.agent-canon.control-root-digest"}}' "$volume" 2>/dev/null) || return 1
  label_state=$("$AGENT_CANON_DOCKER_CMD" volume inspect \
    --format '{{index .Labels "io.agent-canon.state"}}' "$volume" 2>/dev/null) || return 1
  [[ "$volume_id" == "$volume" && "$label_runtime" == shared-v1 &&
     "$label_control" == "$expected" && "$label_state" == controller-v1 ]]
}

_agent_canon_state_volume_creation_receipt_matches() {
  local volume=${1:-$AGENT_CANON_STATE_VOLUME_NAME}
  local receipt="${AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/state-volume-created.tsv}"
  [[ -f "$receipt" && ! -L "$receipt" ]] || return 1
  [[ "$(<"$receipt")" == $'schema\tagent-canon.state-volume-created.v1\nvolume\t'"$volume" ]]
}

_agent_canon_state_volume_write_creation_receipt() {
  local volume=${1:-$AGENT_CANON_STATE_VOLUME_NAME}
  local receipt="${AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/state-volume-created.tsv}"
  local temporary
  [[ -n "$volume" && "$volume" != */* && "$volume" != *$'\n'* ]] || return 1
  mkdir -p -- "$(dirname -- "$receipt")" || return 1
  temporary=$(mktemp "$receipt.tmp.XXXXXX") || return 1
  if ! {
    printf 'schema\tagent-canon.state-volume-created.v1\nvolume\t%s\n' "$volume" > "$temporary"
    chmod 600 "$temporary"
    mv -f -- "$temporary" "$receipt"
  }; then
    rm -f -- "$temporary"
    return 1
  fi
}

_agent_canon_state_volume_clear_creation_receipt() {
  local receipt="${AGENT_CANON_STATE_VOLUME_CREATION_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/state-volume-created.tsv}"
  [[ ! -L "$receipt" ]] || return 1
  if [[ "${AGENT_CANON_TEST_STATE_VOLUME_RECEIPT_REMOVE_FAIL:-0}" == 1 ]]; then
    return 1
  fi
  rm -f -- "$receipt" || return 1
  [[ ! -e "$receipt" && ! -L "$receipt" ]] || return 1
  AGENT_CANON_STATE_VOLUME_CREATED_HERE=0
  export AGENT_CANON_STATE_VOLUME_CREATED_HERE
}

_agent_canon_write_candidate_identity_receipt() {
  local container=$1 container_id=$2 image_ref=$3 image_id=$4
  local receipt="${AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/candidate-container.tsv}"
  local temporary
  [[ -n "$container" && "$container" != *$'\n'* && "$container" != *$'\t'* &&
     -n "$container_id" && "$container_id" != *$'\n'* && "$container_id" != *$'\t'* &&
     -n "$image_ref" && "$image_ref" != *$'\n'* && "$image_ref" != *$'\t'* &&
     -n "$image_id" && "$image_id" != *$'\n'* && "$image_id" != *$'\t'* ]] || return 1
  mkdir -p -- "$(dirname -- "$receipt")" || return 1
  temporary=$(mktemp "$receipt.tmp.XXXXXX") || return 1
  if ! {
    printf 'schema\tagent-canon.candidate-container.v1\n'
    printf 'name\t%s\n' "$container"
    printf 'id\t%s\n' "$container_id"
    printf 'image-ref\t%s\n' "$image_ref"
    printf 'image-id\t%s\n' "$image_id"
    printf 'runtime\tshared-v1\n'
    printf 'control-root-digest\t%s\n' "$(_agent_canon_control_digest)"
  } > "$temporary"; then
    rm -f -- "$temporary"
    return 1
  fi
  chmod 600 "$temporary" || { rm -f -- "$temporary"; return 1; }
  if ! mv -f -- "$temporary" "$receipt" ||
     [[ ! -f "$receipt" || -L "$receipt" ]]; then
    rm -f -- "$temporary"
    return 1
  fi
  AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT=$receipt
  AGENT_CANON_CANDIDATE_CONTAINER_ID=$container_id
  export AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT AGENT_CANON_CANDIDATE_CONTAINER_ID
}

_agent_canon_read_candidate_identity_receipt() {
  local container=$1
  local receipt="${AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/candidate-container.tsv}"
  local key value schema= name= container_id= image_ref= image_id= runtime= control= count=0
  [[ -f "$receipt" && ! -L "$receipt" ]] || return 1
  while IFS=$'\t' read -r key value; do
    case "$key" in
      schema) schema=$value; count=$((count + 1)) ;;
      name) name=$value; count=$((count + 1)) ;;
      id) container_id=$value; count=$((count + 1)) ;;
      image-ref) image_ref=$value; count=$((count + 1)) ;;
      image-id) image_id=$value; count=$((count + 1)) ;;
      runtime) runtime=$value; count=$((count + 1)) ;;
      control-root-digest) control=$value; count=$((count + 1)) ;;
      *) return 1 ;;
    esac
  done < "$receipt"
  [[ "$count" == 7 && "$schema" == agent-canon.candidate-container.v1 &&
     "$name" == "$container" && -n "$container_id" && -n "$image_ref" &&
     -n "$image_id" && "$runtime" == shared-v1 &&
     "$control" == "$(_agent_canon_control_digest)" ]] || return 1
  AGENT_CANON_CANDIDATE_CONTAINER_ID=$container_id
  export AGENT_CANON_CANDIDATE_CONTAINER_ID
  return 0
}

_agent_canon_clear_candidate_identity_receipt() {
  local receipt="${AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/candidate-container.tsv}"
  [[ ! -L "$receipt" ]] || return 1
  rm -f -- "$receipt" || return 1
  [[ ! -e "$receipt" && ! -L "$receipt" ]] || return 1
  unset AGENT_CANON_CANDIDATE_CONTAINER_ID AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT
}

_agent_canon_write_activation_commit_receipt() {
  local image_id=$1 container=$2
  local receipt="${AGENT_CANON_ACTIVATION_COMMIT_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/activation-committed.tsv}"
  local temporary
  [[ "$image_id" == sha256:* && -n "$container" &&
     "$container" != *$'\n'* && "$container" != *$'\t'* ]] || return 1
  [[ ! -L "$receipt" ]] || return 1
  mkdir -p -- "$(dirname -- "$receipt")" || return 1
  temporary=$(mktemp "$receipt.tmp.XXXXXX") || return 1
  if ! {
    printf 'schema\tagent-canon.activation-committed.v1\n'
    printf 'image-id\t%s\n' "$image_id"
    printf 'container\t%s\n' "$container"
  } > "$temporary"; then
    rm -f -- "$temporary"
    return 1
  fi
  chmod 600 "$temporary" || { rm -f -- "$temporary"; return 1; }
  if ! mv -f -- "$temporary" "$receipt" ||
     [[ ! -f "$receipt" || -L "$receipt" ]]; then
    rm -f -- "$temporary"
    return 1
  fi
  AGENT_CANON_ACTIVATION_COMMIT_RECEIPT=$receipt
  export AGENT_CANON_ACTIVATION_COMMIT_RECEIPT
}

_agent_canon_activation_commit_receipt_valid() {
  local receipt="${AGENT_CANON_ACTIVATION_COMMIT_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/activation-committed.tsv}"
  local key value schema= image_id= container= count=0
  [[ -f "$receipt" && ! -L "$receipt" ]] || return 1
  while IFS=$'\t' read -r key value; do
    case "$key" in
      schema) schema=$value; count=$((count + 1)) ;;
      image-id) image_id=$value; count=$((count + 1)) ;;
      container) container=$value; count=$((count + 1)) ;;
      *) return 1 ;;
    esac
  done < "$receipt"
  [[ "$count" == 3 && "$schema" == agent-canon.activation-committed.v1 &&
     "$image_id" == sha256:* && -n "$container" ]]
}

_agent_canon_clear_activation_commit_receipt() {
  local receipt="${AGENT_CANON_ACTIVATION_COMMIT_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/activation-committed.tsv}"
  [[ ! -L "$receipt" ]] || return 1
  if [[ "${AGENT_CANON_TEST_ACTIVATION_COMMIT_RECEIPT_REMOVE_FAIL:-0}" == 1 ]]; then
    return 1
  fi
  rm -f -- "$receipt" || return 1
  [[ ! -e "$receipt" && ! -L "$receipt" ]] || return 1
  unset AGENT_CANON_ACTIVATION_COMMIT_RECEIPT
}

_agent_canon_remove_fresh_state_volume() {
  local volume="${AGENT_CANON_STATE_VOLUME_NAME:-}"
  if [[ "${AGENT_CANON_STATE_VOLUME_CREATED_HERE:-0}" != 1 ]] &&
     _agent_canon_state_volume_creation_receipt_matches "$volume"; then
    AGENT_CANON_STATE_VOLUME_CREATED_HERE=1
    export AGENT_CANON_STATE_VOLUME_CREATED_HERE
  fi
  [[ "${AGENT_CANON_STATE_VOLUME_CREATED_HERE:-0}" == 1 && -n "$volume" ]] || return 0
  if ! "$AGENT_CANON_DOCKER_CMD" volume inspect "$volume" >/dev/null 2>&1; then
    _agent_canon_state_volume_clear_creation_receipt || return 1
    return 0
  fi
  # Re-read ownership before cleanup. A name collision or daemon race must
  # never turn candidate cleanup into deletion of another owner's volume.
  _agent_canon_state_volume_labels_match "$volume" || return 1
  "$AGENT_CANON_DOCKER_CMD" volume rm "$volume" >/dev/null 2>&1 || return 1
  _agent_canon_state_volume_clear_creation_receipt || return 1
}

_agent_canon_remove_fresh_candidate_resources() {
  local container=$(_agent_canon_container_name)
  local candidate_container_id=${1:-${AGENT_CANON_CANDIDATE_CONTAINER_ID:-}}
  local candidate_image_id=${AGENT_CANON_EXPECTED_IMAGE_ID:-}
  local cleanup_rc=0
  # Container creation and volume creation are independent receipts.  A
  # start/health failure with an adopted volume still owns the new candidate
  # container and must remove it, while preserving the adopted volume.
  if [[ "${AGENT_CANON_CANDIDATE_CONTAINER_CREATED_HERE:-0}" == 1 ]]; then
    # Ensure/start does not own the already-selected image.  The outer image
    # replacement transaction, when present, decides whether that image is a
    # failed candidate.  This local cleanup owns only the newly-created
    # container and independently-created volume.
    if _agent_canon_cleanup_candidate_resources "$container" "$candidate_image_id" \
      "$candidate_image_id" \
      "$candidate_container_id"; then
      AGENT_CANON_CANDIDATE_CONTAINER_CREATED_HERE=0
      export AGENT_CANON_CANDIDATE_CONTAINER_CREATED_HERE
    else
      cleanup_rc=1
    fi
  fi
  if [[ "${AGENT_CANON_STATE_VOLUME_CREATED_HERE:-0}" == 1 ]] &&
     ! _agent_canon_remove_fresh_state_volume; then
    cleanup_rc=1
  fi
  return "$cleanup_rc"
}

_agent_canon_cleanup_candidate_resources() {
  local container=${1:-} candidate_image_id=${2:-} old_image_id=${3:-}
  local expected_container_id=${4:-}
  local cleanup_rc=0
  local candidate_absent=0
  local candidate_receipt="${AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/candidate-container.tsv}"
  local observed_image_ref observed_image_id observed_runtime observed_control running
  if [[ -z "$expected_container_id" && -n "$container" ]]; then
    if _agent_canon_read_candidate_identity_receipt "$container"; then
      expected_container_id=$AGENT_CANON_CANDIDATE_CONTAINER_ID
    fi
  fi
  if [[ -z "$expected_container_id" && -n "$container" ]]; then
    # A name without a captured immutable ID is not evidence of the candidate.
    # It may only be used to prove that no object remains; an existing name is
    # a possible replacement and must not be mutated.
    if "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
      return 1
    fi
    if [[ -e "$candidate_receipt" || -L "$candidate_receipt" ]]; then
      _agent_canon_clear_candidate_identity_receipt || return 1
    fi
    candidate_absent=1
  fi
  if [[ -n "$expected_container_id" ]]; then
    # Every candidate field is read back through the captured immutable ID.
    # A missing ID is safe (the candidate is already absent); a failed stop or
    # remove is not, because recovery must not race a still-running process.
    if "$AGENT_CANON_DOCKER_CMD" container inspect "$expected_container_id" >/dev/null 2>&1; then
      if ! observed_runtime=$("$AGENT_CANON_DOCKER_CMD" container inspect \
        --format '{{index .Config.Labels "io.agent-canon.runtime"}}' "$expected_container_id" 2>/dev/null) ||
        ! observed_control=$("$AGENT_CANON_DOCKER_CMD" container inspect \
          --format '{{index .Config.Labels "io.agent-canon.control-root-digest"}}' "$expected_container_id" 2>/dev/null) ||
        ! observed_image_ref=$("$AGENT_CANON_DOCKER_CMD" container inspect \
          --format '{{.Config.Image}}' "$expected_container_id" 2>/dev/null) ||
        [[ "$observed_runtime" != shared-v1 ||
           "$observed_control" != "$(_agent_canon_control_digest)" ||
           -z "$observed_image_ref" ]]; then
        cleanup_rc=1
      elif ! observed_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
        --format '{{.Id}}' "$observed_image_ref" 2>/dev/null) ||
        [[ -n "$candidate_image_id" && "$observed_image_id" != "$candidate_image_id" ]]; then
        cleanup_rc=1
      elif ! "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$expected_container_id" >/dev/null 2>&1 ||
        ! running=$("$AGENT_CANON_DOCKER_CMD" container inspect \
          --format '{{.State.Running}}' "$expected_container_id" 2>/dev/null) ||
        [[ "$running" != false ]] ||
        ! "$AGENT_CANON_DOCKER_CMD" rm "$expected_container_id" >/dev/null 2>&1 ||
        "$AGENT_CANON_DOCKER_CMD" container inspect "$expected_container_id" >/dev/null 2>&1; then
        cleanup_rc=1
      fi
    fi
  elif ((candidate_absent == 0)); then
    cleanup_rc=1
  fi
  if [[ -n "$candidate_image_id" && "$candidate_image_id" != "$old_image_id" ]] &&
     "$AGENT_CANON_DOCKER_CMD" image inspect "$candidate_image_id" >/dev/null 2>&1; then
    "$AGENT_CANON_DOCKER_CMD" image rm "$candidate_image_id" >/dev/null 2>&1 || cleanup_rc=1
  fi
  if ((cleanup_rc == 0)); then
    _agent_canon_clear_candidate_identity_receipt || cleanup_rc=1
  fi
  return "$cleanup_rc"
}

_agent_canon_probe_state_volume() {
  local volume="${1:-$AGENT_CANON_STATE_VOLUME_NAME}"
  local allow_legacy=${2:-0}
  local caller_uid caller_gid probe_name
  [[ "$allow_legacy" == 0 || "$allow_legacy" == 1 ]] || return 1
  caller_uid=$(id -u)
  caller_gid=$(id -g)
  probe_name="agent-canon-volume-probe-$(_agent_canon_control_digest | cut -c1-16)-$$"
  "$AGENT_CANON_DOCKER_CMD" run --rm \
    --name "$probe_name" \
    --user "$caller_uid:$caller_gid" \
    --read-only \
    --network none \
    --tmpfs /tmp \
    --mount "type=volume,src=$volume,dst=$AGENT_CANON_VOLUME_DESTINATION,volume-nocopy" \
    --env AGENT_CANON_VOLUME_PROBE=1 \
    --env "AGENT_CANON_VOLUME_UID=$caller_uid" \
    --env "AGENT_CANON_VOLUME_GID=$caller_gid" \
    --env "AGENT_CANON_VOLUME_DIGEST=$(_agent_canon_control_digest)" \
    --env "AGENT_CANON_VOLUME_ALLOW_LEGACY=$allow_legacy" \
    --entrypoint /bin/sh \
    "$AGENT_CANON_IMAGE_REF" \
    -c 'set -eu
root=/var/lib/agent-canon
runtime="$root/runtime"
uid_value="$AGENT_CANON_VOLUME_UID"
gid_value="$AGENT_CANON_VOLUME_GID"
digest="$AGENT_CANON_VOLUME_DIGEST"
allow_legacy="$AGENT_CANON_VOLUME_ALLOW_LEGACY"
[ "$(id -u)" = "$uid_value" ] && [ "$(id -g)" = "$gid_value" ]
[ "$(stat -c "%a:%u:%g" "$root")" = "711:0:0" ]
marker="$root/.agent-canon-controller-volume-v1"
[ "$(stat -c "%a:%u:%g" "$runtime")" = "700:$uid_value:$gid_value" ]
[ "$(stat -c "%a:%u:%g" "$marker")" = "444:0:0" ]
[ -f "$marker" ] && [ "$(cat "$marker")" = "agent-canon-controller-volume/v1
$digest" ]
private_log="$root/private-log"
[ -d "$private_log" ] && [ ! -L "$private_log" ]
private_log_stat=$(stat -c "%a:%u:%g" "$private_log")
if [ "$private_log_stat" = "555:0:0" ]; then
  [ -z "$(find "$private_log" -type l -print -quit)" ]
  [ -z "$(find "$private_log" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ]
  while IFS= read -r private_log_path; do
    [ -z "$private_log_path" ] && continue
    if [ -d "$private_log_path" ]; then
      [ "$(stat -c "%a:%u:%g" "$private_log_path")" = "555:0:0" ]
    else
      [ "$(stat -c "%a:%u:%g" "$private_log_path")" = "444:0:0" ]
    fi
  done <<EOF_PRIVATE_LOG
$(find "$private_log" -mindepth 1 -print)
EOF_PRIVATE_LOG
else
  [ "$allow_legacy" = 1 ]
  [ "$private_log_stat" = "700:$uid_value:$gid_value" ]
  [ -z "$(find "$private_log" -type l -print -quit)" ]
  [ -z "$(find "$private_log" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ]
fi
probe="$runtime/.agent-canon-non-root-probe.$$"
printf "probe\n" > "$probe"
[ "$(cat "$probe")" = probe ]
mv "$probe" "$probe.renamed"
rm -f "$probe.renamed"'
}

_agent_canon_state_volume_transaction() {
  local action=$1 volume="${AGENT_CANON_STATE_VOLUME_NAME:-}"
  local transaction_name="agent-canon-volume-transaction-$(_agent_canon_control_digest | cut -c1-16)-$$"
  [[ "$action" == snapshot || "$action" == restore || "$action" == clear ]] ||
    _agent_canon_json_error state_volume_transaction_invalid \
      "controller state volume transaction action is invalid"
  [[ -n "$volume" ]] ||
    _agent_canon_json_error state_volume_transaction_invalid \
      "controller state volume transaction volume is unavailable"
  _agent_canon_state_volume_labels_match "$volume" ||
    _agent_canon_json_error state_volume_ownership_mismatch \
      "controller state volume identity changed before transaction"
  "$AGENT_CANON_DOCKER_CMD" run --rm \
    --name "$transaction_name" \
    --user 0:0 \
    --read-only \
    --network none \
    --tmpfs /tmp \
    --mount "type=volume,src=$volume,dst=$AGENT_CANON_VOLUME_DESTINATION,volume-nocopy" \
    --env "AGENT_CANON_VOLUME_TRANSACTION_ACTION=$action" \
    --env "AGENT_CANON_VOLUME_DIGEST=$(_agent_canon_control_digest)" \
    --env "AGENT_CANON_TEST_VOLUME_RESTORE_FAIL_AFTER=${AGENT_CANON_TEST_VOLUME_RESTORE_FAIL_AFTER:-}" \
    --entrypoint /bin/sh \
    "$AGENT_CANON_IMAGE_REF" \
    -c 'set -eu
root=/var/lib/agent-canon
runtime="$root/runtime"
[ -d "$root" ] && [ ! -L "$root" ] || exit 89
[ -d "$runtime" ] && [ ! -L "$runtime" ] || exit 89
transaction="$root/.agent-canon-bootstrap-transaction-v1"
manifest="$transaction/manifest.tsv"
logical_paths="state.json
owner.json
mounts.toml
mounts.tsv
rollback-plan.tsv
rollback-mounts.tsv
previous-image-id
generations
tasks
container-runtime"
action="$AGENT_CANON_VOLUME_TRANSACTION_ACTION"
cleanup_snapshot() {
  cleanup_rc=$?
  if [ "$action" = snapshot ] && [ "$cleanup_rc" -ne 0 ]; then
    rm -rf -- "$transaction" 2>/dev/null || :
  fi
  exit "$cleanup_rc"
}
trap cleanup_snapshot 0
is_logical_path() {
  case "$1" in
    state.json|owner.json|mounts.toml|mounts.tsv|rollback-plan.tsv|rollback-mounts.tsv|previous-image-id|generations|tasks|container-runtime) return 0 ;;
    *) return 1 ;;
  esac
}
remove_path() {
  path=$1
  if [ -e "$path" ] || [ -L "$path" ]; then
    rm -rf -- "$path"
  fi
}
case "$action" in
  snapshot)
    [ -f "$root/.agent-canon-controller-volume-v1" ] || exit 90
    [ ! -e "$transaction" ] && [ ! -L "$transaction" ] || exit 91
    umask 077
    mkdir "$transaction"
    chmod 700 "$transaction"
    printf "schema\tagent-canon.volume-transaction.v1\n" > "$manifest"
    for relative in $logical_paths; do
      source="$runtime/$relative"
      if [ -e "$source" ] || [ -L "$source" ]; then
        [ ! -L "$source" ] || exit 92
        if [ -d "$source" ]; then
          [ -z "$(find "$source" -type l -print -quit)" ] || exit 93
          [ -z "$(find "$source" -type f -links +1 -print -quit)" ] || exit 94
          [ -z "$(find "$source" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ] || exit 95
        else
          [ -f "$source" ] || exit 96
          [ "$(stat -c "%h" "$source")" = 1 ] || exit 97
        fi
        printf "present\t%s\n" "$relative" >> "$manifest"
        cp -a -- "$source" "$transaction/$relative"
        if [ -d "$source" ]; then
          [ -z "$(find "$transaction/$relative" -type l -print -quit)" ] || exit 98
          [ -z "$(find "$transaction/$relative" -type f -links +1 -print -quit)" ] || exit 99
          [ -z "$(find "$transaction/$relative" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ] || exit 100
        else
          [ "$(stat -c "%h" "$transaction/$relative")" = 1 ] || exit 101
        fi
      else
        printf "absent\t%s\n" "$relative" >> "$manifest"
      fi
    done
    [ "$(wc -l < "$manifest")" = 11 ] || exit 102
    ;;
  restore)
    [ -d "$transaction" ] && [ ! -L "$transaction" ] || exit 95
    [ -f "$manifest" ] && [ ! -L "$manifest" ] || exit 96
    [ "$(sed -n "1p" "$manifest")" = "schema\tagent-canon.volume-transaction.v1" ] || exit 97
    manifest_index=0
    while IFS="$(printf "\t")" read -r status relative; do
      [ "$status" = schema ] && continue
      is_logical_path "$relative" || exit 98
      manifest_index=$((manifest_index + 1))
      expected_relative=$(printf "%s\n" $logical_paths | sed -n "${manifest_index}p")
      [ "$relative" = "$expected_relative" ] || exit 98
      case "$status" in
        present)
          [ -e "$transaction/$relative" ] && [ ! -L "$transaction/$relative" ] || exit 103
          if [ -d "$transaction/$relative" ]; then
            [ -z "$(find "$transaction/$relative" -type l -print -quit)" ] || exit 104
            [ -z "$(find "$transaction/$relative" -type f -links +1 -print -quit)" ] || exit 105
            [ -z "$(find "$transaction/$relative" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ] || exit 106
          else
            [ -f "$transaction/$relative" ] || exit 107
            [ "$(stat -c "%h" "$transaction/$relative")" = 1 ] || exit 108
          fi ;;
        absent) [ ! -e "$transaction/$relative" ] && [ ! -L "$transaction/$relative" ] || exit 109 ;;
        *) exit 101 ;;
      esac
    done < "$manifest"
    [ "$manifest_index" -eq 10 ] || exit 98
    restore_stage="$transaction/.restore-stage"
    restore_old="$transaction/.restore-old"
    restore_touched="$transaction/.restore-touched"
    [ ! -e "$restore_stage" ] && [ ! -L "$restore_stage" ] || exit 110
    [ ! -e "$restore_old" ] && [ ! -L "$restore_old" ] || exit 111
    mkdir -p "$restore_stage/runtime" "$restore_old/runtime"
    : > "$restore_touched"
    for relative in $logical_paths; do
      status=$(grep -F "$(printf '\t')$relative" "$manifest" | cut -f1)
      if [ "$status" = present ]; then
        mkdir -p "$(dirname "$restore_stage/runtime/$relative")"
        cp -a -- "$transaction/$relative" "$restore_stage/runtime/$relative"
      fi
    done
    [ -z "$(find "$restore_stage/runtime" -type l -print -quit)" ] || exit 112
    [ -z "$(find "$restore_stage/runtime" -type f -links +1 -print -quit)" ] || exit 113
    [ -z "$(find "$restore_stage/runtime" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ] || exit 114
    restore_cleanup() {
      restore_rc=$?
      if [ "$restore_rc" -ne 0 ]; then
        while IFS= read -r relative; do
          [ -n "$relative" ] || continue
          remove_path "$runtime/$relative"
          if [ -e "$restore_old/runtime/$relative" ] || [ -L "$restore_old/runtime/$relative" ]; then
            mkdir -p "$(dirname "$runtime/$relative")"
            mv "$restore_old/runtime/$relative" "$runtime/$relative" 2>/dev/null || :
          fi
        done < "$restore_touched"
      fi
      rm -rf "$restore_stage" "$restore_old" "$restore_touched"
      trap - 0
      exit "$restore_rc"
    }
    trap restore_cleanup 0
    for relative in $logical_paths; do
      status=$(grep -F "$(printf '\t')$relative" "$manifest" | cut -f1)
      if [ -e "$runtime/$relative" ] || [ -L "$runtime/$relative" ]; then
        mkdir -p "$(dirname "$restore_old/runtime/$relative")"
        mv "$runtime/$relative" "$restore_old/runtime/$relative" || exit 115
        printf '%s\n' "$relative" >> "$restore_touched"
      fi
      if [ "$status" = present ]; then
        mkdir -p "$(dirname "$runtime/$relative")"
        mv "$restore_stage/runtime/$relative" "$runtime/$relative" || exit 116
        if ! grep -Fqx "$relative" "$restore_touched"; then
          printf '%s\n' "$relative" >> "$restore_touched"
        fi
      fi
      [ "${AGENT_CANON_TEST_VOLUME_RESTORE_FAIL_AFTER:-}" != "$relative" ] || exit 117
    done
    trap - 0
    rm -rf "$restore_stage" "$restore_old" "$restore_touched"
    ;;
  clear)
    if [ -e "$transaction" ] || [ -L "$transaction" ]; then
      [ -d "$transaction" ] && [ ! -L "$transaction" ] || exit 102
      rm -rf -- "$transaction"
    fi
    ;;
  *) exit 103 ;;
esac'
}

_agent_canon_prepare_state_volume_snapshot() {
  local volume="${AGENT_CANON_STATE_VOLUME_NAME:-}"
  # Finish every retained post-commit cleanup owner before arming a new
  # rollback generation.  A cleanup error is not an activation failure and
  # must never adopt the committed snapshot as the next rollback payload.
  _agent_canon_finish_committed_activation_cleanup || return $?
  [[ -n "$volume" ]] || return 0
  if [[ "${AGENT_CANON_STATE_VOLUME_CREATED_HERE:-0}" == 1 ]] ||
     _agent_canon_state_volume_creation_receipt_matches "$volume"; then
    return 0
  fi
  if ! "$AGENT_CANON_DOCKER_CMD" volume inspect "$volume" >/dev/null 2>&1; then
    return 0
  fi
  _agent_canon_init_state_volume || return $?
  _agent_canon_state_volume_transaction snapshot || return $?
  AGENT_CANON_STATE_VOLUME_SNAPSHOT_ACTIVE=1
  export AGENT_CANON_STATE_VOLUME_SNAPSHOT_ACTIVE
}

_agent_canon_restore_state_volume_snapshot() {
  local volume="${AGENT_CANON_STATE_VOLUME_NAME:-}"
  [[ "${AGENT_CANON_STATE_VOLUME_SNAPSHOT_ACTIVE:-0}" == 1 ]] || return 0
  [[ -n "$volume" ]] || return 2
  if ! "$AGENT_CANON_DOCKER_CMD" volume inspect "$volume" >/dev/null 2>&1; then
    return 2
  fi
  _agent_canon_state_volume_labels_match "$volume" || return 2
  _agent_canon_state_volume_transaction restore || return $?
  _agent_canon_state_volume_transaction clear || return $?
  AGENT_CANON_STATE_VOLUME_SNAPSHOT_ACTIVE=0
  export AGENT_CANON_STATE_VOLUME_SNAPSHOT_ACTIVE
}

_agent_canon_clear_state_volume_snapshot() {
  local volume="${AGENT_CANON_STATE_VOLUME_NAME:-}"
  [[ "${AGENT_CANON_STATE_VOLUME_SNAPSHOT_ACTIVE:-0}" == 1 ]] || return 0
  [[ -n "$volume" ]] || return 2
  if ! "$AGENT_CANON_DOCKER_CMD" volume inspect "$volume" >/dev/null 2>&1; then
    return 2
  fi
  _agent_canon_state_volume_labels_match "$volume" || return 2
  _agent_canon_state_volume_transaction clear || return $?
  AGENT_CANON_STATE_VOLUME_SNAPSHOT_ACTIVE=0
  export AGENT_CANON_STATE_VOLUME_SNAPSHOT_ACTIVE
}

_agent_canon_init_state_volume() {
  local volume="$AGENT_CANON_STATE_VOLUME_NAME"
  local label_runtime label_control label_state volume_id caller_uid caller_gid init_name init_readback
  if [[ -e "$AGENT_CANON_STATE_ROOT/codex-home" || -L "$AGENT_CANON_STATE_ROOT/codex-home" ]]; then
    if ! _agent_canon_validate_codex_home "$AGENT_CANON_STATE_ROOT/codex-home"; then
      _agent_canon_json_error codex_home_invalid \
        "legacy Codex home contains an unmanaged or unsafe link"
      return 2
    fi
  fi
  AGENT_CANON_STATE_VOLUME_CREATED_HERE=0
  if _agent_canon_state_volume_creation_receipt_matches "$volume"; then
    AGENT_CANON_STATE_VOLUME_CREATED_HERE=1
  fi
  export AGENT_CANON_STATE_VOLUME_CREATED_HERE
  if ! "$AGENT_CANON_DOCKER_CMD" volume inspect "$volume" >/dev/null 2>&1; then
    if ! "$AGENT_CANON_DOCKER_CMD" volume create \
      --label io.agent-canon.runtime=shared-v1 \
      --label "io.agent-canon.control-root-digest=$(_agent_canon_control_digest)" \
      --label io.agent-canon.state=controller-v1 \
      "$volume" >/dev/null; then
      _agent_canon_json_error state_volume_create_failed \
        "controller state volume could not be created"
      _agent_canon_state_volume_clear_creation_receipt || :
      return 2
    fi
    AGENT_CANON_STATE_VOLUME_CREATED_HERE=1
    export AGENT_CANON_STATE_VOLUME_CREATED_HERE
    if ! _agent_canon_state_volume_write_creation_receipt "$volume"; then
      _agent_canon_json_error state_volume_readback_failed \
        "fresh controller state volume creation receipt could not be recorded"
      _agent_canon_remove_fresh_state_volume || :
      return 2
    fi
  fi
  if ! volume_id=$("$AGENT_CANON_DOCKER_CMD" volume inspect \
    --format '{{.Name}}' "$volume" 2>/dev/null); then
    _agent_canon_json_error state_volume_readback_failed \
      "controller state volume could not be inspected"
    _agent_canon_remove_fresh_state_volume || :
    return 2
  fi
  label_runtime=$("$AGENT_CANON_DOCKER_CMD" volume inspect \
    --format '{{index .Labels "io.agent-canon.runtime"}}' "$volume" 2>/dev/null || true)
  label_control=$("$AGENT_CANON_DOCKER_CMD" volume inspect \
    --format '{{index .Labels "io.agent-canon.control-root-digest"}}' "$volume" 2>/dev/null || true)
  label_state=$("$AGENT_CANON_DOCKER_CMD" volume inspect \
    --format '{{index .Labels "io.agent-canon.state"}}' "$volume" 2>/dev/null || true)
  if ! [[ "$volume_id" == "$volume" && "$label_runtime" == shared-v1 &&
     "$label_control" == "$(_agent_canon_control_digest)" &&
     "$label_state" == controller-v1 ]]; then
    _agent_canon_json_error state_volume_ownership_mismatch \
      "controller state volume has unexpected identity or owner" || :
    _agent_canon_remove_fresh_state_volume || :
    return 2
  fi

  caller_uid=$(id -u)
  caller_gid=$(id -g)
  init_name="agent-canon-volume-init-$(_agent_canon_control_digest | cut -c1-16)-$$"
  if ! init_readback=$("$AGENT_CANON_DOCKER_CMD" run --rm \
    --name "$init_name" \
    --user 0:0 \
    --read-only \
    --network none \
    --tmpfs /tmp \
    --mount "type=volume,src=$volume,dst=$AGENT_CANON_VOLUME_DESTINATION,volume-nocopy" \
    --mount "type=bind,src=$AGENT_CANON_STATE_ROOT,dst=$AGENT_CANON_LEGACY_STATE_DESTINATION,readonly" \
    --env "AGENT_CANON_VOLUME_UID=$caller_uid" \
    --env "AGENT_CANON_VOLUME_GID=$caller_gid" \
    --env "AGENT_CANON_VOLUME_CREATED_HERE=${AGENT_CANON_STATE_VOLUME_CREATED_HERE:-0}" \
    --env "AGENT_CANON_VOLUME_DIGEST=$(_agent_canon_control_digest)" \
    --env "AGENT_CANON_TEST_LAYOUT_MIGRATION_AFTER=${AGENT_CANON_TEST_LAYOUT_MIGRATION_AFTER:-}" \
    --entrypoint /bin/sh \
    "$AGENT_CANON_IMAGE_REF" \
    -c 'set -eu
root=/var/lib/agent-canon
runtime="$root/runtime"
legacy=/var/lib/agent-canon-legacy-state
uid_value="$AGENT_CANON_VOLUME_UID"
gid_value="$AGENT_CANON_VOLUME_GID"
digest="$AGENT_CANON_VOLUME_DIGEST"
marker="$root/.agent-canon-controller-volume-v1"
copy_file() {
  source=$1
  destination=$2
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    [ -f "$destination" ] && cmp -s "$source" "$destination" || exit 41
  else
    cp -a "$source" "$destination"
  fi
}
copy_directory() {
  source=$1
  destination=$2
  allow_links=${3:-0}
  [ ! -L "$source" ] || exit 42
  [ -d "$source" ] || exit 43
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    [ -d "$destination" ] && [ ! -L "$destination" ] || exit 44
    if [ "$allow_links" != 1 ]; then
      [ -z "$(find "$destination" -type l -print -quit)" ] || exit 45
    fi
    diff -qr "$source" "$destination" >/dev/null || exit 46
  else
    cp -a "$source" "$destination"
  fi
}
marked=0
root_empty=0
[ -d "$root" ] && [ ! -L "$root" ] || exit 47
if [ -e "$marker" ] || [ -L "$marker" ]; then
  [ -f "$marker" ] && [ ! -L "$marker" ] || exit 47
  marked=1
else
  [ -z "$(find "$root" -mindepth 1 -maxdepth 1 -print -quit)" ] || exit 48
  root_empty=1
  marker_tmp=
  write_probe=
  cleanup_failed() {
    cleanup_rc=$?
    if [ "$cleanup_rc" -ne 0 ] && [ "$root_empty" = 1 ]; then
      rm -f "$marker" "$marker_tmp" "$write_probe" 2>/dev/null || :
      rm -rf "$runtime" "$root/private-log" 2>/dev/null || :
    fi
    exit "$cleanup_rc"
  }
  trap cleanup_failed 0
  mkdir -p "$runtime"
  for file in state.json owner.json; do
    if [ -e "$legacy/$file" ] || [ -L "$legacy/$file" ]; then
      [ -f "$legacy/$file" ] && [ ! -L "$legacy/$file" ] || exit 49
      copy_file "$legacy/$file" "$runtime/$file"
    fi
  done
  for directory in receipts generations tasks; do
    if [ -e "$legacy/$directory" ] || [ -L "$legacy/$directory" ]; then
      copy_directory "$legacy/$directory" "$runtime/$directory"
    fi
  done
  for directory in spool archive cache codex-home; do
    if [ -e "$legacy/$directory" ] || [ -L "$legacy/$directory" ]; then
      if [ "$directory" = codex-home ]; then
        copy_directory "$legacy/$directory" "$runtime/$directory" 1
      else
        copy_directory "$legacy/$directory" "$runtime/$directory"
      fi
    fi
  done
fi
if [ "$marked" = 1 ]; then
  # Pre-762 marked volumes kept operation data beside the marker.  Migrate
  # those directories as one transaction so a failed move cannot leave a
  # valid marker over a partially populated main-era runtime tree.
  root_stat=$(stat -c "%a:%u:%g" "$root")
  [ "$root_stat" = "700:$uid_value:$gid_value" ] ||
    [ "$root_stat" = "711:0:0" ] || exit 63
  marker_stat=$(stat -c "%a:%u:%g" "$marker")
  [ "$marker_stat" = "600:$uid_value:$gid_value" ] ||
    [ "$marker_stat" = "444:0:0" ] || exit 64
  migration="$root/.agent-canon-layout-migration-v1"
  migration_needed=0
  for name in exchange spool archive cache codex-home; do
    if [ -e "$root/$name" ] || [ -L "$root/$name" ]; then
      migration_needed=1
    fi
  done
  if [ "$migration_needed" = 1 ]; then
    [ ! -e "$migration" ] && [ ! -L "$migration" ] || exit 65
    mkdir -m 700 "$migration" "$migration/old" "$migration/staged" \
      "$migration/staged/runtime"
    created_runtime=0 created_receipts=0 created_generations=0 created_tasks=0
    moved_old= moved_new=
    [ -d "$runtime" ] && [ ! -L "$runtime" ] || {
      [ ! -e "$runtime" ] && [ ! -L "$runtime" ] || exit 81
      mkdir -m 700 "$runtime"
      created_runtime=1
    }
    [ -d "$runtime/receipts" ] || created_receipts=1
    [ -d "$runtime/generations" ] || created_generations=1
    [ -d "$runtime/tasks" ] || created_tasks=1
    migration_failed() {
      migration_rc=$?
      if [ "$migration_rc" -ne 0 ]; then
        for destination in $moved_new; do
          rm -rf "$runtime/$destination" 2>/dev/null || :
        done
        [ "$created_receipts" = 0 ] || rm -rf "$runtime/receipts" 2>/dev/null || :
        [ "$created_generations" = 0 ] || rm -rf "$runtime/generations" 2>/dev/null || :
        [ "$created_tasks" = 0 ] || rm -rf "$runtime/tasks" 2>/dev/null || :
        [ "$created_runtime" = 0 ] || rmdir "$runtime" 2>/dev/null || :
        for name in $moved_old; do
          if [ -e "$migration/old/$name" ] || [ -L "$migration/old/$name" ]; then
            mv "$migration/old/$name" "$root/$name" 2>/dev/null || :
          fi
        done
      fi
      rm -rf "$migration"
      trap - 0
      exit "$migration_rc"
    }
    trap migration_failed 0
    for name in exchange spool archive cache codex-home; do
      source="$root/$name"
      [ -e "$source" ] || [ -L "$source" ] || continue
      [ -d "$source" ] && [ ! -L "$source" ] || exit 66
      if [ "$name" = codex-home ]; then
        while IFS= read -r link; do
          [ -n "$link" ] || continue
          relative=${link#"$source"/}
          case "$relative" in
            config.toml|agents/*|hooks/*|skills/*) ;;
            *) exit 67 ;;
          esac
          case "$relative" in
            *//*|../*|*/../*|*/..|./*|*/./*|.) exit 68 ;;
          esac
          target=$(readlink "$link") || exit 69
          [ -n "$target" ] || exit 70
          case "$target" in
            *..*|*"$(printf '\n')"*|*"$(printf '\r')"*|*"$(printf '\t')"*) exit 70 ;;
          esac
        done <<EOF_LINKS
$(find "$source" -type l -print)
EOF_LINKS
      else
        [ -z "$(find "$source" -type l -print -quit)" ] || exit 71
      fi
      destination=container-runtime
      [ "$name" = exchange ] || destination=$name
      [ ! -e "$runtime/$destination" ] && [ ! -L "$runtime/$destination" ] || exit 72
      cp -a "$source" "$migration/staged/runtime/$destination" || exit 73
      [ -d "$migration/staged/runtime/$destination" ] &&
        [ ! -L "$migration/staged/runtime/$destination" ] || exit 74
      [ -z "$(find "$migration/staged/runtime/$destination" \
        ! -type d ! -type f ! -type l -print -quit)" ] || exit 75
      [ "$(stat -c "%a:%u:%g" "$migration/staged/runtime/$destination")" = \
        "700:$uid_value:$gid_value" ] || exit 82
    done
    for name in exchange spool archive cache codex-home; do
      if [ -e "$root/$name" ] || [ -L "$root/$name" ]; then
        mv "$root/$name" "$migration/old/$name" || exit 76
        moved_old="$moved_old $name"
        [ "${AGENT_CANON_TEST_LAYOUT_MIGRATION_AFTER:-}" != "$name" ] || exit 80
      fi
    done
    for name in container-runtime spool archive cache codex-home; do
      [ -e "$migration/staged/runtime/$name" ] || continue
      mv "$migration/staged/runtime/$name" "$runtime/$name" || exit 77
      moved_new="$moved_new $name"
    done
    for name in receipts generations tasks; do
      if [ -e "$runtime/$name" ] || [ -L "$runtime/$name" ]; then
        [ -d "$runtime/$name" ] && [ ! -L "$runtime/$name" ] || exit 78
      fi
      mkdir -m 700 -p "$runtime/$name" || exit 78
    done
    [ -d "$runtime/spool" ] || exit 78
    if [ -e "$runtime/spool/private-feedback" ] ||
       [ -L "$runtime/spool/private-feedback" ]; then
      [ -d "$runtime/spool/private-feedback" ] &&
        [ ! -L "$runtime/spool/private-feedback" ] || exit 79
    fi
    mkdir -m 700 -p "$runtime/spool/private-feedback" || exit 79
    rm -rf "$migration"
    trap - 0
  fi
fi
if [ "$marked" = 0 ]; then
  for file in state.json owner.json; do
    if [ -e "$legacy/$file" ] || [ -L "$legacy/$file" ]; then
      [ -f "$legacy/$file" ] && [ -f "$runtime/$file" ] && [ ! -L "$legacy/$file" ] && [ ! -L "$runtime/$file" ] || exit 51
      cmp -s "$legacy/$file" "$runtime/$file" || exit 52
    fi
  done
  for directory in receipts generations tasks; do
    if [ -e "$legacy/$directory" ] || [ -L "$legacy/$directory" ]; then
      [ -d "$legacy/$directory" ] && [ -d "$runtime/$directory" ] || exit 53
      [ -z "$(find "$legacy/$directory" -type l -print -quit)" ] || exit 54
      diff -qr "$legacy/$directory" "$runtime/$directory" >/dev/null || exit 55
    fi
  done
  for directory in spool archive cache codex-home; do
    if [ -e "$legacy/$directory" ] || [ -L "$legacy/$directory" ]; then
      [ -d "$legacy/$directory" ] && [ -d "$runtime/$directory" ] || exit 56
      if [ "$directory" != codex-home ]; then
        [ -z "$(find "$legacy/$directory" -type l -print -quit)" ] || exit 57
      fi
      diff -qr "$legacy/$directory" "$runtime/$directory" >/dev/null || exit 58
    fi
  done
fi
for directory in "$runtime" "$runtime/receipts" "$runtime/generations" "$runtime/tasks" \
  "$runtime/container-runtime" "$runtime/spool" "$runtime/archive" "$runtime/cache" \
  "$runtime/spool/private-feedback" "$runtime/codex-home" "$root/private-log"; do
  if [ "$marked" = 0 ]; then
    mkdir -p "$directory"
  else
    [ -d "$directory" ] && [ ! -L "$directory" ] || exit 59
  fi
done
for directory in "$root/private-log"; do
  if [ "$marked" = 0 ]; then
    mkdir -p "$directory"
  elif [ -e "$directory" ] || [ -L "$directory" ]; then
    [ -d "$directory" ] && [ ! -L "$directory" ] || exit 59
  else
    mkdir -p "$directory"
  fi
done
if [ "$marked" = 0 ]; then
  chown -R "$uid_value:$gid_value" "$root"
  find "$root" -type d -exec chmod 700 {} +
fi
chown 0:0 "$root"
chmod 711 "$root"
for directory in "$root" "$runtime" "$runtime/receipts" "$runtime/generations" "$runtime/tasks" \
  "$runtime/container-runtime" "$runtime/spool" "$runtime/archive" "$runtime/cache" \
  "$runtime/spool/private-feedback" "$runtime/codex-home" "$root/private-log"; do
  if [ "$directory" = "$root" ]; then
    [ "$(stat -c "%a:%u:%g" "$directory")" = "711:0:0" ] || exit 60
  elif [ "$directory" = "$root/private-log" ] && [ "$marked" = 1 ]; then
    private_log_stat=$(stat -c "%a:%u:%g" "$directory")
    if [ "$private_log_stat" != "555:0:0" ]; then
      [ "$private_log_stat" = "700:$uid_value:$gid_value" ] || exit 60
      [ -z "$(find "$root/private-log" -type l -print -quit)" ] || exit 62
      [ -z "$(find "$root/private-log" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ] || exit 62
    fi
  else
    [ "$(stat -c "%a:%u:%g" "$directory")" = "700:$uid_value:$gid_value" ] || exit 60
  fi
done
if [ "$marked" = 1 ] && [ "$(stat -c "%a:%u:%g" "$root/private-log")" = "555:0:0" ]; then
  [ -z "$(find "$root/private-log" -type l -print -quit)" ] || exit 62
  [ -z "$(find "$root/private-log" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ] || exit 62
  while IFS= read -r private_log_path; do
    [ -z "$private_log_path" ] && continue
    if [ -d "$private_log_path" ]; then
      [ "$(stat -c "%a:%u:%g" "$private_log_path")" = "555:0:0" ] || exit 62
    else
      [ "$(stat -c "%a:%u:%g" "$private_log_path")" = "444:0:0" ] || exit 62
    fi
  done <<EOF_PRIVATE_LOG
$(find "$root/private-log" -mindepth 1 -print)
EOF_PRIVATE_LOG
fi
write_probe="$runtime/.agent-canon-volume-write.$$"
printf "write\n" > "$write_probe"
[ "$(cat "$write_probe")" = "write" ] || exit 62
rm -f "$write_probe"
if [ "$marked" = 0 ]; then
  marker_tmp="$marker.$$"
  printf "agent-canon-controller-volume/v1\\n%s\\n" "$digest" > "$marker_tmp"
  chmod 444 "$marker_tmp"
  chown 0:0 "$marker_tmp"
  mv -f "$marker_tmp" "$marker"
fi
chown 0:0 "$marker"
chmod 444 "$marker"
marker_tmp="$root/.agent-canon-marker-check.$$"
printf "agent-canon-controller-volume/v1\\n%s\\n" "$digest" > "$marker_tmp"
cmp -s "$marker" "$marker_tmp" || exit 50
rm -f "$marker_tmp"
[ "$(stat -c "%a:%u:%g" "$marker")" = "444:0:0" ] || exit 61
printf "marker\\t%s\\ncontent\\tok\\n" "$digest"' ); then
    _agent_canon_json_error state_volume_init_failed \
      "controller state volume could not be initialized"
    _agent_canon_remove_fresh_state_volume || :
    return 2
  fi
  if [[ "$init_readback" != $'marker\t'"$(_agent_canon_control_digest)"$'\ncontent\tok' ]]; then
    _agent_canon_json_error state_volume_readback_failed \
      "controller state volume marker or migrated content readback failed"
    _agent_canon_remove_fresh_state_volume || :
    return 2
  fi
  if ! _agent_canon_probe_state_volume "$volume" 1; then
    _agent_canon_json_error state_volume_access_failed \
      "the resident caller could not access the controller state volume"
    _agent_canon_remove_fresh_state_volume || :
    return 2
  fi
}

_agent_canon_apply_volume_export() (
  set -e
  local kind=$1 host_path=$2 relative=$3 stream_path=$4 expected_digest=$5
  local temporary member_list member relative_path source_digest name staged target
  local backup_root= transaction_target= transaction_backup= transaction_kind= transaction_had_old=0
  local retain_backup=0
  cleanup_export() {
    local cleanup_rc=$?
    if [[ "$transaction_kind" == projection && -n "$transaction_target" ]]; then
      for name in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
        rm -f -- "$transaction_target/$name"
        if [[ -f "$transaction_backup/$name" ]]; then
          mv -- "$transaction_backup/$name" "$transaction_target/$name" || true
        fi
      done
    elif [[ -n "$transaction_target" ]]; then
      if [[ -e "$transaction_target" || -L "$transaction_target" ]]; then
        rm -rf -- "$transaction_target"
      fi
      if [[ "$transaction_had_old" == 1 && -e "$transaction_backup" ]]; then
        mv -- "$transaction_backup" "$transaction_target" || true
      fi
    fi
    rm -f -- "${member_list:-}" "${stream_path:-}"
    rm -rf -- "${temporary:-}"
    [[ "$retain_backup" == 1 ]] || rm -rf -- "${backup_root:-}"
    exit "$cleanup_rc"
  }
  trap cleanup_export 0
  begin_directory_transaction() {
    transaction_kind=directory
    transaction_target=$1
    backup_root=$(mktemp -d "$AGENT_CANON_RUNTIME_ROOT/.volume-export-backup.XXXXXX") || return 1
    transaction_backup="$backup_root/old"
    if [[ -e "$transaction_target" || -L "$transaction_target" ]]; then
      [[ ! -L "$transaction_target" ]] || return 1
      mv -- "$transaction_target" "$transaction_backup" || return 1
      transaction_had_old=1
    fi
  }
  finish_transaction() {
    rm -rf -- "$backup_root"
    transaction_target=
    transaction_backup=
    transaction_kind=
    transaction_had_old=0
    backup_root=
  }
  if [[ ! -f "$stream_path" || -L "$stream_path" || ! "$expected_digest" =~ ^[0-9a-f]{64}$ ]]; then
    _agent_canon_json_error volume_export_invalid "volume export stream or digest is invalid"
    return 2
  fi
  if [[ ! -d "$host_path" || -L "$host_path" ]]; then
    _agent_canon_json_error volume_export_destination_invalid "volume export destination is not a directory"
    return 2
  fi
  temporary=$(mktemp -d "$AGENT_CANON_RUNTIME_ROOT/.volume-export.XXXXXX") || {
    _agent_canon_json_error volume_export_failed "volume export staging directory could not be created"
    return 2
  }
  chmod 700 "$temporary"
  member_list=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.volume-export-members.XXXXXX") || {
    _agent_canon_json_error volume_export_failed "volume export member list could not be created"
    return 2
  }
  if ! tar -tf "$stream_path" >"$member_list"; then
    _agent_canon_json_error volume_export_failed "volume export archive could not be listed"
    return 2
  fi
  while IFS= read -r member; do
    member=${member#./}
    member=${member%/}
    [[ -z "$member" ]] && continue
    [[ "$member" != /* && "$member" != *$'\n'* &&
       "$member" != *$'\r'* && "$member" != *$'\t'* && "$member" != ../* &&
       "$member" != */../* && "$member" != *'/..' ]] || {
      _agent_canon_json_error volume_export_invalid "volume export contains an unsafe archive member"
      return 2
    }
  done < "$member_list"
  if ! tar -xpf "$stream_path" --no-same-owner -C "$temporary"; then
    _agent_canon_json_error volume_export_failed "volume export archive could not be extracted"
    return 2
  fi
  if [[ -n "$(find "$temporary" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ]]; then
    _agent_canon_json_error volume_export_invalid "volume export contains a special file"
    return 2
  fi
  if [[ -n "$(find "$temporary" -type f -links +1 -print -quit)" ]]; then
    _agent_canon_json_error volume_export_invalid "volume export contains a hardlink"
    return 2
  fi
  while IFS= read -r relative_path; do
    [[ "$relative_path" != *$'\n'* && "$relative_path" != *$'\r'* &&
       "$relative_path" != *$'\t'* ]] || {
      _agent_canon_json_error volume_export_invalid "volume export path contains a control character"
      return 2
    }
  done < <(find "$temporary" -mindepth 1 -printf '%P\n')
  case "$kind" in
    projection)
      for relative_path in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
        staged="$temporary/$relative_path"
        [[ ! -e "$staged" && ! -L "$staged" ]] ||
          [[ -f "$staged" && ! -L "$staged" ]] || {
            rm -rf -- "$temporary"
            _agent_canon_json_error volume_export_invalid "controller projection contains an invalid file"
          }
      done
      while IFS= read -r relative_path; do
        case "$relative_path" in
          mounts.toml|mounts.tsv|rollback-plan.tsv|rollback-mounts.tsv) ;;
          *) rm -rf -- "$temporary"; _agent_canon_json_error volume_export_invalid "controller projection contains an unexpected path" ;;
        esac
      done < <(find "$temporary" -mindepth 1 -maxdepth 1 -printf '%P\n')
      source_digest=$(
        for name in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
          if [[ -f "$temporary/$name" && ! -L "$temporary/$name" ]]; then
            printf '%s\t%s\n' "$name" "$(_agent_canon_sha256 "$temporary/$name")"
          else
            printf '%s\tabsent\n' "$name"
          fi
        done | sha256sum | awk '{print $1}'
      )
      backup_root=$(mktemp -d "$AGENT_CANON_RUNTIME_ROOT/.volume-export-backup.XXXXXX") || {
        _agent_canon_json_error volume_export_failed "controller projection backup could not be created"
        return 2
      }
      local backup_target="$backup_root/old" backup_presence="$backup_root/presence"
      mkdir -p "$backup_target"
      for name in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
        target="$host_path/$name"
        if [[ -e "$target" || -L "$target" ]]; then
          [[ -f "$target" && ! -L "$target" ]] || {
            _agent_canon_json_error volume_export_destination_invalid "controller projection target is not a regular file"
            return 2
          }
          printf 'present\t%s\n' "$name" >> "$backup_presence"
          cp -a -- "$target" "$backup_target/$name" || {
            _agent_canon_json_error volume_export_failed "controller projection backup could not be copied"
            return 2
          }
          [[ -f "$backup_target/$name" && ! -L "$backup_target/$name" ]] || {
            _agent_canon_json_error volume_export_failed "controller projection backup readback is invalid"
            return 2
          }
          [[ "$(_agent_canon_sha256 "$target")" == "$(_agent_canon_sha256 "$backup_target/$name")" ]] || {
            _agent_canon_json_error volume_export_failed "controller projection backup readback differs"
            return 2
          }
        else
          printf 'absent\t%s\n' "$name" >> "$backup_presence"
        fi
        if [[ "${AGENT_CANON_TEST_VOLUME_EXPORT_FAIL_BACKUP:-}" == "$name" ]]; then
          _agent_canon_json_error volume_export_failed "injected controller projection backup failure"
          return 2
        fi
      done
      [[ "$(wc -l < "$backup_presence")" == 4 ]] || {
        _agent_canon_json_error volume_export_failed "controller projection backup presence readback is incomplete"
        return 2
      }
      transaction_kind=projection
      transaction_target=$host_path
      transaction_backup=$backup_target
      for name in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
        staged="$temporary/$name"
        target="$host_path/$name"
        if [[ -f "$staged" && ! -L "$staged" ]]; then
          [[ ! -L "$target" ]] || { _agent_canon_json_error volume_export_destination_invalid "controller projection target is a symlink"; return 2; }
          mv -f -- "$staged" "$target" || { _agent_canon_json_error volume_export_failed "controller projection file could not be published"; return 2; }
          if [[ "${AGENT_CANON_TEST_VOLUME_EXPORT_FAIL_AFTER:-}" == "$name" ]]; then
            _agent_canon_json_error volume_export_failed "injected controller projection publish failure"
            return 2
          fi
        elif [[ -e "$target" || -L "$target" ]]; then
          [[ ! -L "$target" ]] || { _agent_canon_json_error volume_export_destination_invalid "controller projection target is a symlink"; return 2; }
          rm -f -- "$target" || { _agent_canon_json_error volume_export_failed "stale controller projection could not be removed"; return 2; }
        fi
      done
      ;;
    skill)
      [[ -d "$temporary/skill-projection" && ! -L "$temporary/skill-projection" ]] || {
        rm -rf -- "$temporary"
        _agent_canon_json_error volume_export_invalid "skill projection tree is missing"
      }
      [[ -z "$(find "$temporary" -mindepth 1 -maxdepth 1 ! -name skill-projection -print -quit)" ]] || {
        rm -rf -- "$temporary"
        _agent_canon_json_error volume_export_invalid "skill projection contains an unexpected path"
      }
      [[ -z "$(find "$temporary/skill-projection" -type l -print -quit)" ]] || {
        _agent_canon_json_error volume_export_invalid "skill projection contains a symlink"
        return 2
      }
      [[ -z "$(find "$temporary/skill-projection" ! -type d ! -type f -print -quit)" ]] || {
        _agent_canon_json_error volume_export_invalid "skill projection contains a special file"
        return 2
      }
      source_digest=$(_agent_canon_path_digest "$temporary/skill-projection") || {
        _agent_canon_json_error volume_export_invalid "skill projection digest could not be computed"
        return 2
      }
      target="$host_path/skill-projection"
      begin_directory_transaction "$target" || {
        _agent_canon_json_error volume_export_destination_invalid "skill projection target is not a regular directory"
        return 2
      }
      mv -- "$temporary/skill-projection" "$target" || {
        _agent_canon_json_error volume_export_failed "skill projection could not be published"
        return 2
      }
      ;;
    eval)
      [[ -d "$temporary/$relative" && ! -L "$temporary/$relative" ]] || {
        rm -rf -- "$temporary"
        _agent_canon_json_error volume_export_invalid "evaluation tree is missing"
      }
      [[ -z "$(find "$temporary" -mindepth 1 -maxdepth 1 ! -name "$relative" -print -quit)" ]] || {
        rm -rf -- "$temporary"
        _agent_canon_json_error volume_export_invalid "evaluation export contains an unexpected path"
      }
      [[ -z "$(find "$temporary/$relative" -type l -print -quit)" ]] || {
        _agent_canon_json_error volume_export_invalid "evaluation export contains a symlink"
        return 2
      }
      [[ -z "$(find "$temporary/$relative" ! -type d ! -type f -print -quit)" ]] || {
        _agent_canon_json_error volume_export_invalid "evaluation export contains a special file"
        return 2
      }
      source_digest=$(_agent_canon_path_digest "$temporary/$relative") || {
        _agent_canon_json_error volume_export_invalid "evaluation digest could not be computed"
        return 2
      }
      target="$host_path/$relative"
      begin_directory_transaction "$target" || {
        _agent_canon_json_error volume_export_destination_invalid "evaluation target is not a regular directory"
        return 2
      }
      mv -- "$temporary/$relative" "$target" || {
        _agent_canon_json_error volume_export_failed "evaluation tree could not be published"
        return 2
      }
      ;;
    private-feedback)
      [[ -z "$(find "$temporary" -type l -print -quit)" ]] || {
        _agent_canon_json_error volume_export_invalid "private feedback contains a symlink"
        return 2
      }
      [[ -z "$(find "$temporary" ! -type d ! -type f -print -quit)" ]] || {
        _agent_canon_json_error volume_export_invalid "private feedback contains a special file"
        return 2
      }
      source_digest=$(
        cd "$temporary" && find . -type f ! -name .agent-canon-private-log-v1 -exec sha256sum {} + |
          LC_ALL=C sort | sha256sum | awk '{print $1}'
      )
      begin_directory_transaction "$host_path" || {
        _agent_canon_json_error volume_export_destination_invalid "private feedback destination is not a regular directory"
        return 2
      }
      mv -- "$temporary" "$host_path" || {
        _agent_canon_json_error volume_export_failed "private feedback could not be published"
        return 2
      }
      ;;
    codex-home)
      _agent_canon_validate_codex_home "$temporary" || {
        _agent_canon_json_error volume_export_invalid "Codex home contains an unmanaged symlink"
        return 2
      }
      [[ -z "$(find "$temporary" ! -type d ! -type f ! -type l -print -quit)" ]] || {
        _agent_canon_json_error volume_export_invalid "Codex home contains a special file"
        return 2
      }
      source_digest=$(_agent_canon_codex_digest "$temporary") || {
        _agent_canon_json_error volume_export_invalid "Codex home digest could not be computed"
        return 2
      }
      begin_directory_transaction "$host_path" || {
        _agent_canon_json_error volume_export_destination_invalid "Codex home destination is not a regular directory"
        return 2
      }
      mv -- "$temporary" "$host_path" || {
        _agent_canon_json_error volume_export_failed "Codex home could not be published"
        return 2
      }
      if [[ "${AGENT_CANON_TEST_VOLUME_EXPORT_FAIL_AFTER:-}" == codex-home ]]; then
        _agent_canon_json_error volume_export_failed "injected Codex home publish failure"
        return 2
      fi
      ;;
    *)
      rm -rf -- "$temporary"
      _agent_canon_json_error volume_export_invalid "volume export kind is not supported"
      ;;
  esac
  [[ "$source_digest" == "$expected_digest" ]] || {
    rm -rf -- "$temporary"
    _agent_canon_json_error volume_copy_failed "volume export digest readback differs"
    return 2
  }
  finish_transaction
  rm -rf -- "$temporary"
)

_agent_canon_volume_copy() {
  local direction=$1 kind=$2 host_path=$3 relative=${4:-}
  local volume=${AGENT_CANON_STATE_VOLUME_NAME:-}
  local copy_name="agent-canon-copy-$(_agent_canon_control_digest | cut -c1-16)-$$"
  _agent_canon_ensure_projection_layout || return $?
  [[ "$direction" == import || "$direction" == export || "$direction" == clear ]] ||
    _agent_canon_json_error volume_copy_invalid "volume copy direction is invalid"
  if [[ "$direction" != clear ]]; then
    [[ "$host_path" = /* && "$host_path" != *$'\n'* && "$host_path" != *$'\r'* &&
       "$host_path" != *$'\t'* && "$host_path" != *,* ]] ||
      _agent_canon_json_error volume_copy_invalid "volume copy host path is invalid"
  fi
  [[ "$kind" == source-sync || "$kind" == mount-registry || "$kind" == host-mounts ||
     "$kind" == rollback-mounts ||
     "$kind" == private-log || "$kind" == codex-home || "$kind" == projection ||
     "$kind" == skill || "$kind" == eval || "$kind" == private-feedback ]] ||
    _agent_canon_json_error volume_copy_invalid "volume copy kind is not allowlisted"
  if [[ "$direction" == import ]]; then
    [[ -e "$host_path" || -L "$host_path" ]] ||
      _agent_canon_json_error volume_copy_source_missing "volume copy source is missing: $kind"
  elif [[ "$direction" == export ]]; then
    mkdir -p -- "$host_path" ||
      _agent_canon_json_error volume_copy_destination_invalid "volume copy destination is unavailable: $kind"
  fi
  if [[ "$kind" == eval || "$kind" == private-feedback ]]; then
    [[ "$relative" =~ ^[A-Za-z0-9_.-]{1,128}$ ]] ||
      _agent_canon_json_error volume_copy_invalid "volume copy relative ID is invalid"
  fi
  local volume_mount="type=volume,src=$volume,dst=$AGENT_CANON_VOLUME_DESTINATION"
  [[ "$direction" == export ]] && volume_mount+=",readonly"
  local -a mounts=(--mount "$volume_mount")
  if [[ "$direction" == import ]]; then
    mounts+=(--mount "type=bind,src=$host_path,dst=/agent-canon-copy-input,readonly")
  fi
  if [[ "$kind" == codex-home && "$direction" == import ]]; then
    mounts+=(--mount "type=bind,src=$AGENT_CANON_REPOSITORY_ROOT,dst=$AGENT_CANON_REPOSITORY_ROOT,readonly")
  fi
  local -a copy_command=( "$AGENT_CANON_DOCKER_CMD" run --rm \
    --name "$copy_name" \
    --user 0:0 \
    --read-only \
    --network none \
    --tmpfs /tmp \
    "${mounts[@]}" \
    --env "AGENT_CANON_COPY_DIRECTION=$direction" \
    --env "AGENT_CANON_COPY_KIND=$kind" \
    --env "AGENT_CANON_COPY_RELATIVE=$relative" \
    --env "AGENT_CANON_COPY_UID=$(id -u)" \
    --env "AGENT_CANON_COPY_GID=$(id -g)" \
    --env "AGENT_CANON_COPY_INSTALL_ROOT=${AGENT_CANON_REPOSITORY_ROOT:-}" \
    --env "AGENT_CANON_PROJECTION_LAYOUT=$AGENT_CANON_PROJECTION_LAYOUT" \
    --env "AGENT_CANON_TEST_PRIVATE_LOG_IMPORT_FAIL_AFTER=${AGENT_CANON_TEST_PRIVATE_LOG_IMPORT_FAIL_AFTER:-}" \
    --env "AGENT_CANON_COPY_DIGEST=$([[ "$direction" == import ]] && { if [[ "$kind" == codex-home ]]; then _agent_canon_codex_digest "$host_path"; else _agent_canon_path_digest "$host_path"; fi; } 2>/dev/null || true)" \
    --entrypoint /bin/sh \
    "$AGENT_CANON_IMAGE_REF" \
    -c 'set -eu
root=/var/lib/agent-canon
runtime="$root/runtime"
[ -d "$runtime" ] || runtime="$root"
exchange_root="$runtime/container-runtime"
spool_root="$runtime/spool"
codex_root="$runtime/codex-home"
[ -d "$exchange_root" ] || exchange_root="$root/exchange"
[ -d "$spool_root" ] || spool_root="$root/spool"
[ -d "$codex_root" ] || codex_root="$root/codex-home"
projection_root="$exchange_root"
if [ "${AGENT_CANON_PROJECTION_LAYOUT:-container-runtime-v1}" = legacy-runtime-v1 ]; then
  projection_root="$runtime"
fi
direction="$AGENT_CANON_COPY_DIRECTION"
kind="$AGENT_CANON_COPY_KIND"
relative="$AGENT_CANON_COPY_RELATIVE"
uid_value="$AGENT_CANON_COPY_UID"
gid_value="$AGENT_CANON_COPY_GID"
digest="$AGENT_CANON_COPY_DIGEST"
install_root="$AGENT_CANON_COPY_INSTALL_ROOT"
digest_field() {
  set -- $(cat)
  [ "$#" -ge 1 ] || return 1
  printf "%s" "$1"
}
file_digest() {
  result=$(sha256sum -- "$1") || return 1
  set -- $result
  [ "$#" -ge 1 ] || return 1
  printf "%s" "$1"
}
tree_digest() {
  (cd "$1" && find . -type f ! -name .agent-canon-private-log-v1 -exec sha256sum {} + | LC_ALL=C sort | sha256sum | digest_field)
}
codex_digest() {
  validate_codex_links "$1" "${2:-1}" || return 1
  (
    cd "$1"
    {
      find . -type f -print | LC_ALL=C sort | while IFS= read -r link; do
        mode=$(stat -c "%a" -- "$link") || exit 1
        printf "file\t%s\t%s\t%s\n" "$link" "$mode" \
          "$(file_digest "$link")"
      done
      find . -type l -print | LC_ALL=C sort | while IFS= read -r link; do
        printf "link\t%s\t%s\n" "$link" "$(readlink -- "$link")"
      done
    } | sha256sum | digest_field
  )
}
projection_digest() {
  for name in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
    if [ -f "$1/$name" ] && [ ! -L "$1/$name" ]; then
      printf "%s\t%s\n" "$name" "$(file_digest "$1/$name")"
    else
      printf "%s\\tabsent\\n" "$name"
    fi
  done | sha256sum | digest_field
}
validate_codex_links() {
  allowed="$install_root/.codex"
  require_targets="${2:-1}"
  if [ "$require_targets" = 1 ]; then
    [ -d "$allowed" ] && [ ! -L "$allowed" ] || return 1
  else
    [ "$allowed" = "${install_root}/.codex" ] || return 1
  fi
  invalid=$(find "$1" -type l -print | while IFS= read -r link; do
    relative_link=${link#"$1"/}
    case "$relative_link" in
      config.toml|agents/*|hooks/*|skills/*) ;;
      *) printf "invalid\n"; continue ;;
    esac
    case "$relative_link" in
      *//*|../*|*/../*|*/..|./*|*/./*|.) printf "invalid\\n"; continue ;;
      config.toml) expected="$allowed/config.toml" ;;
      agents/*|hooks/*) expected="$allowed/$relative_link" ;;
      skills/*) expected="$allowed/personal/skills/${relative_link#skills/}" ;;
    esac
    target=$(readlink -- "$link" 2>/dev/null || true)
    case "$target" in
      /*) [ "$target" = "$expected" ] || printf "invalid\\n" ;;
      *) printf "invalid\\n" ;;
    esac
  done)
  [ -z "$invalid" ]
}
if [ "$direction" = clear ]; then
  case "$kind" in
    host-mounts) rm -f -- "$root/host-mounts.tsv" ;;
    rollback-mounts) rm -f -- "$runtime/rollback-mounts.tsv" ;;
    *) exit 81 ;;
  esac
elif [ "$direction" = import ]; then
  input=/agent-canon-copy-input
  case "$kind" in
    source-sync) destination="$root/source-sync.json"; mode=444; expected=file ;;
    mount-registry) destination="$root/mount-registry.toml"; mode=444; expected=file ;;
    host-mounts) destination="$root/host-mounts.tsv"; mode=444; expected=file ;;
    rollback-mounts) destination="$runtime/rollback-mounts.tsv"; mode=444; expected=file ;;
    private-log) destination="$root/private-log"; mode=555; expected=directory ;;
    codex-home) destination="$codex_root"; mode=700; expected=directory ;;
    *) exit 64 ;;
  esac
  if [ "$expected" = file ]; then
    [ -f "$input" ] && [ ! -L "$input" ] || exit 65
    temporary="$destination.$$"
    cp -- "$input" "$temporary"
    [ -n "$digest" ] && [ "$(file_digest "$temporary")" = "$digest" ] || exit 82
    chmod "$mode" "$temporary"
    chown 0:0 "$temporary"
    mv -f -- "$temporary" "$destination"
  else
    [ -d "$input" ] && [ ! -L "$input" ] || exit 66
    if [ "$kind" = codex-home ]; then
      validate_codex_links "$input" || exit 67
    else
      [ -z "$(find "$input" -type l -print -quit)" ] || exit 67
      [ -z "$(find "$input" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ] || exit 67
    fi
    skip_copy=0
    marker_value=$(printf "agent-canon-private-log/v1\n%s" "$digest")
    # Always stage private-log before publication.  A matching content marker
    # does not prove that an adopted legacy tree already has normalized
    # ownership and modes.
    if [ "$kind" = private-log ] && [ "$skip_copy" = 0 ]; then
      temporary="$destination.tmp.$$"
      backup="$destination.backup.$$"
      rm -rf "$temporary" "$backup"
      mkdir -p "$temporary"
      cp -a "$input/." "$temporary/"
      [ "$(tree_digest "$temporary")" = "$digest" ] || exit 83
      printf "agent-canon-private-log/v1\n%s\n" "$digest" > "$temporary/.agent-canon-private-log-v1"
      find "$temporary" -type d -exec chmod 555 {} +
      find "$temporary" -type f -exec chmod 444 {} +
      chown -R 0:0 "$temporary"
      [ "$(stat -c "%a:%u:%g" "$temporary")" = 555:0:0 ] || exit 83
      [ "$(cat "$temporary/.agent-canon-private-log-v1")" = "$marker_value" ] || exit 83
      had_backup=0
      if [ -e "$destination" ] || [ -L "$destination" ]; then
        [ -d "$destination" ] && [ ! -L "$destination" ] || exit 68
        mv "$destination" "$backup"
        had_backup=1
      fi
      if ! mv "$temporary" "$destination"; then
        rm -rf "$temporary" "$destination"
        [ "$had_backup" = 0 ] || mv "$backup" "$destination"
        exit 84
      fi
      if [ "${AGENT_CANON_TEST_PRIVATE_LOG_IMPORT_FAIL_AFTER:-}" = publish ] ||
         [ "$(tree_digest "$destination")" != "$digest" ] ||
         [ "$(stat -c "%a:%u:%g" "$destination")" != 555:0:0 ] ||
         [ "$(cat "$destination/.agent-canon-private-log-v1")" != "$marker_value" ]; then
        rm -rf "$destination"
        [ "$had_backup" = 0 ] || mv "$backup" "$destination"
        exit 84
      fi
      rm -rf "$backup"
      skip_copy=1
    elif [ "$skip_copy" = 0 ] && { [ -e "$destination" ] || [ -L "$destination" ]; }; then
      [ -d "$destination" ] && [ ! -L "$destination" ] || exit 68
      find "$destination" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    elif [ "$skip_copy" = 0 ]; then
      mkdir -p "$destination"
    fi
    if [ "$skip_copy" = 0 ]; then
      cp -a "$input/." "$destination/"
      if [ "$kind" = codex-home ]; then
        validate_codex_links "$destination" || exit 85
      fi
      if [ "$kind" = codex-home ]; then
        [ -n "$digest" ] && [ "$(codex_digest "$destination")" = "$digest" ] || exit 83
      else
        [ -n "$digest" ] && [ "$(tree_digest "$destination")" = "$digest" ] || exit 83
      fi
      find "$destination" -type d -exec chmod 700 {} +
      chown -R "$uid_value:$gid_value" "$destination"
    fi
    if [ "$kind" = private-log ]; then
      [ -d "$destination" ] && [ ! -L "$destination" ] || exit 86
      [ -z "$(find "$destination" -type l -print -quit)" ] || exit 86
      [ -z "$(find "$destination" -mindepth 1 ! -type d ! -type f ! -type l -print -quit)" ] || exit 86
      while IFS= read -r private_log_path; do
        [ -n "$private_log_path" ] || continue
        if [ -d "$private_log_path" ]; then
          [ "$(stat -c "%a:%u:%g" "$private_log_path")" = 555:0:0 ] || exit 86
        else
          [ "$(stat -c "%a:%u:%g" "$private_log_path")" = 444:0:0 ] || exit 86
        fi
      done <<EOF_PRIVATE_LOG
$(find "$destination" -mindepth 1 -print)
EOF_PRIVATE_LOG
    fi
  fi
  if [ "$direction" = import ]; then
    printf "volume-copy-digest\t%s\n" "$digest"
  fi
else
  case "$kind" in
    projection)
      source="$projection_root"; [ -d "$source" ] && [ ! -L "$source" ] || exit 69
      members=$(mktemp)
      for name in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
        if [ -e "$source/$name" ]; then
          [ -f "$source/$name" ] && [ ! -L "$source/$name" ] || { rm -f "$members"; exit 70; }
          printf "%s\n" "$name" >> "$members"
        fi
      done
      source_digest=$(projection_digest "$source")
      tar -cf - -C "$source" --no-recursion -T "$members"
      rm -f "$members" ;;
    skill)
      source="$exchange_root/skill-projection"; [ -d "$source" ] && [ ! -L "$source" ] || exit 71
      [ -z "$(find "$source" -type l -print -quit)" ] || exit 72
      [ -z "$(find "$source" ! -type d ! -type f ! -type l -print -quit)" ] || {
        printf 'volume-export-invalid\n' >&2
        exit 72
      }
      source_digest=$(tree_digest "$source")
      tar -cf - -C "$exchange_root" skill-projection ;;
    eval)
      source="$spool_root/$relative"; [ -d "$source" ] && [ ! -L "$source" ] || exit 73
      [ -z "$(find "$source" -type l -print -quit)" ] || exit 74
      source_digest=$(tree_digest "$source")
      tar -cf - -C "$spool_root" "$relative" ;;
    private-feedback)
      source="$spool_root/private-feedback"; [ -d "$source" ] && [ ! -L "$source" ] || exit 75
      [ -z "$(find "$source" -type l -print -quit)" ] || exit 76
      source_digest=$(tree_digest "$source")
      tar -cf - -C "$source" . ;;
    codex-home)
      source="$codex_root"; [ -d "$source" ] && [ ! -L "$source" ] || exit 77
      validate_codex_links "$source" 0 || exit 78
      source_digest=$(codex_digest "$source" 0)
      tar -cf - -C "$source" . ;;
    *) exit 79 ;;
  esac
printf "volume-copy-digest\t%s\n" "$source_digest" >&2
fi' )
  if [[ "$direction" == export ]]; then
    local stream_path digest_path expected_digest copy_readback
    stream_path=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.volume-export.XXXXXX") ||
      _agent_canon_json_error volume_copy_failed "volume export stream file could not be created"
    digest_path=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.volume-export-digest.XXXXXX") || {
      rm -f -- "$stream_path"
      _agent_canon_json_error volume_copy_failed "volume export digest file could not be created"
    }
    if ! "${copy_command[@]}" >"$stream_path" 2>"$digest_path"; then
      if grep -Fq 'volume-export-invalid' "$digest_path"; then
        rm -f -- "$stream_path" "$digest_path"
        _agent_canon_json_error volume_export_invalid "volume export contains an unsupported file type"
      fi
      rm -f -- "$stream_path" "$digest_path"
      _agent_canon_json_error volume_copy_failed "volume copy failed: $direction/$kind"
    fi
    copy_readback=$(<"$digest_path")
    [[ "$copy_readback" =~ ^$'volume-copy-digest\t'[0-9a-f]{64}$ ]] || {
      rm -f -- "$stream_path" "$digest_path"
      _agent_canon_json_error volume_copy_readback_failed "volume export digest readback is invalid"
    }
    expected_digest=${copy_readback#*$'\t'}
    if _agent_canon_apply_volume_export "$kind" "$host_path" "$relative" \
      "$stream_path" "$expected_digest"; then
      :
    else
      local export_rc=$?
      rm -f -- "$stream_path" "$digest_path"
      return "$export_rc"
    fi
    rm -f -- "$stream_path" "$digest_path"
  elif [[ "$direction" == clear ]]; then
    if ! "${copy_command[@]}" >/dev/null; then
      _agent_canon_json_error volume_copy_failed "volume copy failed: $direction/$kind"
    fi
  else
    local copy_readback
    if ! copy_readback=$("${copy_command[@]}" ); then
      _agent_canon_json_error volume_copy_failed "volume copy failed: $direction/$kind"
    fi
    [[ "$copy_readback" =~ ^$'volume-copy-digest\t'[0-9a-f]{64}$ ]] ||
      _agent_canon_json_error volume_copy_readback_failed "volume import digest readback is invalid"
  fi
}

_agent_canon_import_host_inputs() {
  local import_rc
  _agent_canon_volume_copy import source-sync \
    "$AGENT_CANON_RUNTIME_ROOT/source-sync.json" || {
      import_rc=$?
      return "$import_rc"
    }
  _agent_canon_volume_copy import mount-registry \
    "$AGENT_CANON_STATE_ROOT/mounts.toml" || {
      import_rc=$?
      return "$import_rc"
    }
  _agent_canon_volume_copy import host-mounts \
    "$AGENT_CANON_STATE_ROOT/mounts.tsv" || {
      import_rc=$?
      return "$import_rc"
    }
  _agent_canon_volume_copy import private-log "$AGENT_CANON_PRIVATE_LOG_ROOT" || {
    import_rc=$?
    return "$import_rc"
  }
}

_agent_canon_publish_controller_projection() (
  set -e
  _agent_canon_ensure_projection_layout
  local exchange="$AGENT_CANON_STATE_ROOT/container-runtime"
  [[ "$AGENT_CANON_PROJECTION_LAYOUT" == legacy-runtime-v1 ]] &&
    exchange="$AGENT_CANON_STATE_ROOT"
  local staging= backup_root= backup_presence= transaction_active=0 retain_backup=0
  local source target expected_digest actual_digest name
  cleanup_projection() {
    local cleanup_rc=$?
    if [[ "$transaction_active" == 1 ]]; then
      for name in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
        target="$AGENT_CANON_STATE_ROOT/$name"
        rm -f -- "$target" || true
        if [[ -f "$backup_root/$name" ]]; then
          mv -- "$backup_root/$name" "$target" || true
        fi
      done
    fi
    rm -rf -- "${staging:-}"
    [[ "${retain_backup:-0}" == 1 ]] || rm -rf -- "${backup_root:-}"
    exit "$cleanup_rc"
  }
  trap cleanup_projection 0
  _agent_canon_volume_copy export projection "$exchange"
  [[ -d "$exchange" && ! -L "$exchange" ]] ||
    _agent_canon_json_error controller_projection_invalid \
      "controller projection exchange is unavailable"
  staging=$(mktemp -d "$AGENT_CANON_RUNTIME_ROOT/.manifest-projection.XXXXXX") ||
    _agent_canon_json_error controller_projection_invalid \
      "controller projection staging directory could not be created"
  chmod 700 "$staging"
  # global-links.tsv is host-owned. It is intentionally not a resident
  # projection: a resident-authored deletion list must never drive host
  # symlink removal.
  for source in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
    if [[ -e "$exchange/$source" || -L "$exchange/$source" ]]; then
      [[ -f "$exchange/$source" && ! -L "$exchange/$source" ]] ||
        _agent_canon_json_error controller_projection_invalid \
          "controller projection is not a regular file: $source"
      cp -- "$exchange/$source" "$staging/$source" ||
        _agent_canon_json_error controller_projection_invalid \
          "controller projection could not be staged: $source"
    fi
  done
  for source in $(find "$staging" -mindepth 1 -maxdepth 1 -printf '%f\n'); do
    case "$source" in
      mounts.toml|mounts.tsv|rollback-plan.tsv|rollback-mounts.tsv) ;;
      *) _agent_canon_json_error controller_projection_invalid \
           "controller projection contains an unexpected path: $source" ;;
    esac
  done
  if [[ -f "$staging/mounts.tsv" ]]; then
    local kind digest mounted_source destination mode
    while IFS=$'\t' read -r kind digest mounted_source destination mode; do
      [[ "$kind" == target && "$digest" =~ ^[A-Za-z0-9_.-]{1,128}$ &&
         "$mounted_source" = /* && -d "$mounted_source" && ! -L "$mounted_source" &&
         "$destination" == "/targets/$digest" && "$mode" == read-only ]] ||
        _agent_canon_json_error controller_projection_invalid \
          "controller target projection is invalid"
    done < "$staging/mounts.tsv"
  fi
  if [[ -f "$staging/mounts.toml" ]]; then
    grep -Fqx 'schema = "agent-canon.mount-registry.v2"' "$staging/mounts.toml" ||
      _agent_canon_json_error controller_projection_invalid \
        "controller mount registry schema is invalid"
  fi
  # Back up the complete fixed-file destination set before publishing any
  # member. The transaction is armed only after every backup is validated.
  backup_root=$(mktemp -d "$AGENT_CANON_RUNTIME_ROOT/.manifest-projection-backup.XXXXXX") ||
    _agent_canon_json_error controller_projection_publish_failed \
      "controller projection backup directory could not be created"
  chmod 700 "$backup_root"
  backup_presence=$(mktemp "$backup_root/presence.XXXXXX")
  chmod 600 "$backup_presence"
  for name in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
    target="$AGENT_CANON_STATE_ROOT/$name"
    if [[ -e "$target" || -L "$target" ]]; then
      [[ -f "$target" && ! -L "$target" ]] ||
        _agent_canon_json_error controller_projection_invalid \
          "projected controller file is not a regular file: $name"
      cp -a -- "$target" "$backup_root/$name" ||
        _agent_canon_json_error controller_projection_publish_failed \
          "controller projection backup could not be copied: $name"
      [[ -f "$backup_root/$name" &&
         "$(_agent_canon_sha256 "$target")" == "$(_agent_canon_sha256 "$backup_root/$name")" ]] ||
        _agent_canon_json_error controller_projection_publish_failed \
          "controller projection backup readback differs: $name"
      printf 'present\t%s\n' "$name" >> "$backup_presence"
    else
      printf 'absent\t%s\n' "$name" >> "$backup_presence"
    fi
  done
  [[ "$(wc -l < "$backup_presence")" == 4 ]] ||
    _agent_canon_json_error controller_projection_publish_failed \
      "controller projection backup presence readback is incomplete"
  mv -- "$backup_presence" "$backup_root/presence" ||
    _agent_canon_json_error controller_projection_publish_failed \
      "controller projection backup presence could not be published"
  backup_presence="$backup_root/presence"
  transaction_active=1
  for name in mounts.toml mounts.tsv rollback-plan.tsv rollback-mounts.tsv; do
    target="$AGENT_CANON_STATE_ROOT/$name"
    if [[ -f "$staging/$name" && ! -L "$staging/$name" ]]; then
      chmod 644 "$staging/$name"
      expected_digest=$(_agent_canon_sha256 "$staging/$name")
      mv -f -- "$staging/$name" "$target" ||
        _agent_canon_json_error controller_projection_publish_failed \
          "controller projection could not be published: $name"
      if [[ "${AGENT_CANON_TEST_CONTROLLER_PROJECTION_FAIL_AFTER:-}" == "$name" ]]; then
        _agent_canon_json_error controller_projection_publish_failed \
          "injected controller projection publish failure"
      fi
      [[ -f "$target" && ! -L "$target" ]] ||
        _agent_canon_json_error controller_projection_publish_failed \
          "controller projection readback is not a regular file: $name"
      actual_digest=$(_agent_canon_sha256 "$target")
      [[ "$actual_digest" == "$expected_digest" ]] ||
        _agent_canon_json_error controller_projection_publish_failed \
          "controller projection readback differs: $name"
    elif [[ -e "$target" || -L "$target" ]]; then
      [[ ! -L "$target" ]] ||
        _agent_canon_json_error controller_projection_publish_failed \
          "controller projection target is a symlink: $name"
      rm -f -- "$target" ||
        _agent_canon_json_error controller_projection_publish_failed \
          "stale controller projection could not be removed: $name"
      if [[ "${AGENT_CANON_TEST_CONTROLLER_PROJECTION_FAIL_AFTER:-}" == "$name" ]]; then
        _agent_canon_json_error controller_projection_publish_failed \
          "injected controller projection publish failure"
      fi
      [[ ! -e "$target" && ! -L "$target" ]] ||
        _agent_canon_json_error controller_projection_publish_failed \
          "stale controller projection remains after removal: $name"
    fi
  done
  if [[ "${AGENT_CANON_KEEP_CONTROLLER_PROJECTION_BACKUP:-0}" == 1 ]]; then
    local retained_backup="$AGENT_CANON_RUNTIME_ROOT/host-state/.controller-projection-backup"
    [[ ! -e "$retained_backup" && ! -L "$retained_backup" ]] ||
      _agent_canon_json_error controller_projection_publish_failed \
        "controller projection backup transaction already exists"
    mv -- "$backup_root" "$retained_backup" ||
      _agent_canon_json_error controller_projection_publish_failed \
        "controller projection backup could not be retained"
    backup_root="$retained_backup"
    retain_backup=1
  else
    rm -rf -- "$backup_root"
  fi
  transaction_active=0
  rm -rf -- "$staging"
)

_agent_canon_restore_controller_projection() {
  local backup_root="$AGENT_CANON_RUNTIME_ROOT/host-state/.controller-projection-backup"
  local name target backup_path restore_rc=0
  [[ -d "$backup_root" && ! -L "$backup_root" ]] || return 0
  [[ -f "$backup_root/presence" && ! -L "$backup_root/presence" ]] || return 2
  while IFS=$'\t' read -r presence name; do
    [[ "$presence" == present || "$presence" == absent ]] || { restore_rc=2; continue; }
    case "$name" in
      mounts.toml|mounts.tsv|rollback-plan.tsv|rollback-mounts.tsv) ;;
      *) restore_rc=2; continue ;;
    esac
    target="$AGENT_CANON_STATE_ROOT/$name"
    if [[ -e "$target" || -L "$target" ]]; then
      rm -f -- "$target" || restore_rc=2
    fi
    if [[ "$presence" == present ]]; then
      backup_path="$backup_root/$name"
      [[ -f "$backup_path" && ! -L "$backup_path" ]] || { restore_rc=2; continue; }
      cp -a -- "$backup_path" "$target" || restore_rc=2
    fi
  done < "$backup_root/presence"
  if ((restore_rc == 0)); then
    rm -rf -- "$backup_root" || restore_rc=2
  fi
  return "$restore_rc"
}

_agent_canon_commit_controller_projection() {
  local backup_root="$AGENT_CANON_RUNTIME_ROOT/host-state/.controller-projection-backup"
  if [[ -e "$backup_root" || -L "$backup_root" ]]; then
    [[ "${AGENT_CANON_TEST_CONTROLLER_PROJECTION_COMMIT_FAIL:-0}" != 1 ]] || return 2
    rm -rf -- "$backup_root" || return 2
    [[ ! -e "$backup_root" && ! -L "$backup_root" ]] || return 2
  fi
}

_agent_canon_prepare_clean_install() {
  # Keep a recoverable host snapshot while the volume migration and candidate
  # activation run.  Legacy files remain in place until the initializer has
  # read back the marker and every migrated controller entry.
  local path directory backup
  AGENT_CANON_CLEAN_INSTALL_PRIOR_ROLLBACK_REF=
  AGENT_CANON_CLEAN_INSTALL_PRIOR_ROLLBACK_ID=
  if [[ -f "$AGENT_CANON_STATE_ROOT/rollback-plan.tsv" &&
        ! -L "$AGENT_CANON_STATE_ROOT/rollback-plan.tsv" ]]; then
    AGENT_CANON_CLEAN_INSTALL_PRIOR_ROLLBACK_REF=$(awk -F $'\t' \
      '$1 == "image-ref" { print $2; exit }' "$AGENT_CANON_STATE_ROOT/rollback-plan.tsv")
    AGENT_CANON_CLEAN_INSTALL_PRIOR_ROLLBACK_ID=$(awk -F $'\t' \
      '$1 == "image-id" { print $2; exit }' "$AGENT_CANON_STATE_ROOT/rollback-plan.tsv")
  fi
  export AGENT_CANON_CLEAN_INSTALL_PRIOR_ROLLBACK_REF \
    AGENT_CANON_CLEAN_INSTALL_PRIOR_ROLLBACK_ID
  backup=$(mktemp -d "$AGENT_CANON_RUNTIME_ROOT/.install-reset.XXXXXX") ||
    _agent_canon_json_error install_runtime_invalid \
      "clean install state backup could not be created"
  for path in \
    "$AGENT_CANON_STATE_ROOT/state.json" \
    "$AGENT_CANON_STATE_ROOT/owner.json" \
    "$AGENT_CANON_STATE_ROOT/mounts.toml" \
    "$AGENT_CANON_STATE_ROOT/mounts.tsv" \
    "$AGENT_CANON_STATE_ROOT/rollback-plan.tsv" \
    "$AGENT_CANON_STATE_ROOT/rollback-mounts.tsv" \
    "$AGENT_CANON_STATE_ROOT/.pending-rollback-plan.tsv" \
    "$AGENT_CANON_STATE_ROOT/previous-image-id" \
    "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv"; do
    [[ ! -L "$path" ]] || {
      rm -rf -- "$backup"
      _agent_canon_json_error install_runtime_invalid \
        "clean install state file is a symlink: $path"
    }
    [[ -e "$path" ]] || continue
    [[ "$path" != "$AGENT_CANON_STATE_ROOT/mounts.toml" ||
       "${AGENT_CANON_INITIAL_MOUNTS_TOML_EXISTS:-0}" == 1 ]] || continue
    [[ "$path" != "$AGENT_CANON_STATE_ROOT/mounts.tsv" ||
       "${AGENT_CANON_INITIAL_MOUNTS_TSV_EXISTS:-0}" == 1 ]] || continue
    if [[ "$path" == "$AGENT_CANON_STATE_ROOT"/* ]]; then
      cp -a -- "$path" "$backup/$(basename -- "$path")" || {
        rm -rf -- "$backup"
        _agent_canon_json_error install_runtime_invalid \
          "clean install state file could not be backed up: $path"
      }
    else
      mkdir -p -- "$backup/host-state"
      cp -a -- "$path" "$backup/host-state/active-image.tsv" || {
        rm -rf -- "$backup"
        _agent_canon_json_error install_runtime_invalid \
          "clean install image state could not be backed up"
      }
    fi
  done
  for directory in \
    "$AGENT_CANON_STATE_ROOT/receipts" \
    "$AGENT_CANON_STATE_ROOT/generations" \
    "$AGENT_CANON_STATE_ROOT/tasks" \
    "$AGENT_CANON_STATE_ROOT/container-runtime"; do
    [[ ! -L "$directory" ]] || {
      rm -rf -- "$backup"
      _agent_canon_json_error install_runtime_invalid \
        "clean install state directory is a symlink: $directory"
    }
    mkdir -p -- "$backup/$(basename -- "$directory")"
    [[ -d "$directory" ]] || continue
    cp -a -- "$directory/." "$backup/$(basename -- "$directory")/" || {
      rm -rf -- "$backup"
      _agent_canon_json_error install_runtime_invalid \
        "clean install state directory could not be backed up: $directory"
    }
  done
  AGENT_CANON_CLEAN_INSTALL_BACKUP=$backup
  export AGENT_CANON_CLEAN_INSTALL_BACKUP
}

_agent_canon_restore_clean_install() {
  local backup=${AGENT_CANON_CLEAN_INSTALL_BACKUP:-} path directory name
  [[ -n "$backup" && -d "$backup" && ! -L "$backup" ]] || return 0
  for path in \
    "$AGENT_CANON_STATE_ROOT/state.json" \
    "$AGENT_CANON_STATE_ROOT/owner.json" \
    "$AGENT_CANON_STATE_ROOT/mounts.toml" \
    "$AGENT_CANON_STATE_ROOT/mounts.tsv" \
    "$AGENT_CANON_STATE_ROOT/rollback-plan.tsv" \
    "$AGENT_CANON_STATE_ROOT/rollback-mounts.tsv" \
    "$AGENT_CANON_STATE_ROOT/.pending-rollback-plan.tsv" \
    "$AGENT_CANON_STATE_ROOT/previous-image-id" \
    "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv"; do
    [[ ! -L "$path" ]] || return 2
    rm -f -- "$path"
  done
  for directory in \
    "$AGENT_CANON_STATE_ROOT/receipts" \
    "$AGENT_CANON_STATE_ROOT/generations" \
    "$AGENT_CANON_STATE_ROOT/tasks" \
    "$AGENT_CANON_STATE_ROOT/container-runtime"; do
    [[ ! -L "$directory" ]] || return 2
    mkdir -p -- "$directory"
    find "$directory" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    name=$(basename -- "$directory")
    cp -a -- "$backup/$name/." "$directory/" || return 2
  done
  for path in \
    "$AGENT_CANON_STATE_ROOT/state.json" \
    "$AGENT_CANON_STATE_ROOT/owner.json" \
    "$AGENT_CANON_STATE_ROOT/mounts.toml" \
    "$AGENT_CANON_STATE_ROOT/mounts.tsv" \
    "$AGENT_CANON_STATE_ROOT/rollback-plan.tsv" \
    "$AGENT_CANON_STATE_ROOT/rollback-mounts.tsv" \
    "$AGENT_CANON_STATE_ROOT/.pending-rollback-plan.tsv" \
    "$AGENT_CANON_STATE_ROOT/previous-image-id"; do
    name=$(basename -- "$path")
    [[ -e "$backup/$name" ]] || continue
    cp -a -- "$backup/$name" "$path" || return 2
  done
  if [[ -e "$backup/host-state/active-image.tsv" ]]; then
    mkdir -p -- "$AGENT_CANON_RUNTIME_ROOT/host-state"
    cp -a -- "$backup/host-state/active-image.tsv" \
      "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" || return 2
  fi
  rm -rf -- "$backup"
  unset AGENT_CANON_CLEAN_INSTALL_BACKUP
  return 0
}

_agent_canon_discard_clean_install_backup() {
  local backup=${AGENT_CANON_CLEAN_INSTALL_BACKUP:-}
  if [[ -n "$backup" ]]; then
    rm -rf -- "$backup" || return 2
    [[ ! -e "$backup" && ! -L "$backup" ]] || return 2
  fi
  unset AGENT_CANON_CLEAN_INSTALL_BACKUP
}

_agent_canon_discard_clean_install_rollback_tag() {
  local attempt_ref=${AGENT_CANON_CLEAN_INSTALL_ROLLBACK_REF:-}
  local prior_ref=${AGENT_CANON_CLEAN_INSTALL_PRIOR_ROLLBACK_REF:-}
  local prior_id=${AGENT_CANON_CLEAN_INSTALL_PRIOR_ROLLBACK_ID:-}
  local attempt_id=${AGENT_CANON_CLEAN_INSTALL_ROLLBACK_ID:-}
  [[ -n "$attempt_ref" ]] || return 0
  # If the attempt reused the prior tag for the same image, it did not change
  # the prior rollback resource. Otherwise remove only the attempt's exact
  # tag, then restore a prior alias that the attempt replaced.
  if [[ "$attempt_ref" == "$prior_ref" && "$attempt_id" == "$prior_id" ]]; then
    unset AGENT_CANON_CLEAN_INSTALL_ROLLBACK_REF AGENT_CANON_CLEAN_INSTALL_ROLLBACK_ID
    return 0
  fi
  if "$AGENT_CANON_DOCKER_CMD" image inspect "$attempt_ref" >/dev/null 2>&1; then
    "$AGENT_CANON_DOCKER_CMD" image rm "$attempt_ref" >/dev/null || return 2
  fi
  if [[ -n "$prior_ref" && -n "$prior_id" ]]; then
    if ! "$AGENT_CANON_DOCKER_CMD" tag "$prior_id" "$prior_ref" >/dev/null 2>&1; then
      return 2
    fi
  fi
  unset AGENT_CANON_CLEAN_INSTALL_ROLLBACK_REF AGENT_CANON_CLEAN_INSTALL_ROLLBACK_ID
  return 0
}

_agent_canon_restore_clean_install_resident() {
  local old_container=${AGENT_CANON_CLEAN_INSTALL_OLD_CONTAINER:-}
  local old_image_ref=${AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF:-}
  local old_image_id=${AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_ID:-}
  local restored
  [[ "${AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED:-0}" == 1 ]] || return 0
  [[ -n "$old_container" && -n "$old_image_ref" && -n "$old_image_id" ]] || return 2
  AGENT_CANON_IMAGE_REF=$old_image_ref
  AGENT_CANON_EXPECTED_IMAGE_ID=$old_image_id
  export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID
  if ! restored=$(_agent_canon_ensure_container); then
    return 2
  fi
  if ! _agent_canon_run_controller "$restored" start >/dev/null; then
    return 2
  fi
  AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED=0
  export AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED
  return 0
}

_agent_canon_clean_install_exit() {
  local rc=$?
  if [[ "${AGENT_CANON_CLEAN_INSTALL_ACTIVE:-0}" == 1 ]]; then
    if [[ "${AGENT_CANON_CLEAN_INSTALL_SUCCESS:-0}" == 1 ||
          "${AGENT_CANON_CLEAN_INSTALL_COMMITTED:-0}" == 1 ]]; then
      _agent_canon_discard_clean_install_backup || rc=2
    else
      local restore_rc=0 restore_errors=()
      _agent_canon_discard_clean_install_rollback_tag || restore_errors+=("rollback_tag_cleanup_failed")
      _agent_canon_restore_state_volume_snapshot || restore_errors+=("state_volume_restore_failed")
      _agent_canon_restore_controller_projection || restore_errors+=("controller_projection_restore_failed")
      _agent_canon_restore_global_links || restore_errors+=("global_links_restore_failed")
      _agent_canon_restore_skill_view_backup || restore_errors+=("skill_view_restore_failed")
      _agent_canon_restore_clean_install || restore_errors+=("clean_install_host_restore_failed")
      if ((${#restore_errors[@]} == 0)); then
        _agent_canon_restore_clean_install_resident || restore_errors+=("previous_resident_restore_failed")
      fi
      if ((${#restore_errors[@]})); then
        restore_rc=2
        _agent_canon_json_error rollback_failed \
          "clean install restoration failed; previous resident restart skipped: ${restore_errors[*]}"
        rc=2
      fi
    fi
  fi
  exit "$rc"
}

_agent_canon_finish_clean_install() {
  # Replacement keeps a rollback image long enough to recover a failed
  # candidate.  Once the fresh install has completed, that prior generation
  # is no longer part of install state and must not leak into the next run.
  local path rollback_plan rollback_ref rollback_tag_prefix
  rollback_plan="$AGENT_CANON_STATE_ROOT/rollback-plan.tsv"
  rollback_ref=${AGENT_CANON_CLEAN_INSTALL_ROLLBACK_REF:-}
  if [[ -z "$rollback_ref" && -f "$AGENT_CANON_STATE_ROOT/previous-image-id" &&
        ! -L "$AGENT_CANON_STATE_ROOT/previous-image-id" ]]; then
    local previous_image_id
    previous_image_id=$(<"$AGENT_CANON_STATE_ROOT/previous-image-id")
    if [[ "$previous_image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      rollback_ref="agent-canon-tools:$(_agent_canon_control_digest | cut -c1-16)-rollback-${previous_image_id#sha256:}"
    fi
  fi
  if [[ -f "$rollback_plan" && ! -L "$rollback_plan" ]]; then
    rollback_ref=${rollback_ref:-$(awk -F $'\t' '$1 == "image-ref" { print $2 }' "$rollback_plan")}
  fi
  if [[ -n "$rollback_ref" ]]; then
    # The plan owns a generated tag, not the image identity.  Never pass an
    # immutable image ID or an unrelated/foreign tag to ``image rm``: an image
    # ID can be the active candidate when Docker reused the same layers, while
    # a foreign tag is outside this install's lifecycle.
    rollback_tag_prefix="agent-canon-tools:$(_agent_canon_control_digest | cut -c1-16)-rollback-"
    if [[ "$rollback_ref" == "$rollback_tag_prefix"* ]]; then
      if "$AGENT_CANON_DOCKER_CMD" image inspect "$rollback_ref" >/dev/null 2>&1; then
        "$AGENT_CANON_DOCKER_CMD" image rm "$rollback_ref" >/dev/null ||
          _agent_canon_json_error install_runtime_invalid \
            "clean install rollback image could not be released"
      fi
    fi
  fi
  for path in \
    "$AGENT_CANON_STATE_ROOT/rollback-plan.tsv" \
    "$AGENT_CANON_STATE_ROOT/.pending-rollback-plan.tsv" \
    "$AGENT_CANON_STATE_ROOT/previous-image-id" \
    "$AGENT_CANON_STATE_ROOT/rollback-mounts.tsv"; do
    [[ ! -L "$path" ]] ||
      _agent_canon_json_error install_runtime_invalid \
        "clean install result is a symlink: $path"
    rm -f -- "$path"
  done
  unset AGENT_CANON_PENDING_ROLLBACK_PLAN AGENT_CANON_PREVIOUS_IMAGE_ID AGENT_CANON_PREVIOUS_IMAGE_REF \
    AGENT_CANON_CLEAN_INSTALL_ROLLBACK_REF AGENT_CANON_CLEAN_INSTALL_ROLLBACK_ID \
    AGENT_CANON_CLEAN_INSTALL_PRIOR_ROLLBACK_REF AGENT_CANON_CLEAN_INSTALL_PRIOR_ROLLBACK_ID \
    AGENT_CANON_CLEAN_INSTALL_OLD_CONTAINER AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF \
    AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_ID AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED
}

_agent_canon_container_exec() {
  local container=$1
  shift
  local image_id container_id source_head rollback_kind=host-mounts
  local rollback_destination=$AGENT_CANON_HOST_MOUNTS_DESTINATION
  image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect --format '{{.Id}}' "$AGENT_CANON_IMAGE_REF")
  _agent_canon_image_projection_layout "$image_id" || return $?
  if [[ "$AGENT_CANON_PROJECTION_LAYOUT" == legacy-runtime-v1 ]]; then
    rollback_kind=rollback-mounts
    rollback_destination="$AGENT_CANON_RUNTIME_DESTINATION/rollback-mounts.tsv"
  fi
  if [[ -n "${AGENT_CANON_ROLLBACK_MOUNTS_FILE:-}" ]]; then
    if [[ -f "$AGENT_CANON_ROLLBACK_MOUNTS_FILE" && ! -L "$AGENT_CANON_ROLLBACK_MOUNTS_FILE" ]]; then
      _agent_canon_volume_copy import "$rollback_kind" "$AGENT_CANON_ROLLBACK_MOUNTS_FILE"
    else
      _agent_canon_volume_copy clear "$rollback_kind" ""
    fi
  fi
  if [[ -n "${AGENT_CANON_RESTORE_TARGETS_FILE:-}" ]]; then
    if [[ -f "$AGENT_CANON_RESTORE_TARGETS_FILE" && ! -L "$AGENT_CANON_RESTORE_TARGETS_FILE" ]]; then
      _agent_canon_volume_copy import "$rollback_kind" "$AGENT_CANON_RESTORE_TARGETS_FILE"
    else
      _agent_canon_volume_copy clear "$rollback_kind" ""
    fi
  fi
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
    extra_env+=(--env "AGENT_CANON_RESTORE_TARGETS_FILE=$rollback_destination")
  [[ -n "${AGENT_CANON_ROLLBACK_MOUNTS_FILE:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_ROLLBACK_MOUNTS_FILE=$rollback_destination")
  [[ -n "${AGENT_CANON_REPOSITORY_ROOT:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_HOST_INSTALL_ROOT=$AGENT_CANON_REPOSITORY_ROOT")
  [[ -n "${AGENT_CANON_TARGET_HOST_ROOT:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_TARGET_HOST_ROOT=$AGENT_CANON_TARGET_HOST_ROOT")
  [[ -n "${AGENT_CANON_TARGET_CONTAINER_ROOT:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_TARGET_CONTAINER_ROOT=$AGENT_CANON_TARGET_CONTAINER_ROOT")
  [[ -n "${AGENT_CANON_TARGET_DIGEST:-}" ]] &&
    extra_env+=(--env "AGENT_CANON_TARGET_DIGEST=$AGENT_CANON_TARGET_DIGEST")
  extra_env+=(--env "AGENT_CANON_PRIVATE_LOG_ROOT=$AGENT_CANON_PRIVATE_LOG_DESTINATION")
  if [[ "$AGENT_CANON_PROJECTION_LAYOUT" == legacy-runtime-v1 ]]; then
    extra_env+=(--env "AGENT_CANON_EXCHANGE_ROOT=$AGENT_CANON_RUNTIME_DESTINATION")
  else
    extra_env+=(--env "AGENT_CANON_EXCHANGE_ROOT=$AGENT_CANON_EXCHANGE_DESTINATION")
  fi
  extra_env+=(--env "AGENT_CANON_PROJECTION_LAYOUT=$AGENT_CANON_PROJECTION_LAYOUT")
  extra_env+=(--env "AGENT_CANON_HOST_SPOOL_ROOT=$AGENT_CANON_SPOOL_DESTINATION")
  extra_env+=(--env "AGENT_CANON_HOST_ARCHIVE_ROOT=$AGENT_CANON_ARCHIVE_DESTINATION")
  extra_env+=(--env "AGENT_CANON_HOST_CACHE_ROOT=$AGENT_CANON_CACHE_DESTINATION")
  extra_env+=(--env "AGENT_CANON_HOST_CODEX_HOME_ROOT=$AGENT_CANON_CODEX_HOME_DESTINATION")
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
      service_text=$(<"$AGENT_CANON_REPOSITORY_ROOT/bootstrap/host/scheduler/systemd/user/agent-canon-sync.service.in")
      timer_text=$(<"$AGENT_CANON_REPOSITORY_ROOT/bootstrap/host/scheduler/systemd/user/agent-canon-sync.timer.in")
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

_agent_canon_image_reference() {
  local requested_ref=${1:-}
  if [[ -n "$requested_ref" ]]; then
    AGENT_CANON_IMAGE_REF=$requested_ref
    export AGENT_CANON_IMAGE_REF
    return 0
  fi
  local source_head manifest_digest control_digest
  if ! source_head=$(git -C "$AGENT_CANON_REPOSITORY_ROOT" rev-parse --verify HEAD); then
    _agent_canon_json_error source_snapshot_failed "AgentCanon source is not a Git checkout"
    return 2
  fi
  manifest_digest=$(_agent_canon_sha256 "$AGENT_CANON_REPOSITORY_ROOT/bootstrap/host/manifest.toml")
  control_digest=$(_agent_canon_control_digest)
  AGENT_CANON_IMAGE_REF="agent-canon-tools:${control_digest:0:16}-${manifest_digest:0:16}-${source_head:0:16}"
  export AGENT_CANON_IMAGE_REF
}

_agent_canon_image() {
  local requested_ref=${1:-}
  _agent_canon_image_reference "$requested_ref"
  if [[ -n "$requested_ref" ]]; then
    if ! "$AGENT_CANON_DOCKER_CMD" pull "$AGENT_CANON_IMAGE_REF"; then
      _agent_canon_json_error candidate_image_build_failed "candidate image could not be pulled"
      return 2
    fi
    return 0
  fi
  local control_digest source_head
  if ! source_head=$(git -C "$AGENT_CANON_REPOSITORY_ROOT" rev-parse --verify HEAD); then
    _agent_canon_json_error source_snapshot_failed "AgentCanon source is not a Git checkout"
    return 2
  fi
  control_digest=$(_agent_canon_control_digest)
  if "$AGENT_CANON_DOCKER_CMD" image inspect "$AGENT_CANON_IMAGE_REF" >/dev/null 2>&1 &&
     [[ "${AGENT_CANON_FORCE_BUILD:-0}" != 1 ]]; then
    return 0
  fi
  if [[ "${AGENT_CANON_ALLOW_BUILD:-0}" != 1 ]]; then
    _agent_canon_json_error image_missing "AgentCanon tool image is not installed"
    return 2
  fi
  if [[ "${AGENT_CANON_FORCE_BUILD:-0}" == 1 ]] || \
     ! "$AGENT_CANON_DOCKER_CMD" image inspect "$AGENT_CANON_IMAGE_REF" >/dev/null 2>&1; then
    if ! "$AGENT_CANON_DOCKER_CMD" build \
      --file "$AGENT_CANON_REPOSITORY_ROOT/bootstrap/container/image/Dockerfile" \
      --tag "$AGENT_CANON_IMAGE_REF" \
      --label io.agent-canon.runtime=shared-v1 \
      --label "io.agent-canon.control-root-digest=$control_digest" \
      --label "io.agent-canon.source-revision=$source_head" \
      --label io.agent-canon.projection-layout=container-runtime-v1 \
      "$AGENT_CANON_REPOSITORY_ROOT"; then
      _agent_canon_json_error candidate_image_build_failed "candidate image build failed"
      return 2
    fi
  fi
}

_agent_canon_image_projection_layout() {
  local image_id=${1:-} capability
  [[ -n "$image_id" ]] || {
    _agent_canon_json_error image_capability_unavailable \
      "resident image identity is unavailable for projection routing"
    return 2
  }
  if ! capability=$(
    "$AGENT_CANON_DOCKER_CMD" image inspect \
      --format '{{index .Config.Labels "io.agent-canon.projection-layout"}}' \
      "$image_id" 2>/dev/null
  ); then
    _agent_canon_json_error image_capability_unavailable \
      "resident image projection capability could not be inspected"
    return 2
  fi
  case "$capability" in
    container-runtime-v1)
      AGENT_CANON_PROJECTION_LAYOUT=container-runtime-v1
      ;;
    "")
      # Released main-era images predate the capability label and write their
      # controller projection directly below /var/lib/agent-canon/runtime.
      AGENT_CANON_PROJECTION_LAYOUT=legacy-runtime-v1
      ;;
    *)
      _agent_canon_json_error image_capability_unknown \
        "resident image declares an unsupported projection capability"
      return 2
      ;;
  esac
  export AGENT_CANON_PROJECTION_LAYOUT
}

_agent_canon_ensure_projection_layout() {
  [[ -n "${AGENT_CANON_PROJECTION_LAYOUT:-}" ]] && return 0
  local image_id
  if image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
    --format '{{.Id}}' "${AGENT_CANON_IMAGE_REF:-}" 2>/dev/null) &&
     [[ -n "$image_id" ]]; then
    _agent_canon_image_projection_layout "$image_id"
    return $?
  fi
  # Standalone copy helpers used by recovery tests can operate on a mounted
  # volume without an image record. The full resident execution path performs
  # strict immutable-image capability inspection before reaching this helper.
  AGENT_CANON_PROJECTION_LAYOUT=container-runtime-v1
  export AGENT_CANON_PROJECTION_LAYOUT
}

_agent_canon_write_active_image() {
  local image_ref=$1 image_id=$2
  if [[ ! "$image_ref" =~ ^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,255}$ ||
        ! "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    _agent_canon_json_error active_image_invalid "active image identity is invalid"
    return 2
  fi
  local path="$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" temporary
  if ! temporary=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/host-state/.active-image.XXXXXX"); then
    _agent_canon_json_error active_image_write_failed "active image state temporary file could not be created"
    return 2
  fi
  if ! {
    printf 'schema\tagent-canon.active-image.v1\n'
    printf 'image-ref\t%s\n' "$image_ref"
    printf 'image-id\t%s\n' "$image_id"
  } > "$temporary"; then
    rm -f -- "$temporary"
    _agent_canon_json_error active_image_write_failed "active image state could not be written"
    return 2
  fi
  if ! chmod 600 "$temporary" || ! mv -f -- "$temporary" "$path"; then
    rm -f -- "$temporary"
    _agent_canon_json_error active_image_write_failed "active image state could not be published"
    return 2
  fi
  AGENT_CANON_IMAGE_REF=$image_ref
  AGENT_CANON_ACTIVE_IMAGE_ID=$image_id
  AGENT_CANON_EXPECTED_IMAGE_ID=$image_id
  export AGENT_CANON_IMAGE_REF AGENT_CANON_ACTIVE_IMAGE_ID AGENT_CANON_EXPECTED_IMAGE_ID
}

_agent_canon_read_active_image() {
  local path="$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv"
  if [[ ! -f "$path" || -L "$path" ]]; then
    _agent_canon_json_error active_image_missing "active resident image state is missing"
    return 2
  fi
  local key value schema= image_ref= image_id=
  local schema_count=0 ref_count=0 id_count=0
  while IFS=$'\t' read -r key value; do
    if [[ -z "$key" || -z "$value" || "$value" == *$'\t'* ||
          "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
      _agent_canon_json_error active_image_invalid "active image state contains an invalid row"
      return 2
    fi
    case "$key" in
      schema) schema=$value; schema_count=$((schema_count + 1)) ;;
      image-ref) image_ref=$value; ref_count=$((ref_count + 1)) ;;
      image-id) image_id=$value; id_count=$((id_count + 1)) ;;
      *)
        _agent_canon_json_error active_image_invalid "active image state contains an unknown key: $key"
        return 2
        ;;
    esac
  done < "$path"
  if [[ "$schema_count" -ne 1 || "$schema" != agent-canon.active-image.v1 ||
        "$ref_count" -ne 1 || "$id_count" -ne 1 ]]; then
    _agent_canon_json_error active_image_invalid "active image state fields are incomplete"
    return 2
  fi
  if [[ ! "$image_ref" =~ ^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,255}$ ||
        ! "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    _agent_canon_json_error active_image_invalid "active image identity is invalid"
    return 2
  fi
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
    return 2
  fi
  if ! image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
    --format '{{.Id}}' "$image_ref" 2>/dev/null); then
    _agent_canon_json_error active_image_migration_failed "resident image ID readback failed"
    return 2
  fi
  AGENT_CANON_IMAGE_REF=$image_ref
  AGENT_CANON_EXPECTED_IMAGE_ID=$image_id
  export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID
  # Ownership is the migration gate. Configuration drift is repairable by the
  # caller and must not prevent it from learning the old image identity for
  # the replacement transaction.
  _agent_canon_classify_existing_container "$container"
  _agent_canon_write_active_image "$image_ref" "$image_id"
}

_agent_canon_record_active_container() {
  local container=$1 image_ref image_id
  if ! image_ref=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.Config.Image}}' "$container" 2>/dev/null); then
    _agent_canon_json_error active_image_readback_failed "resident image reference readback failed"
    return 2
  fi
  if ! image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
    --format '{{.Id}}' "$image_ref" 2>/dev/null); then
    _agent_canon_json_error active_image_readback_failed "resident image ID readback failed"
    return 2
  fi
  _agent_canon_write_active_image "$image_ref" "$image_id"
}

_agent_canon_read_container_identity() {
  local container=$1 error_code=${2:-container_ownership_mismatch}
  local observed_id observed_runtime observed_control
  if ! observed_id=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.Id}}' "$container" 2>/dev/null); then
    _agent_canon_json_error "$error_code" \
      "named resident container identity could not be read"
    return 2
  fi
  if ! observed_runtime=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{index .Config.Labels "io.agent-canon.runtime"}}' "$container" 2>/dev/null); then
    _agent_canon_json_error "$error_code" \
      "named resident ownership labels could not be read"
    return 2
  fi
  if ! observed_control=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{index .Config.Labels "io.agent-canon.control-root-digest"}}' "$container" 2>/dev/null); then
    _agent_canon_json_error "$error_code" \
      "named resident control-root ownership could not be read"
    return 2
  fi
  if [[ -z "$observed_id" ]]; then
    _agent_canon_json_error "$error_code" \
      "named resident container identity is empty"
    return 2
  fi
  AGENT_CANON_OBSERVED_CONTAINER_ID=$observed_id
  AGENT_CANON_OBSERVED_CONTAINER_RUNTIME=$observed_runtime
  AGENT_CANON_OBSERVED_CONTAINER_CONTROL=$observed_control
}

_agent_canon_classify_existing_container() {
  local container=$1
  _agent_canon_read_container_identity "$container"
  if [[ "$AGENT_CANON_OBSERVED_CONTAINER_RUNTIME" != shared-v1 ||
        "$AGENT_CANON_OBSERVED_CONTAINER_CONTROL" != "$(_agent_canon_control_digest)" ]]; then
    _agent_canon_json_error container_ownership_mismatch \
      "named resident is not owned by this AgentCanon control root"
    return 2
  fi
}

_agent_canon_require_existing_container_identity() {
  local container=$1 expected_id=$2 expected_runtime=$3 expected_control=$4
  _agent_canon_read_container_identity "$container" replacement_readback_failed
  if [[ "$AGENT_CANON_OBSERVED_CONTAINER_ID" != "$expected_id" ||
        "$AGENT_CANON_OBSERVED_CONTAINER_RUNTIME" != "$expected_runtime" ||
        "$AGENT_CANON_OBSERVED_CONTAINER_CONTROL" != "$expected_control" ]]; then
    _agent_canon_json_error replacement_readback_failed \
      "named resident identity changed before teardown"
    return 2
  fi
}

_agent_canon_validate_target_manifest() {
  local manifest=${1:-$AGENT_CANON_STATE_ROOT/mounts.tsv}
  if [[ ! -f "$manifest" || -L "$manifest" ]]; then
    _agent_canon_json_error mount_manifest_invalid \
      "target mount manifest is unavailable before resident replacement"
    return 2
  fi
  local kind digest source destination mode
  while IFS=$'\t' read -r kind digest source destination mode; do
    [[ -z "$kind" ]] && continue
    if [[ "$kind" != target || ! "$digest" =~ ^[A-Za-z0-9_.-]{1,128}$ ||
          "$source" != /* || "$destination" != "/targets/$digest" ||
          "$mode" != read-only ]]; then
      _agent_canon_json_error mount_manifest_invalid \
        "target mount manifest is invalid before resident replacement"
      return 2
    fi
    if [[ "$source" == "$AGENT_CANON_CONTROL_ROOT" ||
          "$source" == "$(realpath -e -- "$HOME")" ]]; then
      _agent_canon_json_error mount_manifest_invalid \
        "broad control or home mount is forbidden"
      return 2
    fi
    if [[ ! -d "$source" || -L "$source" ]]; then
      _agent_canon_json_error target_root_invalid \
        "target root does not exist: $source"
      return 2
    fi
  done < "$manifest"
}

_agent_canon_write_rollback_plan() {
  local image_id=$1 image_ref=$2 plan=${3:-$AGENT_CANON_STATE_ROOT/rollback-plan.tsv}
  if [[ "$image_id" != sha256:* || -z "$image_ref" || "$plan" != /* || "$plan" == *$'\n'* ]]; then
    _agent_canon_json_error rollback_plan_invalid "previous image identity or plan path is invalid"
    return 2
  fi
  if [[ -L "$plan" ]]; then
    _agent_canon_json_error rollback_plan_invalid "rollback plan path is a symlink"
    return 2
  fi
  local rollback_ref="agent-canon-tools:$(_agent_canon_control_digest | cut -c1-16)-rollback-${image_id#sha256:}"
  rollback_ref=${rollback_ref:0:128}
  local prior_rollback_id= temporary
  prior_rollback_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
    --format '{{.Id}}' "$rollback_ref" 2>/dev/null || true)
  if ! "$AGENT_CANON_DOCKER_CMD" tag "$image_id" "$rollback_ref"; then
    _agent_canon_json_error rollback_plan_invalid "previous image could not be retained under rollback tag"
    return 2
  fi
  local retained_id
  if ! retained_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
    --format '{{.Id}}' "$rollback_ref" 2>/dev/null) || [[ "$retained_id" != "$image_id" ]]; then
    if [[ -n "$prior_rollback_id" ]]; then
      "$AGENT_CANON_DOCKER_CMD" tag "$prior_rollback_id" "$rollback_ref" >/dev/null 2>&1 || :
    else
      "$AGENT_CANON_DOCKER_CMD" image rm "$rollback_ref" >/dev/null 2>&1 || :
    fi
    _agent_canon_json_error rollback_plan_invalid "retained previous image could not be read back"
    return 2
  fi
  temporary=$(mktemp "${plan}.XXXXXX") || {
    if [[ -n "$prior_rollback_id" ]]; then
      "$AGENT_CANON_DOCKER_CMD" tag "$prior_rollback_id" "$rollback_ref" >/dev/null 2>&1 || :
    else
      "$AGENT_CANON_DOCKER_CMD" image rm "$rollback_ref" >/dev/null 2>&1 || :
    fi
    _agent_canon_json_error rollback_plan_invalid "rollback plan temporary file could not be created"
    return 2
  }
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
        if [[ "$kind" != target || "$destination" != "/targets/$digest" || "$mode" != read-only ]]; then
          rm -f -- "$temporary"
          if [[ -n "$prior_rollback_id" ]]; then
            "$AGENT_CANON_DOCKER_CMD" tag "$prior_rollback_id" "$rollback_ref" >/dev/null 2>&1 || :
          else
            "$AGENT_CANON_DOCKER_CMD" image rm "$rollback_ref" >/dev/null 2>&1 || :
          fi
          _agent_canon_json_error rollback_plan_invalid "target mount manifest is invalid"
          return 2
        fi
        printf 'mount\tmount\t%s\t%s\ttrue\n' "$source" "$destination"
      done < "$AGENT_CANON_STATE_ROOT/mounts.tsv"
    fi
  } > "$temporary" || {
    rm -f -- "$temporary"
    if [[ -n "$prior_rollback_id" ]]; then
      "$AGENT_CANON_DOCKER_CMD" tag "$prior_rollback_id" "$rollback_ref" >/dev/null 2>&1 || :
    else
      "$AGENT_CANON_DOCKER_CMD" image rm "$rollback_ref" >/dev/null 2>&1 || :
    fi
    _agent_canon_json_error rollback_plan_invalid "rollback plan could not be written"
    return 2
  }
  if ! chmod 600 -- "$temporary" || ! mv -f -- "$temporary" "$plan"; then
    rm -f -- "$temporary"
    if [[ -n "$prior_rollback_id" ]]; then
      "$AGENT_CANON_DOCKER_CMD" tag "$prior_rollback_id" "$rollback_ref" >/dev/null 2>&1 || :
    else
      "$AGENT_CANON_DOCKER_CMD" image rm "$rollback_ref" >/dev/null 2>&1 || :
    fi
    _agent_canon_json_error rollback_plan_invalid "rollback plan could not be published"
    return 2
  fi
  return 0
}

_agent_canon_read_rollback_plan() {
  local plan="$AGENT_CANON_STATE_ROOT/rollback-plan.tsv"
  [[ -f "$plan" && ! -L "$plan" ]] ||
    _agent_canon_json_error rollback_unavailable "rollback plan is missing"
  local key value source destination ro
  local schema_seen=0 image_seen=0 ref_seen=0
  local previous_mounts=${1:-"$AGENT_CANON_STATE_ROOT/rollback-mounts.tsv"}
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
           ( -d "$source" ||
             ("$destination" == "$AGENT_CANON_SOURCE_SYNC_DESTINATION" && -f "$source") ||
             ("$destination" == "$AGENT_CANON_MOUNT_REGISTRY_DESTINATION" && -f "$source") ) &&
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
  local state_volume="${AGENT_CANON_STATE_VOLUME_NAME:-agent-canon-runtime-$(_agent_canon_control_digest)}"
  local mount_manifest=${2:-${AGENT_CANON_ROLLBACK_MOUNTS_FILE:-$AGENT_CANON_STATE_ROOT/mounts.tsv}}
  local include_pending=${3:-1}
  local observed_runtime observed_control observed_image observed_image_id observed_network observed_user
  local observed_rootfs observed_capdrop observed_security observed_cpus
  local observed_memory observed_pids observed_mounts expected_mounts mount_manifest
  local require_source_sync=${4:-1}
  if ! observed_runtime=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{index .Config.Labels "io.agent-canon.runtime"}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident container inspect failed"
    return 2
  fi
  if ! observed_control=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{index .Config.Labels "io.agent-canon.control-root-digest"}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident ownership readback failed"
    return 2
  fi
  if ! observed_user=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.Config.User}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident caller identity readback failed"
    return 2
  fi
  if ! observed_image=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.Config.Image}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident image readback failed"
    return 2
  fi
  if ! observed_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
    --format '{{.Id}}' "$observed_image"); then
    _agent_canon_json_error container_ownership_mismatch "resident image ID readback failed"
    return 2
  fi
  if ! observed_network=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.HostConfig.NetworkMode}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident network readback failed"
    return 2
  fi
  if ! observed_rootfs=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.HostConfig.ReadonlyRootfs}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident rootfs readback failed"
    return 2
  fi
  if ! observed_capdrop=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{join .HostConfig.CapDrop ","}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident capability readback failed"
    return 2
  fi
  if ! observed_security=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{join .HostConfig.SecurityOpt ","}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident security readback failed"
    return 2
  fi
  if ! observed_cpus=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.HostConfig.NanoCpus}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident CPU readback failed"
    return 2
  fi
  if ! observed_memory=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.HostConfig.Memory}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident memory readback failed"
    return 2
  fi
  if ! observed_pids=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.HostConfig.PidsLimit}}' "$container"); then
    _agent_canon_json_error container_ownership_mismatch "resident PID readback failed"
    return 2
  fi
  if [[ "$observed_runtime" != shared-v1 ||
        "$observed_control" != "$(_agent_canon_control_digest)" ||
        ("$observed_image" != "$AGENT_CANON_IMAGE_REF" &&
         "$observed_image" != "${AGENT_CANON_EXPECTED_IMAGE_ID:-}") ||
        ( -n "${AGENT_CANON_EXPECTED_IMAGE_ID:-}" && "$observed_image_id" != "$AGENT_CANON_EXPECTED_IMAGE_ID" ) ||
        "$observed_network" != "$AGENT_CANON_CONTAINER_NETWORK" ||
        "$observed_rootfs" != true ||
        "$observed_capdrop" != ALL ||
        "$observed_security" != no-new-privileges ||
        "$observed_cpus" != 2000000000 ||
        "$observed_memory" != 4294967296 ||
        "$observed_pids" != 512 ||
        "$observed_user" != "$(_agent_canon_caller_user)" ]]; then
    _agent_canon_json_error container_ownership_mismatch "named resident has unexpected owner, image, mount, or security configuration"
    return 2
  fi
  if ! expected_mounts=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.expected-mounts.XXXXXX") ||
     ! observed_mounts=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.observed-mounts.XXXXXX"); then
    rm -f -- "${expected_mounts:-}" "${observed_mounts:-}"
    _agent_canon_json_error mount_readback_failed "resident mount readback files could not be created"
    return 2
  fi
  printf 'volume:%s\t%s\ttrue\n' "$state_volume" "$AGENT_CANON_VOLUME_DESTINATION" > "$expected_mounts"
  if [[ -f "$mount_manifest" && ! -L "$mount_manifest" ]]; then
    local kind digest source destination mode
    while IFS=$'\t' read -r kind digest source destination mode; do
      [[ -z "$kind" ]] && continue
      if [[ "$kind" != target || ! "$digest" =~ ^[A-Za-z0-9_.-]{1,128}$ ||
            "$source" != /* || ! -d "$source" || -L "$source" ||
            "$destination" != "/targets/$digest" || "$mode" != read-only ]]; then
        rm -f -- "$expected_mounts" "$observed_mounts"
        _agent_canon_json_error mount_manifest_invalid "target mount manifest is invalid during readback"
        return 2
      fi
      printf '%s\t%s\tfalse\n' "$source" "$destination" >> "$expected_mounts"
    done < "$mount_manifest"
  fi
  if [[ "$include_pending" == 1 && -n "${AGENT_CANON_TARGET_PENDING_SOURCE:-}" ]]; then
    printf '%s\t%s\tfalse\n' "$AGENT_CANON_TARGET_PENDING_SOURCE" \
      "/targets/$AGENT_CANON_TARGET_PENDING_DIGEST" >> "$expected_mounts"
  fi
  "$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{range .Mounts}}{{if eq .Type "volume"}}{{printf "volume:%s\t%s\t%t\n" .Name .Destination .RW}}{{else}}{{printf "%s\t%s\t%t\n" .Source .Destination .RW}}{{end}}{{end}}' \
    "$container" | sed '/^$/d' | sort > "$observed_mounts"
  if [[ "$require_source_sync" == 0 ]]; then
    local filtered_mounts
    filtered_mounts=$(mktemp "$AGENT_CANON_RUNTIME_ROOT/.observed-mounts-filtered.XXXXXX")
    if ! awk -F $'\t' -v destination="$AGENT_CANON_SOURCE_SYNC_DESTINATION" \
      '$2 != destination' "$observed_mounts" > "$filtered_mounts"; then
      rm -f -- "$expected_mounts" "$observed_mounts" "$filtered_mounts"
      _agent_canon_json_error mount_readback_failed "resident mount readback filtering failed"
      return 2
    fi
    mv -- "$filtered_mounts" "$observed_mounts"
  fi
  sort -o "$expected_mounts" "$expected_mounts"
  if ! diff -u "$expected_mounts" "$observed_mounts" >/dev/null; then
    rm -f -- "$expected_mounts" "$observed_mounts"
    _agent_canon_json_error container_ownership_mismatch "resident bind mount set differs from the expected complete manifest"
    return 2
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
  local candidate_container_id= candidate_container_ref="$container"
  local candidate_image_id=${AGENT_CANON_EXPECTED_IMAGE_ID:-}
  AGENT_CANON_CANDIDATE_CONTAINER_CREATED_HERE=0
  export AGENT_CANON_CANDIDATE_CONTAINER_CREATED_HERE
  AGENT_CANON_STATE_VOLUME_NAME="${AGENT_CANON_STATE_VOLUME_NAME:-agent-canon-runtime-$(_agent_canon_control_digest)}"
  export AGENT_CANON_STATE_VOLUME_NAME
  _agent_canon_finish_committed_activation_cleanup || return $?
  local -a target_mount_args=()
  local target_source target_digest target_destination target_mode
  local target_manifest="${AGENT_CANON_ROLLBACK_MOUNTS_FILE:-$AGENT_CANON_STATE_ROOT/mounts.tsv}"
  local candidate_receipt="${AGENT_CANON_CANDIDATE_IDENTITY_RECEIPT:-$AGENT_CANON_RUNTIME_ROOT/host-state/candidate-container.tsv}"
  local receipt_container_id= receipt_name_id=
  if [[ -e "$candidate_receipt" || -L "$candidate_receipt" ]]; then
    if ! _agent_canon_read_candidate_identity_receipt "$container"; then
      _agent_canon_json_error candidate_ensure_failed \
        "resident container identity receipt is invalid"
      return 2
    fi
    receipt_container_id=$AGENT_CANON_CANDIDATE_CONTAINER_ID
    if ! "$AGENT_CANON_DOCKER_CMD" container inspect "$receipt_container_id" >/dev/null 2>&1; then
      # A receipt is stale only when both its immutable ID and the mutable name
      # are absent.  If the name is present, it may be a replacement and is
      # never adopted or removed through the stale receipt.
      if "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
        _agent_canon_json_error candidate_ensure_failed \
          "resident name is occupied after the recorded candidate disappeared"
        return 2
      fi
      if ! _agent_canon_clear_candidate_identity_receipt; then
        _agent_canon_json_error candidate_ensure_failed \
          "stale resident container identity receipt could not be cleared"
        return 2
      fi
      receipt_container_id=
    elif ! receipt_name_id=$("$AGENT_CANON_DOCKER_CMD" container inspect \
      --format '{{.Id}}' "$container" 2>/dev/null) ||
      [[ "$receipt_name_id" != "$receipt_container_id" ]]; then
      _agent_canon_json_error candidate_ensure_failed \
        "recorded candidate is not reachable through its expected name"
      return 2
    fi
  fi
  while IFS=$'\t' read -r target_kind target_digest target_source target_destination target_mode; do
    [[ -n "$target_kind" ]] || continue
    if [[ "$target_kind" != target ||
          ! "$target_digest" =~ ^[A-Za-z0-9_.-]{1,128}$ ]]; then
      _agent_canon_json_error mount_manifest_invalid "invalid target mount record"
      return 2
    fi
    if [[ "$target_source" != /* || ! -d "$target_source" || -L "$target_source" ]]; then
      _agent_canon_json_error mount_manifest_invalid "target mount source is not a regular directory"
      return 2
    fi
    if [[ "$target_source" == "$AGENT_CANON_CONTROL_ROOT" ||
          "$target_source" == "$(realpath -e -- "$HOME")" ]]; then
      _agent_canon_json_error mount_manifest_invalid "broad control or home mount is forbidden"
      return 2
    fi
    if [[ "$target_destination" != "/targets/$target_digest" ||
          "$target_mode" != read-only ]]; then
      _agent_canon_json_error mount_manifest_invalid "target mount destination or mode is invalid"
      return 2
    fi
    target_mount_args+=(--mount "type=bind,src=$target_source,dst=$target_destination,readonly")
  done < "$target_manifest"
  if [[ -n "${AGENT_CANON_TARGET_PENDING_SOURCE:-}" ]]; then
    target_mount_args+=(
      --mount "type=bind,src=$AGENT_CANON_TARGET_PENDING_SOURCE,dst=/targets/$AGENT_CANON_TARGET_PENDING_DIGEST,readonly"
    )
  fi
  if "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
    if ! candidate_container_id=$("$AGENT_CANON_DOCKER_CMD" container inspect \
      --format '{{.Id}}' "$container" 2>/dev/null) || [[ -z "$candidate_container_id" ]]; then
      _agent_canon_json_error candidate_ensure_failed \
        "resident container identity could not be read back"
      return 2
    fi
    if [[ -n "$receipt_container_id" &&
          "$candidate_container_id" != "$receipt_container_id" ]]; then
      _agent_canon_json_error candidate_ensure_failed \
        "resident name no longer identifies the recorded candidate"
      return 2
    fi
    candidate_container_ref=$candidate_container_id
    if ! _agent_canon_state_volume_labels_match "$AGENT_CANON_STATE_VOLUME_NAME"; then
      _agent_canon_json_error state_volume_ownership_mismatch \
        "resident controller state volume has unexpected identity or owner"
      return 2
    fi
    if ! _agent_canon_probe_state_volume "$AGENT_CANON_STATE_VOLUME_NAME" 1; then
      _agent_canon_json_error state_volume_access_failed \
        "the resident caller could not access the controller state volume"
      return 2
    fi
    if _agent_canon_import_host_inputs; then
      :
    else
      local host_input_rc=$?
      _agent_canon_json_error state_volume_import_failed \
        "host-authored state could not be imported into the controller volume"
      return "$host_input_rc"
    fi
    if ! _agent_canon_probe_state_volume "$AGENT_CANON_STATE_VOLUME_NAME"; then
      _agent_canon_json_error state_volume_access_failed \
        "the resident caller could not access the normalized controller state volume"
      return 2
    fi
    _agent_canon_validate_existing_container "$candidate_container_id"
    local validate_rc=$?
    ((validate_rc == 0)) || return "$validate_rc"
  else
    local caller_user
    caller_user=$(_agent_canon_caller_user)
    if _agent_canon_init_state_volume; then
      :
    else
      local state_volume_rc=$?
      return "$state_volume_rc"
    fi
    if _agent_canon_import_host_inputs; then
      :
    else
      local host_input_rc=$?
      _agent_canon_remove_fresh_state_volume || :
      return "$host_input_rc"
    fi
    if ! _agent_canon_probe_state_volume "$AGENT_CANON_STATE_VOLUME_NAME"; then
      _agent_canon_json_error state_volume_access_failed \
        "the resident caller could not access the normalized controller state volume"
      _agent_canon_remove_fresh_state_volume || :
      return 2
    fi
    if [[ -z "$candidate_image_id" ]]; then
      if ! candidate_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
        --format '{{.Id}}' "$AGENT_CANON_IMAGE_REF" 2>/dev/null); then
        _agent_canon_json_error candidate_ensure_failed \
          "resident image identity could not be read back"
        _agent_canon_remove_fresh_state_volume || :
        return 2
      fi
    fi
    if ! candidate_container_id=$("$AGENT_CANON_DOCKER_CMD" create \
      --name "$container" \
      --user "$caller_user" \
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
      --mount "type=volume,src=$AGENT_CANON_STATE_VOLUME_NAME,dst=$AGENT_CANON_VOLUME_DESTINATION" \
      "${target_mount_args[@]}" \
      "$AGENT_CANON_IMAGE_REF"); then
      _agent_canon_json_error candidate_ensure_failed "resident container could not be created"
      _agent_canon_remove_fresh_candidate_resources ||
        _agent_canon_json_error rollback_failed \
          "fresh resident resources could not be removed after create failure"
      return 2
    fi
    candidate_container_ref=$candidate_container_id
    AGENT_CANON_CANDIDATE_CONTAINER_CREATED_HERE=1
    export AGENT_CANON_CANDIDATE_CONTAINER_CREATED_HERE
    # Persist immutable identity immediately after create.  Callers normally
    # capture this function with command substitution, so exported variables
    # cannot bridge a later failure back to the parent shell.
    _agent_canon_write_candidate_identity_receipt "$container" "$candidate_container_id" \
      "$AGENT_CANON_IMAGE_REF" "$candidate_image_id" || {
      _agent_canon_json_error candidate_ensure_failed \
        "resident container identity receipt could not be recorded"
      _agent_canon_remove_fresh_candidate_resources "$candidate_container_id" || :
      return 2
    }
    _agent_canon_validate_existing_container "$candidate_container_id"
    local validate_rc=$?
    if ((validate_rc != 0)); then
      _agent_canon_remove_fresh_candidate_resources "$candidate_container_id" ||
        _agent_canon_json_error rollback_failed \
          "fresh resident resources could not be removed after readback failure"
      return "$validate_rc"
    fi
  fi
  if [[ -z "$candidate_image_id" ]]; then
    if ! candidate_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
      --format '{{.Id}}' "$AGENT_CANON_IMAGE_REF" 2>/dev/null); then
      _agent_canon_json_error candidate_ensure_failed \
        "resident image identity could not be read back"
      _agent_canon_remove_fresh_candidate_resources "$candidate_container_id" || :
      return 2
    fi
  fi
  _agent_canon_write_candidate_identity_receipt "$container" "$candidate_container_id" \
    "$AGENT_CANON_IMAGE_REF" "$candidate_image_id" || {
    _agent_canon_json_error candidate_ensure_failed \
      "resident container identity receipt could not be recorded"
    _agent_canon_remove_fresh_candidate_resources "$candidate_container_id" || :
    return 2
  }
  local running
  running=$("$AGENT_CANON_DOCKER_CMD" container inspect \
    --format '{{.State.Running}}' "$candidate_container_ref" 2>/dev/null || printf false)
  if [[ "$running" != true ]]; then
    if ! "$AGENT_CANON_DOCKER_CMD" start "$candidate_container_ref" >/dev/null; then
      _agent_canon_json_error candidate_ensure_failed "resident container could not be started"
      _agent_canon_remove_fresh_candidate_resources "$candidate_container_id" ||
        _agent_canon_json_error rollback_failed \
          "fresh resident resources could not be removed after start failure"
      return 2
    fi
  fi
  local attempts=0 health
  while ((attempts < AGENT_CANON_HEALTH_ATTEMPTS)); do
    health=$("$AGENT_CANON_DOCKER_CMD" container inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}starting{{end}}' \
      "$candidate_container_ref" 2>/dev/null || printf missing)
    if [[ "$health" == healthy ]]; then
      printf '%s\n' "$container"
      return 0
    fi
    if [[ "$health" == missing ]]; then
      _agent_canon_json_error runtime_unavailable "resident container disappeared"
      _agent_canon_remove_fresh_candidate_resources "$candidate_container_id" ||
        _agent_canon_json_error rollback_failed \
          "fresh resident resources could not be removed after disappearance"
      return 2
    fi
    sleep 1
    attempts=$((attempts + 1))
  done
  _agent_canon_json_error container_unhealthy "resident container did not become healthy"
  _agent_canon_remove_fresh_candidate_resources "$candidate_container_id" ||
    _agent_canon_json_error rollback_failed \
      "fresh resident resources could not be removed after health timeout"
  return 2
}

_agent_canon_run_controller() {
  local container=$1
  shift
  local output_file error_file rc=0
  local temporary_root=${AGENT_CANON_CONTROLLER_TEMP_ROOT:-$AGENT_CANON_RUNTIME_ROOT}
  output_file=$(mktemp "$temporary_root/.bootstrap.stdout.XXXXXX")
  error_file=$(mktemp "$temporary_root/.bootstrap.stderr.XXXXXX")
  _agent_canon_container_exec "$container" \
    python3 /usr/local/share/agent-canon/runtime/tools/runtime/container/bootstrap_runtime.py \
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

_agent_canon_sync_personal_skill_view() {
  local _container=$1
  local source_root="$AGENT_CANON_REPOSITORY_ROOT/.codex/personal/skills"
  local staging_root="$AGENT_CANON_STATE_ROOT/container-runtime/skill-projection"
  local staging_skills="$staging_root/.codex/personal/skills"
  _agent_canon_volume_copy export skill "$AGENT_CANON_STATE_ROOT/container-runtime"
  if [[ "$staging_root" != "$AGENT_CANON_STATE_ROOT/container-runtime/skill-projection" ]]; then
    _agent_canon_json_error skill_projection_path_invalid "skill projection staging path is invalid"
    return 2
  fi
  if [[ -L "$AGENT_CANON_STATE_ROOT/container-runtime" ]]; then
    _agent_canon_json_error skill_projection_path_invalid "skill projection exchange is a symlink"
    return 2
  fi
  if [[ -L "$source_root" ]]; then
    _agent_canon_json_error skill_projection_path_invalid "personal skill source is a symlink"
    return 2
  fi
  if [[ ! -d "$staging_skills" || -L "$staging_skills" ]]; then
    _agent_canon_json_error skill_projection_copy_failed \
      "resident personal skill view was not materialized"
    return 2
  fi
  if find "$staging_skills" -type l -print -quit | grep -q .; then
    _agent_canon_json_error skill_projection_copy_failed \
      "resident personal skill view contains a symlink"
    return 2
  fi
  if ! find "$staging_skills" -type f -name SKILL.md -print -quit | grep -q .; then
    _agent_canon_json_error skill_projection_copy_failed \
      "resident personal skill view contains no generated skills"
    return 2
  fi
  if ! mkdir -p -- "$source_root"; then
    _agent_canon_json_error skill_projection_copy_failed \
      "host personal skill view could not be created"
    return 2
  fi
  if ! cp -a -- "$staging_skills/." "$source_root/"; then
    _agent_canon_json_error skill_projection_copy_failed \
      "host personal skill view could not be published"
    return 2
  fi
  if [[ -z "$(find "$source_root" -type f -name SKILL.md -print -quit)" ]]; then
    _agent_canon_json_error skill_projection_copy_failed \
      "host personal skill view readback is missing"
    return 2
  fi
  return 0
}

_agent_canon_prepare_skill_view_backup() {
  local source_root="$AGENT_CANON_REPOSITORY_ROOT/.codex/personal/skills"
  local backup_root="$AGENT_CANON_RUNTIME_ROOT/host-state/.skill-view-backup"
  [[ ! -e "$backup_root" && ! -L "$backup_root" ]] || return 2
  [[ ! -L "$source_root" ]] || return 2
  mkdir -p -- "$backup_root" || return 2
  if [[ -e "$source_root" ]]; then
    [[ -d "$source_root" ]] || return 2
    cp -a -- "$source_root" "$backup_root/skills" || return 2
    printf 'present\n' > "$backup_root/presence"
  else
    printf 'absent\n' > "$backup_root/presence"
  fi
}

_agent_canon_restore_skill_view_backup() {
  local source_root=
  local backup_root="$AGENT_CANON_RUNTIME_ROOT/host-state/.skill-view-backup"
  local presence restore_rc=0
  [[ -d "$backup_root" && ! -L "$backup_root" ]] || return 0
  [[ -n "${AGENT_CANON_REPOSITORY_ROOT:-}" ]] || return 2
  source_root="$AGENT_CANON_REPOSITORY_ROOT/.codex/personal/skills"
  [[ -f "$backup_root/presence" && ! -L "$backup_root/presence" ]] || return 2
  presence=$(<"$backup_root/presence")
  [[ "$presence" == present || "$presence" == absent ]] || return 2
  if [[ -e "$source_root" || -L "$source_root" ]]; then
    rm -rf -- "$source_root" || restore_rc=2
  fi
  if [[ "$presence" == present ]]; then
    [[ -d "$backup_root/skills" && ! -L "$backup_root/skills" ]] || return 2
    mkdir -p -- "$(dirname -- "$source_root")" || restore_rc=2
    cp -a -- "$backup_root/skills" "$source_root" || restore_rc=2
  fi
  if ((restore_rc == 0)); then
    rm -rf -- "$backup_root" || restore_rc=2
  fi
  return "$restore_rc"
}

_agent_canon_commit_skill_view_backup() {
  local backup_root="$AGENT_CANON_RUNTIME_ROOT/host-state/.skill-view-backup"
  if [[ -e "$backup_root" || -L "$backup_root" ]]; then
    [[ "${AGENT_CANON_TEST_SKILL_VIEW_COMMIT_FAIL:-0}" != 1 ]] || return 2
    rm -rf -- "$backup_root" || return 2
    [[ ! -e "$backup_root" && ! -L "$backup_root" ]] || return 2
  fi
}

_agent_canon_finish_committed_activation_cleanup() {
  local cleanup_rc=0
  local receipt="${AGENT_CANON_ACTIVATION_COMMIT_RECEIPT:-${AGENT_CANON_RUNTIME_ROOT:-}/host-state/activation-committed.tsv}"
  local volume="${AGENT_CANON_STATE_VOLUME_NAME:-}"
  if [[ ! -e "$receipt" && ! -L "$receipt" ]]; then
    return 0
  fi
  if ! _agent_canon_activation_commit_receipt_valid; then
    _agent_canon_json_error rollback_failed \
      "activation commit receipt is invalid; retained transaction state was not released"
    return 2
  fi
  # The commit receipt is the sole boundary between rollback and cleanup.
  # Clear the committed in-volume snapshot idempotently before any new
  # snapshot can be taken, then attempt every retained backup owner.  Missing
  # backups/receipts are already-cleaned success on retry.
  if [[ -n "$volume" ]] && {
    ! "$AGENT_CANON_DOCKER_CMD" volume inspect "$volume" >/dev/null 2>&1 ||
    ! _agent_canon_state_volume_labels_match "$volume" ||
    ! _agent_canon_state_volume_transaction clear
  }; then
      _agent_canon_json_error rollback_failed \
        "committed controller state volume transaction could not be released"
      cleanup_rc=2
  elif [[ -n "$volume" ]]; then
    AGENT_CANON_STATE_VOLUME_SNAPSHOT_ACTIVE=0
    export AGENT_CANON_STATE_VOLUME_SNAPSHOT_ACTIVE
  fi
  if ! _agent_canon_state_volume_clear_creation_receipt; then
    _agent_canon_json_error rollback_failed \
      "state volume creation receipt could not be released"
    cleanup_rc=2
  fi
  if ! _agent_canon_clear_candidate_identity_receipt; then
    _agent_canon_json_error rollback_failed \
      "candidate identity receipt could not be released"
    cleanup_rc=2
  fi
  if ! _agent_canon_commit_global_links; then
    cleanup_rc=2
  fi
  if ! _agent_canon_commit_controller_projection; then
    _agent_canon_json_error rollback_failed \
      "controller projection backup could not be released"
    cleanup_rc=2
  fi
  if ! _agent_canon_commit_skill_view_backup; then
    _agent_canon_json_error rollback_failed \
      "skill view backup could not be released"
    cleanup_rc=2
  fi
  if ((cleanup_rc == 0)) && ! _agent_canon_clear_activation_commit_receipt; then
    _agent_canon_json_error rollback_failed \
      "activation commit receipt could not be released"
    cleanup_rc=2
  fi
  return "$cleanup_rc"
}

_agent_canon_restore_candidate_failure() {
  local container=$1 old_image_id=$2 candidate_image_id=$3
  local old_image_ref=${AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF:-$old_image_id}
  local recovery_errors=()
  # Quiesce and remove the candidate before restoring the authoritative
  # volume snapshot. A failed cleanup is recorded, but never skips recovery.
  if ! _agent_canon_cleanup_candidate_resources "$container" "$candidate_image_id" "$old_image_id"; then
    recovery_errors+=("candidate_cleanup_failed")
  fi
  if ((${#recovery_errors[@]})); then
    _agent_canon_json_error rollback_failed \
      "previous resident restart skipped; candidate quiescence was not proven: ${recovery_errors[*]}"
    return 2
  fi
  if ! _agent_canon_restore_state_volume_snapshot; then
    recovery_errors+=("state_volume_restore_failed")
  fi
  if ! _agent_canon_restore_controller_projection; then
    recovery_errors+=("controller_projection_restore_failed")
  fi
  if ! _agent_canon_restore_global_links; then
    recovery_errors+=("global_links_restore_failed")
  fi
  if ! _agent_canon_restore_skill_view_backup; then
    recovery_errors+=("skill_view_restore_failed")
  fi
  if ((${#recovery_errors[@]})); then
    _agent_canon_json_error rollback_failed \
      "previous resident restart skipped; required restoration failed: ${recovery_errors[*]}"
    return 2
  fi
  AGENT_CANON_IMAGE_REF=$old_image_ref
  AGENT_CANON_EXPECTED_IMAGE_ID=$old_image_id
  export AGENT_CANON_IMAGE_REF
  export AGENT_CANON_EXPECTED_IMAGE_ID
  local restored
  if ! restored=$(_agent_canon_ensure_container); then
    recovery_errors+=("previous_container_start_failed")
  elif ! _agent_canon_run_controller "$restored" start >/dev/null; then
    recovery_errors+=("previous_state_start_failed")
  fi
  if [[ -n "${AGENT_CANON_PREVIOUS_IMAGE_REF:-}" ]]; then
    if ! _agent_canon_write_active_image "$AGENT_CANON_PREVIOUS_IMAGE_REF" "$old_image_id"; then
      recovery_errors+=("previous_active_image_write_failed")
    fi
  fi
  if ((${#recovery_errors[@]})); then
    _agent_canon_json_error rollback_failed "previous resident restoration failed: ${recovery_errors[*]}"
    return 2
  fi
  return 0
}

_agent_canon_discard_pending_rollback_plan() {
  local pending="$AGENT_CANON_STATE_ROOT/.pending-rollback-plan.tsv"
  if [[ -L "$pending" ]]; then
    _agent_canon_json_error rollback_plan_invalid "pending rollback plan is a symlink"
    return 2
  fi
  rm -f -- "$pending"
  unset AGENT_CANON_PENDING_ROLLBACK_PLAN
}

_agent_canon_commit_pending_rollback_plan() {
  local pending=${AGENT_CANON_PENDING_ROLLBACK_PLAN:-}
  [[ -n "$pending" ]] || return 0
  local plan="$AGENT_CANON_STATE_ROOT/rollback-plan.tsv"
  if [[ "$pending" != "$AGENT_CANON_STATE_ROOT/.pending-rollback-plan.tsv" ||
        ! -f "$pending" || -L "$pending" || -L "$plan" ]]; then
    _agent_canon_json_error rollback_plan_invalid "pending rollback plan is unavailable"
    return 2
  fi
  if ! mv -f -- "$pending" "$plan"; then
    _agent_canon_json_error rollback_plan_invalid "pending rollback plan could not be published"
    return 2
  fi
  unset AGENT_CANON_PENDING_ROLLBACK_PLAN
}

_agent_canon_prepare_forced_update_locked() {
  local container=$(_agent_canon_container_name)
  local pending="$AGENT_CANON_STATE_ROOT/.pending-rollback-plan.tsv"
  local old_image_ref old_image_id planned_image_id planned_image_ref
  _agent_canon_discard_pending_rollback_plan
  if [[ ! -f "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" ]] &&
     ! "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
    return 0
  fi
  if [[ -f "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" ]]; then
    if _agent_canon_read_active_image; then
      :
    else
      return $?
    fi
  else
    if ! old_image_ref=$("$AGENT_CANON_DOCKER_CMD" container inspect \
      --format '{{.Config.Image}}' "$container" 2>/dev/null); then
      _agent_canon_json_error active_image_readback_failed "resident image reference readback failed"
      return 2
    fi
    if ! old_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
      --format '{{.Id}}' "$old_image_ref" 2>/dev/null); then
      _agent_canon_json_error active_image_readback_failed "resident image ID readback failed"
      return 2
    fi
    AGENT_CANON_IMAGE_REF=$old_image_ref
    AGENT_CANON_ACTIVE_IMAGE_ID=$old_image_id
    AGENT_CANON_EXPECTED_IMAGE_ID=$old_image_id
    export AGENT_CANON_IMAGE_REF AGENT_CANON_ACTIVE_IMAGE_ID AGENT_CANON_EXPECTED_IMAGE_ID
    _agent_canon_classify_existing_container "$container" || return $?
  fi
  old_image_ref=${AGENT_CANON_IMAGE_REF:-$old_image_ref}
  old_image_id=${AGENT_CANON_ACTIVE_IMAGE_ID:-$old_image_id}
  if ! _agent_canon_write_rollback_plan "$old_image_id" "$old_image_ref" "$pending"; then
    _agent_canon_discard_pending_rollback_plan || :
    return 2
  fi
  planned_image_id=$(awk -F $'\t' '$1 == "image-id" { print $2 }' "$pending")
  planned_image_ref=$(awk -F $'\t' '$1 == "image-ref" { print $2 }' "$pending")
  if [[ "$planned_image_id" != "$old_image_id" || -z "$planned_image_ref" ]]; then
    _agent_canon_discard_pending_rollback_plan || :
    _agent_canon_json_error rollback_plan_invalid "retained rollback plan readback differs from the active image"
    return 2
  fi
  AGENT_CANON_PENDING_ROLLBACK_PLAN=$pending
  export AGENT_CANON_PENDING_ROLLBACK_PLAN
}

_agent_canon_update_locked() {
  local requested_ref=${1:-} candidate_image_ref=$2 candidate_image_id rc
  set +e
  _agent_canon_prepare_forced_update_locked
  rc=$?
  set -e
  if ((rc != 0)); then
    _agent_canon_discard_pending_rollback_plan || :
    return "$rc"
  fi
  set +e
  _agent_canon_image "$requested_ref"
  rc=$?
  set -e
  if ((rc != 0)); then
    _agent_canon_discard_pending_rollback_plan || :
    return "$rc"
  fi
  candidate_image_ref=$AGENT_CANON_IMAGE_REF
  if ! candidate_image_id=$({
    "$AGENT_CANON_DOCKER_CMD" image inspect --format '{{.Id}}' "$candidate_image_ref"
  }); then
    _agent_canon_discard_pending_rollback_plan || :
    _agent_canon_json_error candidate_image_missing "candidate resident image could not be inspected"
    return 2
  fi
  set +e
  (
    set -e
    _agent_canon_replace_resident_locked "$candidate_image_ref" "$candidate_image_id" update
  )
  rc=$?
  set -e
  set +e
  _agent_canon_discard_pending_rollback_plan
  local discard_rc=$?
  set -e
  if ((rc != 0)); then
    return "$rc"
  fi
  return "$discard_rc"
}

_agent_canon_replace_resident_locked() {
  local candidate_image_ref=$1 candidate_image_id=$2
  local replacement_operation=${3:-update}
  local clean_install_prepared=${4:-0}
  local old_image_id old_image_ref old_container candidate restored rc
  local old_container_present=0 current_resident_valid=0 clean_install=0 old_quiesced=0
  local old_container_removed=0 old_container_id old_container_runtime old_container_control stale_target_pruned=
  if [[ "$clean_install_prepared" != 1 ]]; then
    AGENT_CANON_CLEAN_INSTALL_ACTIVE=0
    AGENT_CANON_CLEAN_INSTALL_SUCCESS=0
    AGENT_CANON_CLEAN_INSTALL_COMMITTED=0
    AGENT_CANON_CLEAN_INSTALL_OLD_CONTAINER=
    AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF=
    AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_ID=
    AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED=0
    AGENT_CANON_CLEAN_INSTALL_OLD_REMOVED=0
  else
    AGENT_CANON_CLEAN_INSTALL_SUCCESS=0
    AGENT_CANON_CLEAN_INSTALL_COMMITTED=0
  fi
  export AGENT_CANON_CLEAN_INSTALL_OLD_CONTAINER \
    AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF \
    AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_ID \
    AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED \
    AGENT_CANON_CLEAN_INSTALL_OLD_REMOVED AGENT_CANON_CLEAN_INSTALL_COMMITTED
  trap '_agent_canon_clean_install_exit' EXIT
  if ! candidate_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect --format '{{.Id}}' "$candidate_image_ref"); then
    _agent_canon_json_error candidate_image_missing "candidate resident image disappeared before replacement"
    return 2
  fi
  if [[ "$clean_install_prepared" == 1 ]]; then
    old_container=${AGENT_CANON_CLEAN_INSTALL_OLD_CONTAINER:-}
    old_image_ref=${AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF:-}
    old_image_id=${AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_ID:-}
    old_container_present=0
    [[ -n "$old_container" ]] && old_container_present=1
    old_quiesced=${AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED:-0}
    old_container_removed=${AGENT_CANON_CLEAN_INSTALL_OLD_REMOVED:-0}
    clean_install=1
    stale_target_pruned=clean_install
  else
    old_container=$(_agent_canon_container_name)
    if "$AGENT_CANON_DOCKER_CMD" container inspect "$old_container" >/dev/null 2>&1; then
      # A named resident is claimable only by its immutable AgentCanon labels.
      # Install does not validate its old layout, mounts, or security fields.
      _agent_canon_classify_existing_container "$old_container" || return $?
      old_container_id=$AGENT_CANON_OBSERVED_CONTAINER_ID
      old_container_runtime=$AGENT_CANON_OBSERVED_CONTAINER_RUNTIME
      old_container_control=$AGENT_CANON_OBSERVED_CONTAINER_CONTROL
      old_container_present=1
    fi
    old_image_ref=
    old_image_id=
  fi
  if [[ "$replacement_operation" == install && "$clean_install_prepared" != 1 ]]; then
    # Install deliberately ignores the previous active-image and mount
    # records. Capture the owned resident's exact image reference and validate
    # its immutable identity;
    # the existing resident replacement transaction will tear it down after
    # the candidate is ready and restore it if candidate activation fails.
    if ((old_container_present == 1)); then
      if ! old_image_ref=$("$AGENT_CANON_DOCKER_CMD" container inspect \
        --format '{{.Config.Image}}' "$old_container"); then
        _agent_canon_json_error active_image_readback_failed "resident image reference readback failed"
        return 2
      fi
      if ! old_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
        --format '{{.Id}}' "$old_image_ref"); then
        _agent_canon_json_error active_image_readback_failed "resident image ID readback failed"
        return 2
      fi
    fi
    # Establish the EXIT-trap restore owner before stopping the resident or
    # resetting any mounted runtime state.  A prepare failure must therefore
    # restart the exact resident captured above.
    AGENT_CANON_CLEAN_INSTALL_OLD_CONTAINER=$old_container
    AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF=$old_image_ref
    AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_ID=$old_image_id
    AGENT_CANON_CLEAN_INSTALL_ACTIVE=1
    export AGENT_CANON_CLEAN_INSTALL_OLD_CONTAINER \
      AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF \
      AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_ID \
      AGENT_CANON_CLEAN_INSTALL_ACTIVE
    if ((old_container_present == 1)); then
      # The runtime files below are mounted by the old resident. Quiesce it
      # while the replacement lock is held, before taking the clean-install
      # snapshot or removing those files.
      _agent_canon_require_existing_container_identity "$old_container" \
        "$old_container_id" "$old_container_runtime" "$old_container_control" || return $?
      if ! "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$old_container_id" >/dev/null; then
        _agent_canon_json_error replacement_stop_failed "old resident could not be stopped"
        return 2
      fi
      old_quiesced=1
      AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED=1
      export AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED
    fi
    _agent_canon_prepare_clean_install
    clean_install=1
    stale_target_pruned=clean_install
  elif ((old_container_present == 1)); then
    # A missing target is stale derived registry state. Remove only those
    # entries before the complete manifest validation; malformed or otherwise
    # invalid records remain validation errors.
    _agent_canon_prune_stale_target_manifest || return $?
    stale_target_pruned=$AGENT_CANON_TARGET_PRUNE_DIGESTS
    _agent_canon_validate_target_manifest "$AGENT_CANON_STATE_ROOT/mounts.tsv" || return $?
  else
    _agent_canon_prune_stale_target_manifest || return $?
    stale_target_pruned=$AGENT_CANON_TARGET_PRUNE_DIGESTS
  fi
  AGENT_CANON_IMAGE_REF=$candidate_image_ref
  AGENT_CANON_EXPECTED_IMAGE_ID=$candidate_image_id
  export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID

  # Existing volumes carry the authoritative rollback payload. Preserve its
  # bounded logical set before any candidate ensure/import can mutate it.
  if ! _agent_canon_prepare_state_volume_snapshot; then
    _agent_canon_json_error rollback_snapshot_failed \
      "controller state volume rollback snapshot could not be prepared"
    return 2
  fi

  # This readback happens after the replacement lock is acquired.  A build
  # may have completed while another update owned the resident, so the
  # resident state—not the caller's pre-lock snapshot—is authoritative.
  if ((clean_install == 1)); then
    AGENT_CANON_IMAGE_REF=$candidate_image_ref
    AGENT_CANON_EXPECTED_IMAGE_ID=$candidate_image_id
    export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID
  elif [[ -f "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" ]] ||
     "$AGENT_CANON_DOCKER_CMD" container inspect "$old_container" >/dev/null 2>&1; then
    _agent_canon_use_active_image "$old_container" || return $?
    old_image_ref=$AGENT_CANON_IMAGE_REF
    old_image_id=$AGENT_CANON_ACTIVE_IMAGE_ID
    if [[ -z "$stale_target_pruned" && -n "$old_image_id" && "$old_image_id" == "$candidate_image_id" &&
          "$old_image_ref" == "$candidate_image_ref" &&
          -n "$candidate_image_id" ]] &&
       ((old_container_present == 1)); then
      # The first updater already completed the transaction.  Revalidate the
      # exact resident and health path. A mismatch is owned drift, so continue
      # through the serialized replacement below instead of returning an
      # ownership error.
      if _agent_canon_validate_existing_container "$old_container" \
        "$AGENT_CANON_STATE_ROOT/mounts.tsv" 1 0 >/dev/null 2>/dev/null; then
        current_resident_valid=1
      fi
    fi
    if ((current_resident_valid == 1)); then
      AGENT_CANON_IMAGE_REF=$candidate_image_ref
      AGENT_CANON_EXPECTED_IMAGE_ID=$candidate_image_id
      export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID
      if candidate=$(_agent_canon_ensure_container); then
        :
      else
        rc=$?
        _agent_canon_restore_state_volume_snapshot || {
          _agent_canon_json_error rollback_failed \
            "controller state volume snapshot could not be restored"
          return 2
        }
        _agent_canon_clear_candidate_identity_receipt || {
          _agent_canon_json_error rollback_failed \
            "up-to-date candidate identity receipt could not be released after rollback"
          return 2
        }
        return "$rc"
      fi
      if _agent_canon_record_active_container "$candidate"; then
        :
      else
        rc=$?
        _agent_canon_restore_state_volume_snapshot || {
          _agent_canon_json_error rollback_failed \
            "controller state volume snapshot could not be restored"
          return 2
        }
        _agent_canon_clear_candidate_identity_receipt || {
          _agent_canon_json_error rollback_failed \
            "up-to-date candidate identity receipt could not be released after rollback"
          return 2
        }
        return "$rc"
      fi
      if _agent_canon_discard_pending_rollback_plan; then
        :
      else
        rc=$?
        _agent_canon_restore_state_volume_snapshot || rc=2
        _agent_canon_clear_candidate_identity_receipt || rc=2
        return "$rc"
      fi
      if ! _agent_canon_write_activation_commit_receipt "$candidate_image_id" "$candidate"; then
        _agent_canon_json_error rollback_failed \
          "up-to-date activation commit receipt could not be published"
        _agent_canon_restore_state_volume_snapshot || {
          _agent_canon_json_error rollback_failed \
            "controller state volume snapshot could not be restored"
          return 2
        }
        _agent_canon_clear_candidate_identity_receipt || {
          _agent_canon_json_error rollback_failed \
            "up-to-date candidate identity receipt could not be released after rollback"
          return 2
        }
        return 2
      fi
      AGENT_CANON_CLEAN_INSTALL_COMMITTED=1
      AGENT_CANON_CLEAN_INSTALL_SUCCESS=1
      export AGENT_CANON_CLEAN_INSTALL_COMMITTED AGENT_CANON_CLEAN_INSTALL_SUCCESS
      _agent_canon_finish_committed_activation_cleanup || {
        _agent_canon_json_error rollback_failed \
          "up-to-date committed activation cleanup remains pending"
        return 2
      }
      printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"%s","code":"up_to_date","changed":false}\n' \
        "$replacement_operation"
      return 0
    fi
    AGENT_CANON_IMAGE_REF=$old_image_ref
    AGENT_CANON_EXPECTED_IMAGE_ID=$old_image_id
    export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID
  else
    unset AGENT_CANON_EXPECTED_IMAGE_ID AGENT_CANON_ACTIVE_IMAGE_ID
  fi

  AGENT_CANON_IMAGE_REF=$candidate_image_ref
  AGENT_CANON_EXPECTED_IMAGE_ID=$candidate_image_id
  AGENT_CANON_PREVIOUS_IMAGE_ID=$old_image_id
  export AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID AGENT_CANON_PREVIOUS_IMAGE_ID
  if ((old_container_present == 1 && old_container_removed == 0)); then
    # This is deliberately the final readback before teardown. Stop/remove by
    # the captured immutable ID so a name swap cannot redirect the mutation.
    _agent_canon_require_existing_container_identity "$old_container" \
      "$old_container_id" "$old_container_runtime" "$old_container_control" || return $?
  fi
  if ((old_container_present == 1)) &&
     [[ -z "${AGENT_CANON_PENDING_ROLLBACK_PLAN:-}" ]]; then
    _agent_canon_write_rollback_plan "$old_image_id" "$old_image_ref" || return $?
    if ((clean_install == 1)); then
      AGENT_CANON_CLEAN_INSTALL_ROLLBACK_REF=$(awk -F $'\t' \
        '$1 == "image-ref" { print $2; exit }' "$AGENT_CANON_STATE_ROOT/rollback-plan.tsv")
      AGENT_CANON_CLEAN_INSTALL_ROLLBACK_ID=$old_image_id
      export AGENT_CANON_CLEAN_INSTALL_ROLLBACK_REF AGENT_CANON_CLEAN_INSTALL_ROLLBACK_ID
    fi
  fi
  if [[ -n "$old_image_id" ]]; then
    if ! printf '%s\n' "$old_image_id" > "$AGENT_CANON_STATE_ROOT/previous-image-id"; then
      _agent_canon_json_error active_image_write_failed "previous image state could not be written"
      return 2
    fi
    AGENT_CANON_PREVIOUS_IMAGE_REF=$old_image_ref
    export AGENT_CANON_PREVIOUS_IMAGE_REF
  fi
  if [[ -n "$old_image_id" ]] &&
     ((old_container_present == 1 && old_container_removed == 0)); then
    if ((old_quiesced == 0)) && ! "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$old_container_id" >/dev/null; then
      _agent_canon_json_error replacement_stop_failed "old resident could not be stopped"
      return 2
    fi
    if ! "$AGENT_CANON_DOCKER_CMD" rm "$old_container_id" >/dev/null; then
      _agent_canon_json_error replacement_remove_failed "old resident could not be removed"
      return 2
    fi
  fi
  if candidate=$(_agent_canon_ensure_container); then
    :
  else
    local candidate_rc=$?
    local candidate_cleanup_rc=0
    _agent_canon_cleanup_candidate_resources "$(_agent_canon_container_name)" \
      "${candidate_image_id:-}" "$old_image_id" || candidate_cleanup_rc=1
    if ((candidate_cleanup_rc != 0)); then
      _agent_canon_json_error rollback_failed \
        "candidate quiescence was not proven; volume restoration was skipped"
      return 2
    fi
    if ! _agent_canon_restore_state_volume_snapshot; then
      _agent_canon_json_error rollback_failed \
        "controller state volume snapshot could not be restored"
      return 2
    fi
    if ! _agent_canon_restore_controller_projection ||
       ! _agent_canon_restore_global_links ||
       ! _agent_canon_restore_skill_view_backup; then
      _agent_canon_json_error rollback_failed \
        "late activation state could not be restored"
      return 2
    fi
    if ((clean_install == 1)); then
      if _agent_canon_discard_clean_install_rollback_tag &&
         _agent_canon_restore_clean_install; then
        AGENT_CANON_CLEAN_INSTALL_ACTIVE=0
      else
        _agent_canon_json_error rollback_failed \
          "clean install state could not be restored after candidate failure"
        return 2
      fi
    fi
    if ((candidate_cleanup_rc != 0)); then
      _agent_canon_json_error rollback_failed \
        "candidate resources could not be removed after health failure"
      return 2
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
    if ((candidate_rc != 2)); then
      _agent_canon_json_error candidate_unhealthy "candidate resident container failed health readback"
      candidate_rc=2
    fi
    return "$candidate_rc"
  fi
  rc=0
  if _agent_canon_run_controller "$candidate" "$replacement_operation"; then
    :
  else
    rc=$?
  fi
  if ((rc == 0)); then
    AGENT_CANON_KEEP_CONTROLLER_PROJECTION_BACKUP=1
    export AGENT_CANON_KEEP_CONTROLLER_PROJECTION_BACKUP
    if _agent_canon_publish_controller_projection; then
      :
    else
      rc=$?
    fi
  fi
  if ((rc == 0)) && [[ -n "${AGENT_CANON_REPOSITORY_ROOT:-}" ]]; then
    if _agent_canon_prepare_skill_view_backup; then
      :
    else
      rc=$?
    fi
    if ((rc == 0)); then
      if _agent_canon_sync_personal_skill_view "$candidate"; then
        :
      else
        rc=$?
      fi
    fi
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
  if ((rc == 0)) && [[ -n "${AGENT_CANON_PENDING_ROLLBACK_PLAN:-}" ]]; then
    if _agent_canon_commit_pending_rollback_plan; then
      :
    else
      rc=$?
    fi
  fi
  if ((rc == 0)) && ((clean_install == 1)); then
    if _agent_canon_drop_legacy_controller_state; then
      :
    else
      rc=$?
    fi
  fi
  if ((rc == 0)); then
    if ! _agent_canon_write_activation_commit_receipt "$candidate_image_id" "$candidate"; then
      _agent_canon_json_error rollback_failed \
        "activation commit receipt could not be published"
      rc=2
    fi
  fi
  if ((rc == 0)); then
    # All activation readbacks have succeeded.  Mark the transaction committed
    # before any backup/receipt removal so a cleanup failure cannot enter the
    # old-generation recovery path after partial publication.
    AGENT_CANON_CLEAN_INSTALL_COMMITTED=1
    AGENT_CANON_CLEAN_INSTALL_SUCCESS=1
    export AGENT_CANON_CLEAN_INSTALL_COMMITTED AGENT_CANON_CLEAN_INSTALL_SUCCESS
  fi
  if [[ "${AGENT_CANON_CLEAN_INSTALL_COMMITTED:-0}" == 1 ]]; then
    if ! _agent_canon_finish_committed_activation_cleanup; then
      _agent_canon_json_error state_volume_transaction_cleanup_failed \
        "committed activation cleanup remains pending"
      rc=2
    else
      unset AGENT_CANON_KEEP_CONTROLLER_PROJECTION_BACKUP
    fi
  fi
  if ((rc != 0)) && [[ "${AGENT_CANON_CLEAN_INSTALL_COMMITTED:-0}" != 1 ]] &&
     [[ -z "$old_image_id" ]]; then
    local fresh_cleanup_rc=0
    _agent_canon_cleanup_candidate_resources "${candidate:-$(_agent_canon_container_name)}" \
      "${candidate_image_id:-}" "$old_image_id" || fresh_cleanup_rc=1
    if ((fresh_cleanup_rc != 0)); then
      _agent_canon_json_error rollback_failed \
        "candidate quiescence was not proven; volume restoration was skipped"
      return 2
    fi
    if ! _agent_canon_restore_state_volume_snapshot; then
      fresh_cleanup_rc=1
    fi
    _agent_canon_restore_controller_projection || fresh_cleanup_rc=1
    _agent_canon_restore_global_links || fresh_cleanup_rc=1
    _agent_canon_restore_skill_view_backup || fresh_cleanup_rc=1
    _agent_canon_remove_fresh_state_volume || fresh_cleanup_rc=1
    if ((fresh_cleanup_rc != 0)); then
      _agent_canon_json_error rollback_failed \
        "fresh candidate resources could not be removed after failure"
      return 2
    fi
  fi
  if ((rc != 0)) && [[ "${AGENT_CANON_CLEAN_INSTALL_COMMITTED:-0}" != 1 ]] &&
     ((clean_install == 1)); then
    if _agent_canon_discard_clean_install_rollback_tag &&
       _agent_canon_restore_clean_install; then
      AGENT_CANON_CLEAN_INSTALL_ACTIVE=0
    else
      _agent_canon_json_error rollback_failed \
        "clean install state could not be restored after candidate failure"
      return 2
    fi
  fi
  if ((rc != 0)) && [[ "${AGENT_CANON_CLEAN_INSTALL_COMMITTED:-0}" != 1 ]] &&
     [[ -n "$old_image_id" ]]; then
    if ! _agent_canon_restore_candidate_failure "$candidate" "$old_image_id" "$candidate_image_id"; then
      _agent_canon_json_error rollback_failed "candidate failure recovery was incomplete"
      return 2
    fi
  fi
  unset AGENT_CANON_PREVIOUS_IMAGE_ID AGENT_CANON_PREVIOUS_IMAGE_REF
  if ((clean_install == 1)) && ((rc == 0)); then
    AGENT_CANON_CLEAN_INSTALL_SUCCESS=1
  fi
  return "$rc"
}

_agent_canon_with_replacement_lock() {
  local callback=$1
  shift
  local lock_path="$AGENT_CANON_RUNTIME_ROOT/host-state/replacement.lock"
  local lock_fd rc unlock_rc
  if [[ -L "$lock_path" ]]; then
    _agent_canon_json_error replacement_lock_invalid "resident replacement lock is a symlink"
    return 2
  fi
  if ! command -v flock >/dev/null 2>&1; then
    _agent_canon_json_error replacement_lock_unavailable "flock is required for resident replacement"
    return 2
  fi
  if [[ "${AGENT_CANON_LOCK_READ_ONLY:-0}" == 1 ]]; then
    # A preview must not create the runtime or its lock.  Prefer the existing
    # replacement lock; a pre-existing runtime directory is a read-only lock
    # fallback for first-run previews, and /dev/null covers a missing runtime.
    if [[ -e "$lock_path" ]]; then
      exec {lock_fd}<"$lock_path" || {
        _agent_canon_json_error replacement_lock_unavailable "resident replacement lock could not be opened"
        return 2
      }
    elif [[ -d "$AGENT_CANON_RUNTIME_ROOT" ]]; then
      exec {lock_fd}<"$AGENT_CANON_RUNTIME_ROOT" || {
        _agent_canon_json_error replacement_lock_unavailable "runtime directory could not be opened for preview"
        return 2
      }
    else
      exec {lock_fd}</dev/null || {
        _agent_canon_json_error replacement_lock_unavailable "preview lock could not be opened"
        return 2
      }
    fi
  elif ! exec {lock_fd}>"$lock_path"; then
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
    "$callback" "$@"
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

_agent_canon_gc_array_contains() {
  local needle=$1 item
  shift
  for item in "$@"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

_agent_canon_gc_locked() {
  local dry_run=${1:-0}
  local control_digest live_name live_id live_ref live_image_id listing
  local state_volume
  local container_id container_name image_id image_repository image_tag image_ref
  local active_ref= active_id= rollback_ref= rollback_id= rollback_plan
  local state_receipt= rollback_mounts=
  local -a container_keep_json=() container_remove_json=()
  local -a image_keep_json=() image_remove_json=()
  local -a volume_keep_json=() volume_remove_json=()
  local -a kept_container_ids=() kept_image_ids=() kept_image_refs=()
  local -a removed_volume_names=()
  local -a removed_container_ids=() removed_image_refs=() removed_image_ids=()

  [[ "$dry_run" == 0 || "$dry_run" == 1 ]] ||
    _agent_canon_json_error argument_invalid "gc dry-run flag is invalid"
  AGENT_CANON_STATE_ROOT=${AGENT_CANON_STATE_ROOT:-$AGENT_CANON_RUNTIME_ROOT/container-state}
  export AGENT_CANON_STATE_ROOT
  control_digest=$(_agent_canon_control_digest)
  live_name=$(_agent_canon_container_name)
  state_volume="agent-canon-runtime-$control_digest"

  # The existing identity reader is authoritative.  Never use a persisted
  # container ID: the daemon may have recreated the named resident.
  if _agent_canon_read_container_identity "$live_name" >/dev/null 2>&1; then
    live_id=$AGENT_CANON_OBSERVED_CONTAINER_ID
    if ! live_ref=$("$AGENT_CANON_DOCKER_CMD" container inspect \
      --format '{{.Config.Image}}' "$live_name" 2>/dev/null); then
      _agent_canon_json_error gc_resident_readback_failed "resident image reference could not be read"
    fi
    live_ref=${live_ref//$'\n'/}
    container_keep_json+=("{\"id\":\"$(_agent_canon_json_escape "$live_id")\",\"name\":\"$(_agent_canon_json_escape "$live_name")\"}")
    kept_container_ids+=("$live_id")
    [[ -n "$live_ref" ]] ||
      _agent_canon_json_error gc_resident_readback_failed "resident image reference is empty"
    if ! live_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
      --format '{{.Id}}' "$live_ref" 2>/dev/null); then
      _agent_canon_json_error gc_resident_readback_failed "resident image ID could not be read"
    fi
    live_image_id=${live_image_id//$'\n'/}
    [[ "$live_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] ||
      _agent_canon_json_error gc_resident_readback_failed "resident image ID is invalid"
    kept_image_ids+=("$live_image_id")
    kept_image_refs+=("$live_ref")
  else
    live_id=
    live_ref=
  fi

  # Existing state readers validate their own schemas.  The rollback reader
  # writes its derived mount projection, so preview directs that output to a
  # temporary file outside the runtime and removes it immediately.
  if [[ -f "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" ]]; then
    _agent_canon_read_active_image
    active_ref=$AGENT_CANON_IMAGE_REF
    active_id=$AGENT_CANON_ACTIVE_IMAGE_ID
  fi
  rollback_plan="$AGENT_CANON_STATE_ROOT/rollback-plan.tsv"
  if [[ -f "$rollback_plan" ]]; then
    if [[ "$dry_run" == 1 ]]; then
      rollback_mounts=$(mktemp "${TMPDIR:-/tmp}/agent-canon-gc-rollback.XXXXXX") ||
        _agent_canon_json_error gc_state_invalid "rollback reader temporary file could not be created"
      _agent_canon_read_rollback_plan "$rollback_mounts"
    else
      _agent_canon_read_rollback_plan
    fi
    rollback_ref=$AGENT_CANON_ROLLBACK_IMAGE_REF
    rollback_id=$AGENT_CANON_ROLLBACK_IMAGE_ID
    [[ -n "$rollback_mounts" ]] && rm -f -- "$rollback_mounts"
  fi

  for image_id in "$active_id" "$rollback_id"; do
    [[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || continue
    _agent_canon_gc_array_contains "$image_id" "${kept_image_ids[@]}" ||
      kept_image_ids+=("$image_id")
  done
  for image_ref in "$active_ref" "$rollback_ref" "$live_ref"; do
    [[ -n "$image_ref" ]] || continue
    _agent_canon_gc_array_contains "$image_ref" "${kept_image_refs[@]}" ||
      kept_image_refs+=("$image_ref")
  done

  if ! listing=$("$AGENT_CANON_DOCKER_CMD" container ls --all --no-trunc \
    --filter "label=io.agent-canon.runtime=shared-v1" \
    --filter "label=io.agent-canon.control-root-digest=$control_digest" \
    --format '{{.ID}}\t{{.Names}}'); then
    _agent_canon_json_error gc_enumeration_failed "owned containers could not be enumerated"
  fi
  while IFS=$'\t' read -r container_id container_name; do
    [[ -n "$container_id" ]] || continue
    [[ "$container_name" == "$live_name" && "$container_id" == "$live_id" ]] && continue
    container_remove_json+=("{\"id\":\"$(_agent_canon_json_escape "$container_id")\",\"name\":\"$(_agent_canon_json_escape "$container_name")\"}")
    _agent_canon_gc_array_contains "$container_id" "${removed_container_ids[@]}" ||
      removed_container_ids+=("$container_id")
  done <<<"$listing"

  if ! listing=$("$AGENT_CANON_DOCKER_CMD" image ls --all --no-trunc \
    --filter "label=io.agent-canon.runtime=shared-v1" \
    --filter "label=io.agent-canon.control-root-digest=$control_digest" \
    --format '{{.ID}}\t{{.Repository}}\t{{.Tag}}'); then
    _agent_canon_json_error gc_enumeration_failed "owned images could not be enumerated"
  fi
  while IFS=$'\t' read -r image_id image_repository image_tag; do
    [[ -n "$image_id" ]] || continue
    image_ref=
    if [[ "$image_repository" != '<none>' && "$image_tag" != '<none>' &&
          -n "$image_repository" && -n "$image_tag" ]]; then
      image_ref="$image_repository:$image_tag"
    fi
    if _agent_canon_gc_array_contains "$image_id" "${kept_image_ids[@]}" ||
      { [[ -n "$image_ref" ]] && _agent_canon_gc_array_contains "$image_ref" "${kept_image_refs[@]}"; }; then
      image_keep_json+=("{\"id\":\"$(_agent_canon_json_escape "$image_id")\",\"ref\":\"$(_agent_canon_json_escape "$image_ref")\"}")
      _agent_canon_gc_array_contains "$image_id" "${kept_image_ids[@]}" || kept_image_ids+=("$image_id")
    else
      if [[ -n "$image_ref" ]]; then
        if ! _agent_canon_gc_array_contains "$image_ref" "${removed_image_refs[@]}"; then
          removed_image_refs+=("$image_ref")
          image_remove_json+=("{\"id\":\"$(_agent_canon_json_escape "$image_id")\",\"ref\":\"$(_agent_canon_json_escape "$image_ref")\"}")
        fi
      elif ! _agent_canon_gc_array_contains "$image_id" "${removed_image_ids[@]}"; then
        removed_image_ids+=("$image_id")
        image_remove_json+=("{\"id\":\"$(_agent_canon_json_escape "$image_id")\",\"ref\":\"\"}")
      fi
    fi
  done <<<"$listing"

  if ! listing=$("$AGENT_CANON_DOCKER_CMD" volume ls \
    --filter "label=io.agent-canon.runtime=shared-v1" \
    --filter "label=io.agent-canon.control-root-digest=$control_digest" \
    --format '{{.Name}}'); then
    _agent_canon_json_error gc_enumeration_failed "owned state volumes could not be enumerated"
  fi
  while IFS= read -r volume_name; do
    [[ -n "$volume_name" ]] || continue
    if [[ "$volume_name" == "$state_volume" ]]; then
      volume_keep_json+=("{\"name\":\"$(_agent_canon_json_escape \"$volume_name\")\"}")
    else
      volume_remove_json+=("{\"name\":\"$(_agent_canon_json_escape \"$volume_name\")\"}")
      _agent_canon_gc_array_contains "$volume_name" "${removed_volume_names[@]}" ||
        removed_volume_names+=("$volume_name")
    fi
  done <<<"$listing"

  if [[ "$dry_run" == 0 ]]; then
    for container_id in "${removed_container_ids[@]}"; do
      if ! "$AGENT_CANON_DOCKER_CMD" rm -f "$container_id" >/dev/null; then
        _agent_canon_json_error gc_remove_failed "stale owned container could not be removed"
      fi
    done
    for image_ref in "${removed_image_refs[@]}"; do
      if ! "$AGENT_CANON_DOCKER_CMD" image rm "$image_ref" >/dev/null; then
        _agent_canon_json_error gc_remove_failed "stale owned image tag could not be removed"
      fi
    done
    for image_id in "${removed_image_ids[@]}"; do
      if ! "$AGENT_CANON_DOCKER_CMD" image rm "$image_id" >/dev/null; then
        _agent_canon_json_error gc_remove_failed "stale owned image could not be removed"
      fi
    done
    for volume_name in "${removed_volume_names[@]}"; do
      if ! "$AGENT_CANON_DOCKER_CMD" volume rm "$volume_name" >/dev/null; then
        _agent_canon_json_error gc_remove_failed "stale owned state volume could not be removed"
      fi
    done
  fi

  if [[ -n "$live_id" ]]; then
    local state_output state_rc=0
    AGENT_CANON_IMAGE_REF=$live_ref
    export AGENT_CANON_IMAGE_REF
    if [[ "$dry_run" == 1 ]]; then
      state_output=$(AGENT_CANON_CONTROLLER_TEMP_ROOT=${TMPDIR:-/tmp} \
        _agent_canon_run_controller "$live_name" gc --dry-run) || state_rc=$?
    else
      state_output=$(_agent_canon_run_controller "$live_name" gc) || state_rc=$?
    fi
    ((state_rc == 0)) ||
      _agent_canon_json_error gc_state_failed "container runtime GC failed"
    state_receipt=$(printf '%s\n' "$state_output" | tail -n 1)
    [[ "$state_receipt" == \{*\} ]] ||
      _agent_canon_json_error gc_state_failed "container runtime GC returned no receipt"
  fi
  printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"gc","code":"%s","details":{"dry_run":%s,"containers":{"keep":[%s],"remove":[%s]},"images":{"keep":[%s],"remove":[%s]},"volumes":{"keep":[%s],"remove":[%s]},"state":%s}}\n' \
    "$([[ "$dry_run" == 1 ]] && printf gc_plan || printf gc_complete)" \
    "$([[ "$dry_run" == 1 ]] && printf true || printf false)" \
    "$(IFS=,; printf '%s' "${container_keep_json[*]}")" \
    "$(IFS=,; printf '%s' "${container_remove_json[*]}")" \
    "$(IFS=,; printf '%s' "${image_keep_json[*]}")" \
    "$(IFS=,; printf '%s' "${image_remove_json[*]}")" \
    "$(IFS=,; printf '%s' "${volume_keep_json[*]}")" \
    "$(IFS=,; printf '%s' "${volume_remove_json[*]}")" \
    "${state_receipt:-null}"
}

_agent_canon_gc() {
  local dry_run=0 argument
  for argument in "${command_args[@]:1}"; do
    case "$argument" in
      --dry-run) dry_run=1 ;;
      *) _agent_canon_json_error argument_invalid "unsupported gc argument: $argument"; return 2 ;;
    esac
  done
  if [[ "$dry_run" == 1 ]]; then
    AGENT_CANON_LOCK_READ_ONLY=1 \
      AGENT_CANON_CONTROLLER_TEMP_ROOT=${TMPDIR:-/tmp} \
      _agent_canon_with_replacement_lock _agent_canon_gc_locked "$dry_run"
  else
    _agent_canon_with_replacement_lock _agent_canon_gc_locked "$dry_run"
  fi
}

_agent_canon_install_locked() {
  # Clean install owns one serialized transition.  Capture and remove only the
  # named resident after ownership readback, then clear generated state before
  # building the candidate.  The EXIT trap restores the captured state if any
  # later phase fails.
  local old_container=$(_agent_canon_container_name)
  local old_container_id= old_image_ref= old_image_id=
  local old_container_present=0
  if "$AGENT_CANON_DOCKER_CMD" container inspect "$old_container" >/dev/null 2>&1; then
    _agent_canon_classify_existing_container "$old_container" || return $?
    old_container_id=$AGENT_CANON_OBSERVED_CONTAINER_ID
    old_container_present=1
    if ! old_image_ref=$("$AGENT_CANON_DOCKER_CMD" container inspect \
      --format '{{.Config.Image}}' "$old_container"); then
      _agent_canon_json_error active_image_readback_failed "resident image reference readback failed"
      return 2
    fi
    if ! old_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
      --format '{{.Id}}' "$old_image_ref"); then
      _agent_canon_json_error active_image_readback_failed "resident image ID readback failed"
      return 2
    fi
  fi

  if ((old_container_present == 0)); then
    old_container=
  fi
  AGENT_CANON_CLEAN_INSTALL_OLD_CONTAINER=$old_container
  AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF=$old_image_ref
  AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_ID=$old_image_id
  AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED=0
  AGENT_CANON_CLEAN_INSTALL_OLD_REMOVED=0
  AGENT_CANON_CLEAN_INSTALL_ACTIVE=1
  export AGENT_CANON_CLEAN_INSTALL_OLD_CONTAINER \
    AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF \
    AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_ID \
    AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED \
    AGENT_CANON_CLEAN_INSTALL_OLD_REMOVED \
    AGENT_CANON_CLEAN_INSTALL_ACTIVE
  trap '_agent_canon_clean_install_exit' EXIT

  if ((old_container_present == 1)); then
    if ! "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$old_container_id" >/dev/null; then
      _agent_canon_json_error replacement_stop_failed "old resident could not be stopped"
      return 2
    fi
    AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED=1
    export AGENT_CANON_CLEAN_INSTALL_OLD_QUIESCED
    if ! "$AGENT_CANON_DOCKER_CMD" rm "$old_container_id" >/dev/null; then
      _agent_canon_json_error replacement_remove_failed "old resident could not be removed"
      return 2
    fi
    AGENT_CANON_CLEAN_INSTALL_OLD_REMOVED=1
    export AGENT_CANON_CLEAN_INSTALL_OLD_REMOVED
  fi
  _agent_canon_prepare_clean_install

  AGENT_CANON_ALLOW_BUILD=1
  export AGENT_CANON_ALLOW_BUILD
  _agent_canon_image "${1:-}"
  local candidate_image_ref=$AGENT_CANON_IMAGE_REF candidate_image_id
  if ! candidate_image_id=$("$AGENT_CANON_DOCKER_CMD" image inspect \
    --format '{{.Id}}' "$candidate_image_ref"); then
    _agent_canon_json_error candidate_image_missing "candidate resident image could not be inspected"
    return 2
  fi
  _agent_canon_replace_resident_locked \
    "$candidate_image_ref" "$candidate_image_id" install 1
}

_agent_canon_install() {
  local requested_ref=${1:-}
  _agent_canon_with_replacement_lock _agent_canon_install_locked "$requested_ref"
}

_agent_canon_replace_resident() {
  local candidate_image_ref=$1 candidate_image_id=$2
  local replacement_operation=${3:-update}
  if [[ -z "$candidate_image_ref" || -z "$candidate_image_id" ]]; then
    _agent_canon_json_error replacement_identity_missing "candidate resident image identity is incomplete"
    return 2
  fi
  _agent_canon_with_replacement_lock _agent_canon_replace_resident_locked \
    "$candidate_image_ref" "$candidate_image_id" "$replacement_operation"
}

_agent_canon_update() {
  local requested_ref=${1:-} candidate_image_ref=${2:-}
  _agent_canon_with_replacement_lock _agent_canon_update_locked \
    "$requested_ref" "$candidate_image_ref"
}

_agent_canon_ensure_start_resident() {
  local container=$(_agent_canon_container_name)
  if "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
    _agent_canon_classify_existing_container "$container"
    _agent_canon_validate_target_manifest "$AGENT_CANON_STATE_ROOT/mounts.tsv"
    if _agent_canon_validate_existing_container "$container" \
      "$AGENT_CANON_STATE_ROOT/mounts.tsv" 1 0 >/dev/null 2>/dev/null; then
      _agent_canon_ensure_container
    else
      # Start has no new image candidate. Reuse the active image through the
      # same serialized replacement path so stale mounts/security are rebuilt
      # from the current manifest before the requested start transition.
      _agent_canon_replace_resident "$AGENT_CANON_IMAGE_REF" \
        "$AGENT_CANON_EXPECTED_IMAGE_ID" start >/dev/null
      printf '%s\n' "$container"
    fi
  else
    _agent_canon_ensure_container
  fi
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
  _agent_canon_volume_copy export private-feedback "$spool" private-feedback
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
  python3 "$AGENT_CANON_REPOSITORY_ROOT/tools/runtime/archive/runtime_log_archive_git.py" \
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

_agent_canon_prepare_global_links() {
  local home_root
  home_root=$(realpath -e -- "$HOME") || return 2
  [[ "$AGENT_CANON_CONTROL_ROOT" == "$home_root" ]] || return 0
  local source_root="$AGENT_CANON_REPOSITORY_ROOT/.codex/personal"
  local skill_source_root="$AGENT_CANON_REPOSITORY_ROOT/agents/skills"
  local manifest="$AGENT_CANON_STATE_ROOT/global-links.tsv"
  local config_target="$home_root/.codex/config.toml"
  local config_source="$source_root/config.toml"
  local transaction="$AGENT_CANON_RUNTIME_ROOT/host-state/.global-links-transaction"
  local stage="$transaction/stage" backup="$transaction/backup"
  local link source resolved mode digest index=0
  local failures=()
  [[ ! -e "$transaction" && ! -L "$transaction" ]] ||
    { _agent_canon_json_error global_link_transaction_exists \
        "global link transaction already exists"; return 2; }
  [[ ! -L "$source_root" && ! -L "$skill_source_root" ]] ||
    { _agent_canon_json_error global_link_source_invalid \
        "global link source directory is a symlink"; return 2; }
  [[ ! -e "$source_root" || -d "$source_root" ]] ||
    { _agent_canon_json_error global_link_source_invalid \
        "global link source directory is not a directory"; return 2; }
  [[ ! -e "$skill_source_root" || -d "$skill_source_root" ]] ||
    { _agent_canon_json_error global_link_source_invalid \
        "global skill source directory is not a directory"; return 2; }
  for source in "$home_root/.codex" "$home_root/.agents" \
    "$home_root/.codex/agents" "$home_root/.agents/skills"; do
    [[ ! -L "$source" ]] ||
      { _agent_canon_json_error global_link_collision \
          "global link parent is a symlink: $source"; return 2; }
    [[ ! -e "$source" || -d "$source" ]] ||
      { _agent_canon_json_error global_link_collision \
          "global link parent is not a directory: $source"; return 2; }
  done
  if [[ -e "$config_source" || -L "$config_source" ]]; then
    [[ -f "$config_source" && ! -L "$config_source" ]] ||
      { _agent_canon_json_error global_link_source_invalid \
          "personal Codex configuration is not a regular file"; return 2; }
  fi
  if [[ -e "$config_target" || -L "$config_target" ]]; then
    if [[ -L "$config_target" ]]; then
      resolved=$(readlink -f -- "$config_target" 2>/dev/null || printf '')
      [[ -f "$config_source" && "$resolved" == "$(realpath -e -- "$config_source")" ]] ||
        failures+=("$config_target")
      mode=$(stat -c '%a' -- "$config_source")
    elif [[ -f "$config_target" ]]; then
      mode=$(stat -c '%a' -- "$config_target")
    else
      failures+=("$config_target")
    fi
  else
    if [[ -f "$config_source" ]]; then
      mode=$(stat -c '%a' -- "$config_source")
    else
      mode=600
    fi
  fi
  shopt -s nullglob
  local -a skill_sources=("$skill_source_root"/*)
  local -a agent_sources=("$AGENT_CANON_REPOSITORY_ROOT/.codex/agents"/*.toml)
  shopt -u nullglob
  for source in "${skill_sources[@]}"; do
    [[ -d "$source" && ! -L "$source" ]] || continue
    link="$home_root/.agents/skills/${source##*/}"
    if [[ -L "$link" ]]; then
      resolved=$(readlink -f -- "$link" 2>/dev/null || printf '')
      [[ "$resolved" == "$(realpath -e -- "$source")" ]] || failures+=("$link")
    elif [[ -e "$link" ]]; then
      failures+=("$link")
    fi
  done
  for source in "${agent_sources[@]}"; do
    [[ -f "$source" && ! -L "$source" ]] || continue
    link="$home_root/.codex/agents/${source##*/}"
    if [[ -L "$link" ]]; then
      resolved=$(readlink -f -- "$link" 2>/dev/null || printf '')
      [[ "$resolved" == "$(realpath -e -- "$source")" ]] || failures+=("$link")
    elif [[ -e "$link" ]]; then
      failures+=("$link")
    fi
  done
  ((${#failures[@]} == 0)) ||
    { _agent_canon_json_error global_link_collision \
        "global link install preserved collisions: ${failures[*]}"; return 2; }

  mkdir -p -- "$stage" "$backup" ||
    _agent_canon_json_error global_link_transaction_failed \
      "global link transaction could not be staged"
  chmod 700 "$transaction" "$stage" "$backup"
  : > "$transaction/paths.tsv"
  : > "$transaction/targets.tsv"
  if [[ -e "$manifest" || -L "$manifest" ]]; then
    [[ -f "$manifest" && ! -L "$manifest" ]] ||
      _agent_canon_json_error global_link_manifest_invalid \
        "global link manifest is not a regular file"
    cp -a -- "$manifest" "$backup/manifest" ||
      _agent_canon_json_error global_link_transaction_failed \
        "global link manifest backup failed"
    printf 'present\tmanifest\n' >> "$transaction/paths.tsv"
  else
    printf 'absent\tmanifest\n' >> "$transaction/paths.tsv"
  fi
  for source in "$config_source" "$config_target"; do
    local key
    if [[ "$source" == "$config_source" ]]; then key=config-source; else key=config-target; fi
    if [[ -e "$source" || -L "$source" ]]; then
      cp -a -- "$source" "$backup/$key" ||
        _agent_canon_json_error global_link_transaction_failed \
          "global link backup failed: $source"
      printf 'present\t%s\n' "$key" >> "$transaction/paths.tsv"
    else
      printf 'absent\t%s\n' "$key" >> "$transaction/paths.tsv"
    fi
  done
  index=0
  for source in "${skill_sources[@]}"; do
    [[ -d "$source" && ! -L "$source" ]] || continue
    link="$home_root/.agents/skills/${source##*/}"
    index=$((index + 1))
    if [[ -e "$link" || -L "$link" ]]; then
      cp -a -- "$link" "$backup/link-$index" ||
        _agent_canon_json_error global_link_transaction_failed \
          "global link backup failed: $link"
      printf 'present\tlink-%s\n' "$index" >> "$transaction/paths.tsv"
    else
      printf 'absent\tlink-%s\n' "$index" >> "$transaction/paths.tsv"
    fi
    printf 'link-%s\t%s\n' "$index" "$link" >> "$transaction/targets.tsv"
  done
  for source in "${agent_sources[@]}"; do
    [[ -f "$source" && ! -L "$source" ]] || continue
    link="$home_root/.codex/agents/${source##*/}"
    index=$((index + 1))
    if [[ -e "$link" || -L "$link" ]]; then
      cp -a -- "$link" "$backup/link-$index" ||
        _agent_canon_json_error global_link_transaction_failed \
          "global link backup failed: $link"
      printf 'present\tlink-%s\n' "$index" >> "$transaction/paths.tsv"
    else
      printf 'absent\tlink-%s\n' "$index" >> "$transaction/paths.tsv"
    fi
    printf 'link-%s\t%s\n' "$index" "$link" >> "$transaction/targets.tsv"
  done
  if [[ -e "$config_target" && ! -L "$config_target" ]]; then
    cp -a -- "$config_target" "$stage/config-source" ||
      _agent_canon_json_error global_link_transaction_failed \
        "regular Codex configuration could not be staged"
    chmod "$mode" "$stage/config-source"
    printf '1\n' > "$transaction/update-source"
  elif [[ ! -e "$config_source" ]]; then
    printf '# AgentCanon personal Codex configuration.\n' > "$stage/config-source"
    chmod 600 "$stage/config-source"
    printf '1\n' > "$transaction/update-source"
  else
    printf '0\n' > "$transaction/update-source"
  fi
  {
    printf 'schema\tagent-canon.global-links.v1\n'
    digest=$(_agent_canon_sha256 "$stage/config-source" 2>/dev/null ||
      _agent_canon_sha256 "$config_source")
    printf 'config\t%s\t%s\t%s\t%s\n' "$config_target" "$config_source" "$mode" "$digest"
    for source in "${skill_sources[@]}"; do
      [[ -d "$source" && ! -L "$source" ]] || continue
      printf 'link\t%s/.agents/skills/%s\t%s\n' "$home_root" "${source##*/}" "$source"
    done
    for source in "${agent_sources[@]}"; do
      [[ -f "$source" && ! -L "$source" ]] || continue
      printf 'link\t%s/.codex/agents/%s\t%s\n' "$home_root" "${source##*/}" "$source"
    done
  } > "$stage/global-links.tsv" ||
    _agent_canon_json_error global_link_transaction_failed \
      "global link manifest could not be staged"
  chmod 600 "$stage/global-links.tsv" "$transaction/paths.tsv" "$transaction/update-source"
  AGENT_CANON_GLOBAL_LINK_TRANSACTION_ROOT=$transaction
  AGENT_CANON_GLOBAL_LINK_TRANSACTION_ACTIVE=1
  export AGENT_CANON_GLOBAL_LINK_TRANSACTION_ROOT AGENT_CANON_GLOBAL_LINK_TRANSACTION_ACTIVE
}

_agent_canon_restore_global_links() {
  local transaction=${AGENT_CANON_GLOBAL_LINK_TRANSACTION_ROOT:-$AGENT_CANON_RUNTIME_ROOT/host-state/.global-links-transaction}
  local backup="$transaction/backup" presence key target restore_rc=0
  [[ -d "$transaction" && ! -L "$transaction" ]] || return 0
  [[ -f "$transaction/paths.tsv" && ! -L "$transaction/paths.tsv" ]] || return 2
  while IFS=$'\t' read -r presence key; do
    case "$key" in
      manifest) target="$AGENT_CANON_STATE_ROOT/global-links.tsv" ;;
      config-source) target="$AGENT_CANON_REPOSITORY_ROOT/.codex/personal/config.toml" ;;
      config-target) target="$(realpath -e -- "$HOME")/.codex/config.toml" ;;
      link-*)
        target=$(awk -F $'\t' -v backup_key="$key" '$1 == backup_key { print $2; exit }' "$transaction/targets.tsv" 2>/dev/null || printf '')
        ;;
      *) restore_rc=2; continue ;;
    esac
    if [[ -e "$target" || -L "$target" ]]; then
      rm -rf -- "$target" || restore_rc=2
    fi
    if [[ "$presence" == present ]]; then
      [[ -e "$backup/$key" || -L "$backup/$key" ]] || { restore_rc=2; continue; }
      cp -a -- "$backup/$key" "$target" || restore_rc=2
    elif [[ "$presence" != absent ]]; then
      restore_rc=2
    fi
  done < "$transaction/paths.tsv"
  if ((restore_rc == 0)); then
    rm -rf -- "$transaction" || restore_rc=2
    unset AGENT_CANON_GLOBAL_LINK_TRANSACTION_ROOT AGENT_CANON_GLOBAL_LINK_TRANSACTION_ACTIVE
  fi
  return "$restore_rc"
}

_agent_canon_commit_global_links() {
  local transaction=${AGENT_CANON_GLOBAL_LINK_TRANSACTION_ROOT:-$AGENT_CANON_RUNTIME_ROOT/host-state/.global-links-transaction}
  [[ ! -e "$transaction" && ! -L "$transaction" ]] && {
    unset AGENT_CANON_GLOBAL_LINK_TRANSACTION_ROOT AGENT_CANON_GLOBAL_LINK_TRANSACTION_ACTIVE
    return 0
  }
  if [[ "${AGENT_CANON_TEST_GLOBAL_LINK_COMMIT_FAIL:-0}" == 1 ]] ||
     ! rm -rf -- "$transaction" ||
     [[ -e "$transaction" || -L "$transaction" ]]; then
    _agent_canon_json_error rollback_failed \
      "global-link transaction backup could not be released"
    return 2
  fi
  unset AGENT_CANON_GLOBAL_LINK_TRANSACTION_ROOT AGENT_CANON_GLOBAL_LINK_TRANSACTION_ACTIVE
}

_agent_canon_apply_global_links() {
  local transaction=${AGENT_CANON_GLOBAL_LINK_TRANSACTION_ROOT:-} stage backup
  local home_root source_root config_source config_target manifest key target source
  [[ -n "$transaction" && -d "$transaction" && ! -L "$transaction" ]] || return 2
  stage="$transaction/stage"
  backup="$transaction/backup"
  home_root=$(realpath -e -- "$HOME") || return 2
  source_root="$AGENT_CANON_REPOSITORY_ROOT/.codex/personal"
  config_source="$source_root/config.toml"
  config_target="$home_root/.codex/config.toml"
  manifest="$AGENT_CANON_STATE_ROOT/global-links.tsv"
  mkdir -p -- "$home_root/.agents/skills" "$home_root/.codex/agents" "$source_root" || {
    _agent_canon_restore_global_links
    return 2
  }
  if [[ "$(<"$transaction/update-source")" == 1 ]]; then
    cp -a -- "$stage/config-source" "$config_source" || {
      _agent_canon_restore_global_links
      return 2
    }
  fi
  if [[ -e "$config_target" || -L "$config_target" ]]; then
    if [[ -L "$config_target" ]]; then
      resolved=$(readlink -f -- "$config_target" 2>/dev/null || printf '')
      [[ "$resolved" == "$(realpath -e -- "$config_source")" ]] || {
        _agent_canon_restore_global_links
        return 2
      }
    else
      rm -f -- "$config_target" || {
        _agent_canon_restore_global_links
        return 2
      }
      ln -s -- "$config_source" "$config_target" || {
        _agent_canon_restore_global_links
        return 2
      }
    fi
  else
    ln -s -- "$config_source" "$config_target" || {
      _agent_canon_restore_global_links
      return 2
    }
  fi
  while IFS=$'\t' read -r key target source; do
    [[ "$key" == link ]] || continue
    if [[ -L "$target" ]]; then
      resolved=$(readlink -f -- "$target" 2>/dev/null || printf '')
      [[ "$resolved" == "$(realpath -e -- "$source")" ]] || {
        _agent_canon_restore_global_links
        return 2
      }
    elif [[ -e "$target" ]]; then
      _agent_canon_restore_global_links
      return 2
    else
      ln -s -- "$source" "$target" || {
        _agent_canon_restore_global_links
        return 2
      }
    fi
  done < "$stage/global-links.tsv"
  mv -f -- "$stage/global-links.tsv" "$manifest" || {
    _agent_canon_restore_global_links
    return 2
  }
  return 0
}

_agent_canon_install_global_links() {
  _agent_canon_prepare_global_links || return $?
  [[ "${AGENT_CANON_GLOBAL_LINK_TRANSACTION_ACTIVE:-0}" == 1 ]] || return 0
  _agent_canon_apply_global_links
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
  [[ ${#command_args[@]} -gt 0 ]] || { _agent_canon_usage >&2; return 64; }
  local operation=${command_args[0]} image_ref=
  if [[ "$operation" == sync ]]; then
    local sync_request sync_request_rc
    if sync_request=$(_agent_canon_sync_request_metadata); then
      :
    else
      sync_request_rc=$?
      return "$sync_request_rc"
    fi
    local sync_root sync_remote sync_branch sync_remote_url sync_head sync_tree
    IFS=$'\t' read -r sync_root sync_remote sync_branch sync_remote_url sync_head sync_tree <<<"$sync_request"
    AGENT_CANON_REPOSITORY_ROOT=$sync_root
    AGENT_CANON_SYNC_INITIAL_REMOTE=$sync_remote
    AGENT_CANON_SYNC_INITIAL_BRANCH=$sync_branch
    AGENT_CANON_SYNC_INITIAL_REMOTE_URL=$sync_remote_url
    AGENT_CANON_SYNC_INITIAL_HEAD=$sync_head
    AGENT_CANON_SYNC_INITIAL_TREE=$sync_tree
  fi
  [[ -n "$AGENT_CANON_RUNTIME_ROOT" ]] || AGENT_CANON_RUNTIME_ROOT="$AGENT_CANON_REPOSITORY_ROOT/.runtime"
  _agent_canon_validate_roots
  local source_sync_alignment=
  if [[ "$operation" == install ]]; then
    local source_sync_rc
    if source_sync_alignment=$(_agent_canon_install_source_admission \
      "$AGENT_CANON_REPOSITORY_ROOT"); then
      :
    else
      source_sync_rc=$?
      return "$source_sync_rc"
    fi
  fi
  AGENT_CANON_DOCKER_CMD=${AGENT_CANON_DOCKER:-docker}
  export AGENT_CANON_REPOSITORY_ROOT AGENT_CANON_CONTROL_ROOT AGENT_CANON_RUNTIME_ROOT
  if ! command -v "$AGENT_CANON_DOCKER_CMD" >/dev/null 2>&1 &&
     [[ ! -x "$AGENT_CANON_DOCKER_CMD" ]]; then
    _agent_canon_json_error runtime_unavailable "Docker executable is unavailable"
  fi
  if [[ "$operation" == update ]]; then
    # Ownership is resolved before image build or runtime-state preparation.
    # A foreign collision therefore cannot trigger any candidate build or
    # host-state mutation.
    local preflight_container=$(_agent_canon_container_name)
    if "$AGENT_CANON_DOCKER_CMD" container inspect "$preflight_container" >/dev/null 2>&1; then
      _agent_canon_classify_existing_container "$preflight_container"
    fi
  fi
  if [[ "$operation" == gc && "${command_args[1]:-}" == --dry-run ]]; then
    # A preview is read-only: dispatch before host-runtime preparation, which
    # creates directories, files, modes, and the normal replacement lock.
    AGENT_CANON_STATE_ROOT="$AGENT_CANON_RUNTIME_ROOT/container-state"
    export AGENT_CANON_STATE_ROOT
    _agent_canon_gc
    return $?
  fi
  _agent_canon_prepare_host_runtime
  if [[ -n "$source_sync_alignment" ]]; then
    local source_sync_code source_sync_head source_sync_tree source_sync_remote_url
    IFS=$'\t' read -r source_sync_code source_sync_head source_sync_tree source_sync_remote_url \
      <<<"$source_sync_alignment"
    if ! _agent_canon_source_sync_write success "$source_sync_code" \
      "$AGENT_CANON_REPOSITORY_ROOT" "$source_sync_head" "$source_sync_tree" origin \
      "$source_sync_remote_url" main "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"; then
      _agent_canon_json_error source_sync_state_write_failed \
        "aligned source-sync state could not be atomically published"
    fi
  fi
  if [[ "$operation" == update ]]; then
    # mounts.tsv is the host-owned projection consumed before the resident
    # controller runs.  Drop only syntactically valid target rows whose
    # source is already gone, so candidate creation can converge instead of
    # failing on stale derived state.
    _agent_canon_prune_stale_target_manifest
  fi
  local index
  for index in "${!command_args[@]}"; do
    if [[ "${command_args[index]}" == --image-ref && $((index + 1)) -lt ${#command_args[@]} ]]; then
      image_ref=${command_args[index+1]}
    fi
  done
  case "$operation" in
    gc)
      # Docker resource reconciliation is host-owned and serialized with
      # resident replacement.  Do not create/adopt a container or delegate a
      # second cleanup implementation to the resident controller.
      _agent_canon_gc
      return $?
      ;;
    status)
      local container=$(_agent_canon_container_name)
      local running health resident_drift=false
      if [[ -f "$AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv" ]] ||
         "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
        _agent_canon_use_active_image "$container"
        if "$AGENT_CANON_DOCKER_CMD" container inspect "$container" >/dev/null 2>&1; then
          _agent_canon_classify_existing_container "$container"
          if _agent_canon_validate_existing_container "$container" \
            "$AGENT_CANON_STATE_ROOT/mounts.tsv" 1 0 >/dev/null 2>/dev/null; then
            :
          else
            resident_drift=true
          fi
        fi
      fi
      running=$("$AGENT_CANON_DOCKER_CMD" container inspect --format '{{.State.Running}}' "$container" 2>/dev/null || printf false)
      health=$("$AGENT_CANON_DOCKER_CMD" container inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$container" 2>/dev/null || printf absent)
      running=${running//$'\n'/}
      health=${health//$'\n'/}
      local source_sync_json
      if ! source_sync_json=$(_agent_canon_source_sync_json); then
        source_sync_json=null
      fi
      printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"status","container":{"name":"%s","running":%s,"health":"%s","drift":%s},"runtime_root":"%s","source_sync":%s}\n' \
        "$container" "$running" "$health" "$resident_drift" "$AGENT_CANON_RUNTIME_ROOT" "$source_sync_json"
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
      local state_volume="agent-canon-runtime-$(_agent_canon_control_digest)"
      if "$AGENT_CANON_DOCKER_CMD" volume inspect "$state_volume" >/dev/null 2>&1; then
        _agent_canon_state_volume_labels_match "$state_volume" ||
          _agent_canon_json_error uninstall_volume_ownership_mismatch \
            "controller state volume does not have the exact AgentCanon ownership labels"
        _agent_canon_probe_state_volume "$state_volume" ||
          _agent_canon_json_error uninstall_volume_marker_invalid \
            "controller state volume marker or access contract is invalid"
        if ! "$AGENT_CANON_DOCKER_CMD" volume rm "$state_volume" >/dev/null; then
          _agent_canon_json_error uninstall_volume_remove_failed \
            "Docker could not remove the owned controller state volume"
        fi
        if "$AGENT_CANON_DOCKER_CMD" volume inspect "$state_volume" >/dev/null 2>&1; then
          _agent_canon_json_error uninstall_volume_remove_failed \
            "owned controller state volume remains after removal"
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
      # Do not use if/|| around the install transaction. Bash suppresses
      # errexit for every function and subshell reached from that context,
      # which would let a failed phase continue into later lifecycle work.
      local install_rc
      _agent_canon_install "$image_ref"
      install_rc=$?
      ((install_rc == 0)) || return "$install_rc"
      _agent_canon_finish_clean_install
      return 0
      ;;
    update)
      AGENT_CANON_ALLOW_BUILD=1
      AGENT_CANON_FORCE_BUILD=1
      export AGENT_CANON_ALLOW_BUILD AGENT_CANON_FORCE_BUILD
      _agent_canon_image_reference "$image_ref"
      _agent_canon_update "$image_ref" "$AGENT_CANON_IMAGE_REF"
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
      AGENT_CANON_ROLLBACK_MOUNTS_FILE="$AGENT_CANON_STATE_ROOT/rollback-mounts.tsv"
      export AGENT_CANON_CURRENT_IMAGE_ID AGENT_CANON_CURRENT_IMAGE_REF AGENT_CANON_RESTORE_IMAGE_ID AGENT_CANON_RESTORE_IMAGE_REF AGENT_CANON_ROLLBACK_MOUNTS_FILE
      if ! _agent_canon_run_controller "$rollback_candidate" rollback >/dev/null; then
        unset AGENT_CANON_CURRENT_IMAGE_ID AGENT_CANON_CURRENT_IMAGE_REF AGENT_CANON_RESTORE_IMAGE_ID AGENT_CANON_RESTORE_IMAGE_REF
        AGENT_CANON_ROLLBACK_MOUNTS_FILE="$AGENT_CANON_STATE_ROOT/mounts.tsv"
        AGENT_CANON_RESTORE_TARGETS_FILE="$AGENT_CANON_STATE_ROOT/mounts.tsv"
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
      if ! _agent_canon_publish_controller_projection; then
        _agent_canon_json_error rollback_failed "rollback manifest projection failed"
      fi
      unset AGENT_CANON_CURRENT_IMAGE_ID AGENT_CANON_CURRENT_IMAGE_REF AGENT_CANON_RESTORE_IMAGE_ID AGENT_CANON_RESTORE_IMAGE_REF
      AGENT_CANON_IMAGE_REF=$rollback_image_id
      export AGENT_CANON_IMAGE_REF
      if ! _agent_canon_validate_existing_container "$rollback_candidate" \
        "$AGENT_CANON_STATE_ROOT/mounts.tsv"; then
        AGENT_CANON_ROLLBACK_MOUNTS_FILE="$current_mounts_backup"
        AGENT_CANON_RESTORE_TARGETS_FILE="$AGENT_CANON_STATE_ROOT/mounts.tsv"
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
          AGENT_CANON_RESTORE_TARGETS_FILE="$AGENT_CANON_STATE_ROOT/mounts.tsv"
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
      local target_container=$(_agent_canon_container_name)
      if [[ "$target_action" == add ]] &&
         "$AGENT_CANON_DOCKER_CMD" container inspect "$target_container" >/dev/null 2>&1; then
        # A foreign resident is classified before any registry cleanup.  Only
        # an AgentCanon-owned resident may enter target convergence.
        _agent_canon_classify_existing_container "$target_container"
        _agent_canon_prune_stale_target_manifest
      elif [[ "$target_action" == add ]]; then
        _agent_canon_prune_stale_target_manifest
      fi
      local target_current_image target_current_image_id target_candidate target_rc=0 existing_target_digest=
      existing_target_digest=$(_agent_canon_target_digest "$target_host_root" || true)
      _agent_canon_use_active_image "$target_container"
      target_current_image=$AGENT_CANON_IMAGE_REF
      target_current_image_id=$AGENT_CANON_ACTIVE_IMAGE_ID
      if [[ "$target_action" == add && "$existing_target_digest" == "$target_digest" &&
            -z "${AGENT_CANON_TARGET_PRUNE_DIGESTS:-}" ]] &&
         "$AGENT_CANON_DOCKER_CMD" container inspect "$target_container" >/dev/null 2>&1 &&
         _agent_canon_validate_existing_container "$target_container" \
           "$AGENT_CANON_STATE_ROOT/mounts.tsv" 0 >/dev/null 2>/dev/null; then
        printf '{"schema":"agent-canon.bootstrap-receipt.v2","status":"ok","operation":"target_add","code":"target_unchanged","changed":false,"target_digest":"%s"}\n' \
          "$target_digest"
        return 0
      fi
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
        # Target add can repair owned resident drift (including stale mounts),
        # but ownership was already classified above.  Full configuration
        # readback remains the fast no-op gate and is not a precondition for
        # replacement.
        if _agent_canon_validate_existing_container "$target_container" \
          "$AGENT_CANON_STATE_ROOT/mounts.tsv" 0 >/dev/null 2>/dev/null; then
          :
        fi
        "$AGENT_CANON_DOCKER_CMD" stop --time 10 "$target_container" >/dev/null
        "$AGENT_CANON_DOCKER_CMD" rm "$target_container" >/dev/null
      fi
      if target_candidate=$(_agent_canon_ensure_container); then
        :
      else
        target_rc=$?
        unset AGENT_CANON_TARGET_PENDING_SOURCE AGENT_CANON_TARGET_PENDING_DIGEST
        if [[ -n "$target_current_image_id" ]]; then
          AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF=$target_current_image
          export AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF
          if ! _agent_canon_restore_candidate_failure "$target_container" \
            "$target_current_image_id" "$target_current_image_id"; then
            _agent_canon_json_error rollback_failed \
              "target mount replacement recovery was incomplete"
            return 2
          fi
          unset AGENT_CANON_CLEAN_INSTALL_OLD_IMAGE_REF
        fi
        unset AGENT_CANON_TARGET_HOST_ROOT AGENT_CANON_TARGET_CONTAINER_ROOT
        unset AGENT_CANON_TARGET_DIGEST
        return "$target_rc"
      fi
      command_args=("target" "$target_action" --root "$target_container_root" --mode read-only)
      AGENT_CANON_TARGET_HOST_ROOT=$target_host_root
      AGENT_CANON_TARGET_CONTAINER_ROOT=$target_container_root
      AGENT_CANON_TARGET_DIGEST=$target_digest
      export AGENT_CANON_TARGET_HOST_ROOT AGENT_CANON_TARGET_CONTAINER_ROOT AGENT_CANON_TARGET_DIGEST
      _agent_canon_run_controller "$target_candidate" "${command_args[@]}" || target_rc=$?
      if ((target_rc == 0)); then
        _agent_canon_publish_controller_projection || target_rc=$?
      fi
      # The pending bind exists only while the candidate is being created. The
      # resident controller has now committed the target into mounts.tsv, so
      # do not let the pre-create input participate in readback a second time.
      unset AGENT_CANON_TARGET_PENDING_SOURCE AGENT_CANON_TARGET_PENDING_DIGEST
      if ((target_rc == 0)); then
        # The resident has committed the host-source/container-target record.
        # Read back the complete mount set once from the host Docker boundary;
        # this confirms that the resident-side /targets/<digest> verification
        # was backed by the bind mount that the host requested.
        if _agent_canon_validate_existing_container "$target_candidate" \
          "$AGENT_CANON_STATE_ROOT/mounts.tsv"; then
          :
        else
          target_rc=$?
        fi
      fi
      if ((target_rc != 0)) && [[ -n "$target_current_image_id" ]]; then
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
      _agent_canon_volume_copy export codex-home "$AGENT_CANON_STATE_ROOT/codex-home"
      _agent_canon_sync_personal_skill_view "$codex_container"
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
      _agent_canon_volume_copy import codex-home "$AGENT_CANON_STATE_ROOT/codex-home"
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
        _agent_canon_volume_copy export eval "$AGENT_CANON_STATE_ROOT/spool" "$eval_run_id"
        _agent_canon_archive_eval_sync "$eval_run_id"
        return $?
      fi
      ;;&
    install|update|start|stop|rollback|uninstall|target|tool|template|task|gc|eval|exec)
      if [[ "$operation" != install && "$operation" != update ]]; then
        _agent_canon_use_active_image "$(_agent_canon_container_name)"
      fi
      local container
      if [[ "$operation" == start ]]; then
        container=$(_agent_canon_ensure_start_resident)
      else
        container=$(_agent_canon_ensure_container)
      fi
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
        python3 /usr/local/share/agent-canon/runtime/tools/runtime/container/bootstrap_runtime.py \
        --container-control \
        --repository-root /usr/local/share/agent-canon/runtime \
        --control-parent-root /var/lib/agent-canon \
        --runtime-root /var/lib/agent-canon/runtime \
        "${command_args[@]}" >"$output_file" 2>"$error_file" || rc=$?
      cat "$output_file"
      cat "$error_file" >&2
      rm -f -- "$output_file" "$error_file"
      if ((rc == 0)) && [[ "$operation" == eval && "${command_args[1]:-}" == collect ]]; then
        local eval_collect_run_id= eval_collect_index=2
        while ((eval_collect_index < ${#command_args[@]})); do
          if [[ "${command_args[eval_collect_index]}" == --run-id &&
                $((eval_collect_index + 1)) -lt ${#command_args[@]} ]]; then
            eval_collect_run_id=${command_args[eval_collect_index+1]}
            break
          fi
          eval_collect_index=$((eval_collect_index + 1))
        done
        [[ "$eval_collect_run_id" =~ ^[A-Za-z0-9_.-]{1,128}$ ]] ||
          _agent_canon_json_error argument_missing "eval collect requires a valid --run-id"
        _agent_canon_volume_copy export eval "$AGENT_CANON_STATE_ROOT/spool" "$eval_collect_run_id" || rc=$?
      fi
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
