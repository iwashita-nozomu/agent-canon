#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Defines collision-safe Git update materialization predicates shared by AgentCanon plan and apply.
# upstream design ../../documents/agent-canon/agent-canon-update-route.md canonical update materialization acceptance
# downstream implementation ../sync_agent_canon.sh plans and applies parent submodule updates
# downstream implementation ../update_agent_canon.sh merges remote main into a source branch
# @dependency-end

update_materialization_unresolved_conflict() {
  local repo="$1"
  [ -n "$(git -C "$repo" ls-files --unmerged)" ]
}

update_materialization_flagged_entry_differs() {
  local repo="$1"
  local path="$2"
  local index_record=""
  local index_meta=""
  local index_mode=""
  local index_type=""
  local index_oid=""
  local index_stage=""
  local work_path="$repo/$path"
  local actual_mode=""
  local actual_type=""
  local actual_oid=""

  index_record="$(git -C "$repo" ls-files --stage -- "$path")" || return 2
  [ -n "$index_record" ] || return 1
  index_meta="${index_record%%$'\t'*}"
  [ "$index_meta" != "$index_record" ] || return 2
  read -r index_mode index_type index_oid index_stage <<<"$index_meta"
  [ -n "$index_mode" ] && [ -n "$index_type" ] && [ -n "$index_oid" ] || return 2
  [ "${index_stage:-0}" = "0" ] || return 1

  if [ ! -e "$work_path" ] && [ ! -L "$work_path" ]; then
    return 0
  fi

  case "$index_mode" in
    120000)
      [ -L "$work_path" ] || return 0
      actual_type=blob
      [ "$actual_type" = "$index_type" ] || return 0
      actual_oid="$(readlink -n -- "$work_path" | git -C "$repo" hash-object --stdin)" \
        || return 2
      ;;
    160000)
      [ -d "$work_path" ] || return 0
      actual_type=commit
      [ "$actual_type" = "$index_type" ] || return 0
      actual_oid="$(git -C "$work_path" rev-parse --verify 'HEAD^{commit}' 2>/dev/null)" \
        || return 0
      [ "$actual_oid" = "$index_oid" ] || return 0
      [ -z "$(git -C "$work_path" status --porcelain=v1 --untracked-files=all)" ] \
        || return 0
      return 1
      ;;
    100644|100755)
      [ -f "$work_path" ] || return 0
      actual_type=blob
      [ "$actual_type" = "$index_type" ] || return 0
      actual_mode=100644
      [ -x "$work_path" ] && actual_mode=100755
      [ "$actual_mode" = "$index_mode" ] || return 0
      actual_oid="$(git -C "$repo" hash-object --no-filters -- "$work_path")" \
        || return 2
      ;;
    *)
      return 0
      ;;
  esac

  [ "$actual_oid" != "$index_oid" ]
}

update_materialization_flagged_worktree_paths() {
  local repo="$1"
  local flagged_file=""
  local record=""
  local flag=""
  local path=""
  local differs_rc=0

  flagged_file="$(mktemp)" || return 1
  if ! git -C "$repo" ls-files -v -z >"$flagged_file"; then
    rm -f "$flagged_file"
    return 1
  fi
  while IFS= read -r -d '' record; do
    [ -n "$record" ] || continue
    flag="${record:0:1}"
    [ "$flag" != "H" ] || continue
    path="${record:2}"
    update_materialization_flagged_entry_differs "$repo" "$path" \
      || differs_rc=$?
    if [ "$differs_rc" -eq 0 ]; then
      printf '%s\0' "$path"
    elif [ "$differs_rc" -ne 1 ]; then
      rm -f "$flagged_file"
      return "$differs_rc"
    fi
    differs_rc=0
  done <"$flagged_file"
  rm -f "$flagged_file"
}

update_materialization_local_paths() {
  local repo="$1"
  git -C "$repo" diff --no-renames --name-only -z --
  git -C "$repo" diff --cached --no-renames --name-only -z --
  git -C "$repo" diff --name-only --diff-filter=U -z --
  git -C "$repo" ls-files --others --exclude-standard -z
  git -C "$repo" ls-files --others --ignored --exclude-standard -z
  update_materialization_flagged_worktree_paths "$repo"
}

update_materialization_result_tree() {
  local repo="$1"
  local current_sha="$2"
  local remote_sha="$3"
  local merge_output=""
  local merge_rc=0
  local result_tree=""

  if git -C "$repo" merge-base --is-ancestor "$remote_sha" "$current_sha"; then
    git -C "$repo" rev-parse "$current_sha^{tree}"
    return
  fi
  if git -C "$repo" merge-base --is-ancestor "$current_sha" "$remote_sha"; then
    git -C "$repo" rev-parse "$remote_sha^{tree}"
    return
  fi

  if merge_output="$(
    git -C "$repo" merge-tree --write-tree --no-messages "$current_sha" "$remote_sha" 2>/dev/null
  )"; then
    result_tree="${merge_output%%$'\n'*}"
    git -C "$repo" cat-file -e "$result_tree^{tree}" 2>/dev/null || return 3
    printf '%s\n' "$result_tree"
    return
  else
    merge_rc=$?
  fi
  if [ "$merge_rc" -eq 1 ]; then
    return 2
  fi
  return 3
}

update_materialization_write_paths() {
  local repo="$1"
  local current_sha="$2"
  local result_tree="$3"
  git -C "$repo" diff --no-renames --name-only -z "$current_sha^{tree}" "$result_tree" --
}

update_materialization_paths_collide() {
  local local_path="$1"
  local update_path="$2"

  [ "$local_path" = "$update_path" ] \
    || [[ "$local_path" == "$update_path/"* ]] \
    || [[ "$update_path" == "$local_path/"* ]]
}

update_materialization_collision_path() {
  local repo="$1"
  local current_sha="$2"
  local result_tree="$3"
  local local_path=""
  local update_path=""
  local local_paths_file=""
  local update_paths_file=""
  local -a local_paths=()
  local -a update_paths=()

  local_paths_file="$(mktemp)"
  update_paths_file="$(mktemp)"
  if ! update_materialization_local_paths "$repo" >"$local_paths_file"; then
    rm -f "$local_paths_file" "$update_paths_file"
    return 3
  fi
  if ! update_materialization_write_paths \
    "$repo" "$current_sha" "$result_tree" >"$update_paths_file"; then
    rm -f "$local_paths_file" "$update_paths_file"
    return 3
  fi
  mapfile -d '' -t local_paths <"$local_paths_file"
  mapfile -d '' -t update_paths <"$update_paths_file"
  rm -f "$local_paths_file" "$update_paths_file"

  for local_path in "${local_paths[@]}"; do
    for update_path in "${update_paths[@]}"; do
      if update_materialization_paths_collide "$local_path" "$update_path"; then
        printf '%s\n' "$local_path"
        return 0
      fi
    done
  done
  return 1
}

update_materialization_history_state() {
  local repo="$1"
  local current_sha="$2"
  local remote_sha="$3"

  if [ "$current_sha" = "$remote_sha" ]; then
    echo "equal"
  elif git -C "$repo" merge-base --is-ancestor "$remote_sha" "$current_sha"; then
    echo "ahead"
  elif git -C "$repo" merge-base --is-ancestor "$current_sha" "$remote_sha"; then
    echo "behind"
  else
    echo "diverged"
  fi
}
