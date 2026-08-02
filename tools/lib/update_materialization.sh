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

update_materialization_local_uncommitted_paths() {
  local repo="$1"
  git -C "$repo" diff --no-renames --name-only -z --
  git -C "$repo" diff --cached --no-renames --name-only -z --
  git -C "$repo" ls-files --others --exclude-standard -z
}

update_materialization_write_paths() {
  local repo="$1"
  local current_sha="$2"
  local remote_sha="$3"
  local merge_base=""

  if git -C "$repo" merge-base --is-ancestor "$remote_sha" "$current_sha"; then
    return
  fi
  if git -C "$repo" merge-base --is-ancestor "$current_sha" "$remote_sha"; then
    git -C "$repo" diff --no-renames --name-only -z "$current_sha" "$remote_sha" --
    return
  fi
  merge_base="$(git -C "$repo" merge-base "$current_sha" "$remote_sha")"
  git -C "$repo" diff --no-renames --name-only -z "$merge_base" "$remote_sha" --
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
  local remote_sha="$3"
  local local_path=""
  local update_path=""
  local -a local_paths=()
  local -a update_paths=()

  while IFS= read -r -d '' local_path; do
    local_paths+=("$local_path")
  done < <(update_materialization_local_uncommitted_paths "$repo")
  while IFS= read -r -d '' update_path; do
    update_paths+=("$update_path")
  done < <(update_materialization_write_paths "$repo" "$current_sha" "$remote_sha")

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
