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

update_materialization_local_paths() {
  local repo="$1"
  git -C "$repo" diff --no-renames --name-only -z --
  git -C "$repo" diff --cached --no-renames --name-only -z --
  git -C "$repo" diff --name-only --diff-filter=U -z --
  git -C "$repo" ls-files --others --exclude-standard -z
  git -C "$repo" ls-files --others --ignored --exclude-standard -z
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
