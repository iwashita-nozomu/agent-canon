#!/usr/bin/env bash
# @dependency-start
# upstream implementation ./agent_tools/check_dependency_headers.py validates dependency manifests
# upstream implementation ../tests/agent_tools/test_check_dependency_headers.py tests dependency manifest checker
# downstream implementation ../tests/agent_tools/test_dependency_manifest_tools.py root symlink view for manifest tests
# downstream implementation ../tests/agent_tools/test_evaluate_agent_run.py root symlink view for eval tests
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"
REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
DEFAULT_BRANCH="${AGENT_CANON_BRANCH:-main}"
FORCE_RELINK="${AGENT_CANON_FORCE_RELINK:-0}"
PLAN_REMOTE_OVERRIDE_URL="${AGENT_CANON_PLAN_REMOTE_URL:-}"

usage() {
  cat <<EOF
Usage:
  bash tools/sync_agent_canon.sh plan [branch]
  bash tools/sync_agent_canon.sh link-root
  bash tools/sync_agent_canon.sh check
  bash tools/sync_agent_canon.sh snapshot
  bash tools/sync_agent_canon.sh add <remote-url> [branch]
  bash tools/sync_agent_canon.sh pull [branch]
  bash tools/sync_agent_canon.sh ensure-latest [branch]
  bash tools/sync_agent_canon.sh push [branch]
  bash tools/sync_agent_canon.sh status

Environment overrides:
  AGENT_CANON_PREFIX
  AGENT_CANON_REMOTE_NAME
  AGENT_CANON_REMOTE_URL
  AGENT_CANON_BRANCH
  AGENT_CANON_FORCE_RELINK=1
EOF
}

die() {
  echo "sync_agent_canon.sh: $*" >&2
  exit 1
}

require_git_repo() {
  git -C "$ROOT_DIR" rev-parse --show-toplevel >/dev/null 2>&1 || die "repository root not found"
}

require_clean_worktree() {
  if [ -n "$(git -C "$ROOT_DIR" status --short)" ]; then
    die "worktree is dirty; commit or stash changes before subtree operations"
  fi
}

ensure_remote() {
  local remote_url="$1"
  if git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    return
  fi
  git -C "$ROOT_DIR" remote add "$REMOTE_NAME" "$remote_url"
}

require_existing_remote() {
  git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1 || die "remote '$REMOTE_NAME' is not configured"
}

default_remote_url() {
  if [ -n "${AGENT_CANON_REMOTE_URL:-}" ]; then
    echo "$AGENT_CANON_REMOTE_URL"
    return
  fi
  if [ -d "/mnt/git/agent-canon.git" ]; then
    echo "/mnt/git/agent-canon.git"
    return
  fi
  return 0
}

ensure_existing_remote_or_default() {
  local remote_url=""
  if git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    return
  fi
  remote_url="$(default_remote_url)"
  if [ -z "$remote_url" ]; then
    die "remote '$REMOTE_NAME' is not configured; set AGENT_CANON_REMOTE_URL or run 'git remote add $REMOTE_NAME <agent-canon-url>'"
  fi
  git -C "$ROOT_DIR" remote add "$REMOTE_NAME" "$remote_url"
  echo "agent_canon_remote_added=$remote_url"
}

ensure_prefix_exists() {
  [ -d "$ROOT_DIR/$PREFIX" ] || die "prefix '$PREFIX' does not exist"
}

build_link_specs() {
  cat <<EOF
AGENTS.md:${PREFIX}/ROOT_AGENTS.md
agents:${PREFIX}/agents
.agents:${PREFIX}/.agents
.claude:${PREFIX}/.claude
CLAUDE.md:${PREFIX}/CLAUDE.md
.codex/config.toml:../${PREFIX}/.codex/config.toml
.codex/README.md:../${PREFIX}/.codex/README.md
.codex/agents:../${PREFIX}/.codex/agents
.github/AGENTS.md:../${PREFIX}/.github/AGENTS.md
.github/copilot-instructions.md:../${PREFIX}/.github/copilot-instructions.md
documents/BRANCH_SCOPE.md:../${PREFIX}/documents/BRANCH_SCOPE.md
documents/AGENTS_COORDINATION.md:../${PREFIX}/documents/AGENTS_COORDINATION.md
documents/DOCSTRING_GUIDE.md:../${PREFIX}/documents/DOCSTRING_GUIDE.md
documents/FILE_CHECKLIST_OPERATIONS.md:../${PREFIX}/documents/FILE_CHECKLIST_OPERATIONS.md
documents/README.md:../${PREFIX}/documents/README.md
documents/dependency-manifest-design.md:../${PREFIX}/documents/dependency-manifest-design.md
documents/notes-lifecycle.md:../${PREFIX}/documents/notes-lifecycle.md
documents/REVIEW_PROCESS.md:../${PREFIX}/documents/REVIEW_PROCESS.md
documents/SHARED_RUNTIME_SURFACES.md:../${PREFIX}/documents/SHARED_RUNTIME_SURFACES.md
documents/SKILL_IMPLEMENTATION_GUIDE.md:../${PREFIX}/documents/SKILL_IMPLEMENTATION_GUIDE.md
documents/TROUBLESHOOTING.md:../${PREFIX}/documents/TROUBLESHOOTING.md
documents/WORKTREE_SCOPE_TEMPLATE.md:../${PREFIX}/documents/WORKTREE_SCOPE_TEMPLATE.md
documents/agent-canon-subtree-migration.md:../${PREFIX}/documents/agent-canon-subtree-migration.md
documents/coding-conventions-cpp.md:../${PREFIX}/documents/coding-conventions-cpp.md
documents/coding-conventions-experiments.md:../${PREFIX}/documents/coding-conventions-experiments.md
documents/coding-conventions-house-style.md:../${PREFIX}/documents/coding-conventions-house-style.md
documents/coding-conventions-logging.md:../${PREFIX}/documents/coding-conventions-logging.md
documents/coding-conventions-project.md:../${PREFIX}/documents/coding-conventions-project.md
documents/coding-conventions-python.md:../${PREFIX}/documents/coding-conventions-python.md
documents/coding-conventions-reviews.md:../${PREFIX}/documents/coding-conventions-reviews.md
documents/coding-conventions-testing.md:../${PREFIX}/documents/coding-conventions-testing.md
documents/experiment-critical-review.md:../${PREFIX}/documents/experiment-critical-review.md
documents/experiment-registry.md:../${PREFIX}/documents/experiment-registry.md
documents/experiment-report-style.md:../${PREFIX}/documents/experiment-report-style.md
documents/experiment_runner.md:../${PREFIX}/documents/experiment_runner.md
documents/cpp-build-layout.md:../${PREFIX}/documents/cpp-build-layout.md
documents/linux-wsl-host-requirements.md:../${PREFIX}/documents/linux-wsl-host-requirements.md
documents/remote-execution-repo-contract.md:../${PREFIX}/documents/remote-execution-repo-contract.md
documents/server-host-contract.md:../${PREFIX}/documents/server-host-contract.md
documents/template-bootstrap.md:../${PREFIX}/documents/template-bootstrap.md
documents/worktree-lifecycle.md:../${PREFIX}/documents/worktree-lifecycle.md
documents/conventions/README.md:../../${PREFIX}/documents/conventions/README.md
documents/conventions/common/01_principles.md:../../../${PREFIX}/documents/conventions/common/01_principles.md
documents/conventions/common/02_naming.md:../../../${PREFIX}/documents/conventions/common/02_naming.md
documents/conventions/common/03_comments.md:../../../${PREFIX}/documents/conventions/common/03_comments.md
documents/conventions/common/04_operators.md:../../../${PREFIX}/documents/conventions/common/04_operators.md
documents/conventions/common/05_docs.md:../../../${PREFIX}/documents/conventions/common/05_docs.md
documents/conventions/python/01_scope.md:../../../${PREFIX}/documents/conventions/python/01_scope.md
documents/conventions/python/04_type_annotations.md:../../../${PREFIX}/documents/conventions/python/04_type_annotations.md
documents/conventions/python/06_comments.md:../../../${PREFIX}/documents/conventions/python/06_comments.md
documents/conventions/python/07_type_checker.md:../../../${PREFIX}/documents/conventions/python/07_type_checker.md
documents/conventions/python/09_file_roles.md:../../../${PREFIX}/documents/conventions/python/09_file_roles.md
documents/conventions/python/11_naming.md:../../../${PREFIX}/documents/conventions/python/11_naming.md
documents/conventions/python/15_jax_rules.md:../../../${PREFIX}/documents/conventions/python/15_jax_rules.md
documents/conventions/python/20_benchmark_policy.md:../../../${PREFIX}/documents/conventions/python/20_benchmark_policy.md
documents/conventions/python/30_experiment_directory_structure.md:../../../${PREFIX}/documents/conventions/python/30_experiment_directory_structure.md
documents/design/README.md:../../${PREFIX}/documents/design/README.md
documents/design/protocols.md:../../${PREFIX}/documents/design/protocols.md
documents/templates/README.md:../../${PREFIX}/documents/templates/README.md
documents/templates/remote_execution_repo.template.toml:../../${PREFIX}/documents/templates/remote_execution_repo.template.toml
documents/templates/remote_execution_target.template.toml:../../${PREFIX}/documents/templates/remote_execution_target.template.toml
documents/templates/server_host_inventory.template.md:../../${PREFIX}/documents/templates/server_host_inventory.template.md
documents/templates/server_runtime_layout.template.toml:../../${PREFIX}/documents/templates/server_runtime_layout.template.toml
documents/tools/README.md:../../${PREFIX}/documents/tools/README.md
documents/tools/TOOLS_DIRECTORY.md:../../${PREFIX}/documents/tools/TOOLS_DIRECTORY.md
memory/README.md:../${PREFIX}/memory/README.md
memory/USER_PREFERENCES.md:../${PREFIX}/memory/USER_PREFERENCES.md
memory/AGENT_PHILOSOPHY.md:../${PREFIX}/memory/AGENT_PHILOSOPHY.md
mcp:${PREFIX}/mcp
notes/experiments/README.md:../../${PREFIX}/notes/experiments/README.md
notes/experiments/REPORT_TEMPLATE.md:../../${PREFIX}/notes/experiments/REPORT_TEMPLATE.md
notes/experiments/results/README.md:../../../${PREFIX}/notes/experiments/results/README.md
notes/branches/README.md:../../${PREFIX}/notes/branches/README.md
notes/branches/BRANCH_NOTE_TEMPLATE.md:../../${PREFIX}/notes/branches/BRANCH_NOTE_TEMPLATE.md
notes/failures/README.md:../../${PREFIX}/notes/failures/README.md
notes/failures/FAILURE_NOTE_TEMPLATE.md:../../${PREFIX}/notes/failures/FAILURE_NOTE_TEMPLATE.md
notes/github-mirror-procedure.md:../${PREFIX}/notes/github-mirror-procedure.md
notes/guardrails/README.md:../../${PREFIX}/notes/guardrails/README.md
notes/guardrails/engineering_avoidances.md:../../${PREFIX}/notes/guardrails/engineering_avoidances.md
notes/knowledge/README.md:../../${PREFIX}/notes/knowledge/README.md
notes/knowledge/KNOWLEDGE_NOTE_TEMPLATE.md:../../${PREFIX}/notes/knowledge/KNOWLEDGE_NOTE_TEMPLATE.md
notes/knowledge/benchmark_levels_analysis.md:../../${PREFIX}/notes/knowledge/benchmark_levels_analysis.md
notes/knowledge/benchmark_vs_experiment.md:../../${PREFIX}/notes/knowledge/benchmark_vs_experiment.md
notes/knowledge/coding_decision_methods.md:../../${PREFIX}/notes/knowledge/coding_decision_methods.md
notes/knowledge/environment_setup.md:../../${PREFIX}/notes/knowledge/environment_setup.md
notes/knowledge/experiment_directory_planning.md:../../${PREFIX}/notes/knowledge/experiment_directory_planning.md
notes/knowledge/experiment_operations.md:../../${PREFIX}/notes/knowledge/experiment_operations.md
notes/knowledge/git_mirroring.md:../../${PREFIX}/notes/knowledge/git_mirroring.md
notes/knowledge/literature_intake.md:../../${PREFIX}/notes/knowledge/literature_intake.md
notes/knowledge/path_resolution.md:../../${PREFIX}/notes/knowledge/path_resolution.md
notes/knowledge/pyright_operations.md:../../${PREFIX}/notes/knowledge/pyright_operations.md
notes/themes/README.md:../../${PREFIX}/notes/themes/README.md
notes/themes/THEME_NOTE_TEMPLATE.md:../../${PREFIX}/notes/themes/THEME_NOTE_TEMPLATE.md
notes/themes/from_another_agent.md:../../${PREFIX}/notes/themes/from_another_agent.md
notes/worktrees/README.md:../../${PREFIX}/notes/worktrees/README.md
notes/worktrees/WORKTREE_LOG_TEMPLATE.md:../../${PREFIX}/notes/worktrees/WORKTREE_LOG_TEMPLATE.md
tests/agent_tools/__init__.py:../../${PREFIX}/tests/agent_tools/__init__.py
tests/agent_tools/test_check_agent_runtime_alignment.py:../../${PREFIX}/tests/agent_tools/test_check_agent_runtime_alignment.py
tests/agent_tools/test_doc_start.py:../../${PREFIX}/tests/agent_tools/test_doc_start.py
tests/agent_tools/test_log_user_preference.py:../../${PREFIX}/tests/agent_tools/test_log_user_preference.py
tests/agent_tools/test_log_agent_learning.py:../../${PREFIX}/tests/agent_tools/test_log_agent_learning.py
tests/agent_tools/test_check_mcp_inventory.py:../../${PREFIX}/tests/agent_tools/test_check_mcp_inventory.py
tests/agent_tools/test_check_dependency_headers.py:../../${PREFIX}/tests/agent_tools/test_check_dependency_headers.py
tests/agent_tools/test_dependency_manifest_tools.py:../../${PREFIX}/tests/agent_tools/test_dependency_manifest_tools.py
tests/agent_tools/test_evaluate_agent_run.py:../../${PREFIX}/tests/agent_tools/test_evaluate_agent_run.py
tests/agent_tools/test_smoke_test_research_perspective_pack.py:../../${PREFIX}/tests/agent_tools/test_smoke_test_research_perspective_pack.py
tests/agent_tools/test_task_start_and_close.py:../../${PREFIX}/tests/agent_tools/test_task_start_and_close.py
tests/agent_tools/test_waterfall_gate_check.py:../../${PREFIX}/tests/agent_tools/test_waterfall_gate_check.py
tests/agent_tools/test_work_log.py:../../${PREFIX}/tests/agent_tools/test_work_log.py
tests/agent_tools/test_worktree_scope_lint.py:../../${PREFIX}/tests/agent_tools/test_worktree_scope_lint.py
tests/tools/test_check_merge_structure.py:../../${PREFIX}/tests/tools/test_check_merge_structure.py
tests/tools/test_check_markdown_math.py:../../${PREFIX}/tests/tools/test_check_markdown_math.py
tests/tools/test_mirror_skill_shims.py:../../${PREFIX}/tests/tools/test_mirror_skill_shims.py
tests/tools/test_run_managed_experiment.py:../../${PREFIX}/tests/tools/test_run_managed_experiment.py
tests/tools/test_run_repo_program.py:../../${PREFIX}/tests/tools/test_run_repo_program.py
tests/tools/test_update_agent_canon.py:../../${PREFIX}/tests/tools/test_update_agent_canon.py
tools:${PREFIX}/tools
EOF
}

build_removed_legacy_paths() {
  cat <<EOF
documents/WORKFLOW_GUIDE.md
documents/academic-writing-workflow.md
documents/adaptive-improvement-workflow.md
documents/agent-canon-pr-workflow.md
documents/agent-learning-workflow.md
documents/experiment-workflow.md
documents/implementation-waterfall-workflow.md
documents/long-form-writing-workflow.md
documents/main-integration-workflow.md
documents/paper-writing-workflow.md
documents/research-workflow.md
documents/workflow-references.md
notes/themes/AGENT_PHILOSOPHY.md
notes/themes/USER_PREFERENCES.md
memory/global
memory/methods
memory/candidates
memory/subagent_loadouts.yaml
EOF
}

build_copy_specs() {
  cat <<EOF
.github/workflows/agent-coordination.yml:${PREFIX}/.github/workflows/agent-coordination.yml
.github/PULL_REQUEST_TEMPLATE/agent_canon.md:${PREFIX}/.github/PULL_REQUEST_TEMPLATE/agent_canon.md
EOF
}

link_path() {
  local path="$1"
  local target="$2"
  local abs_path="$ROOT_DIR/$path"
  rm -rf "$abs_path"
  mkdir -p "$(dirname "$abs_path")"
  ln -s "$target" "$abs_path"
}

copy_path() {
  local path="$1"
  local source="$2"
  local abs_path="$ROOT_DIR/$path"
  local abs_source="$ROOT_DIR/$source"
  [ -e "$abs_source" ] || die "copy source '$source' does not exist"
  rm -rf "$abs_path"
  mkdir -p "$(dirname "$abs_path")"
  cp "$abs_source" "$abs_path"
}

ensure_surface_sync_safe() {
  local force="${1:-0}"
  local -a paths=()
  local status=""
  local spec=""

  if [ "$force" = "1" ] || [ "$FORCE_RELINK" = "1" ]; then
    return
  fi

  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    paths+=("${spec%%:*}")
  done < <(
    {
      build_link_specs
      build_copy_specs
    }
  )
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    paths+=("$path")
  done < <(build_removed_legacy_paths)

  [ "${#paths[@]}" -gt 0 ] || return
  status="$(git -C "$ROOT_DIR" status --short -- "${paths[@]}")"
  if [ -n "$status" ]; then
    echo "$status" >&2
    die "shared surface has uncommitted changes; commit or stash them first, or rerun with AGENT_CANON_FORCE_RELINK=1"
  fi
}

cmd_link_root() {
  local force="${1:-0}"
  ensure_prefix_exists
  ensure_surface_sync_safe "$force"

  local spec=""
  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local target="${spec#*:}"
    link_path "$path" "$target"
  done < <(build_link_specs)

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local source="${spec#*:}"
    copy_path "$path" "$source"
  done < <(build_copy_specs)

  while IFS= read -r path; do
    [ -n "$path" ] || continue
    rm -rf "$ROOT_DIR/$path"
  done < <(build_removed_legacy_paths)
}

cmd_snapshot() {
  cmd_link_root
}

cmd_check() {
  ensure_prefix_exists

  local spec=""
  local failed=0

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local target="${spec#*:}"
    local abs_path="$ROOT_DIR/$path"
    if [ -L "$abs_path" ] && [ "$(readlink "$abs_path")" = "$target" ] && [ -e "$abs_path" ]; then
      continue
    fi
    if [ -L "$abs_path" ] && ! [ -e "$abs_path" ]; then
      echo "link[$path]=broken" >&2
    elif [ -e "$abs_path" ]; then
      echo "link[$path]=drift" >&2
    else
      echo "link[$path]=missing" >&2
    fi
    failed=1
  done < <(build_link_specs)

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local source="${spec#*:}"
    local abs_path="$ROOT_DIR/$path"
    local abs_source="$ROOT_DIR/$source"
    if [ -f "$abs_path" ] && [ -f "$abs_source" ] && cmp -s "$abs_path" "$abs_source"; then
      continue
    fi
    if [ -e "$abs_path" ]; then
      echo "copy[$path]=drift" >&2
    else
      echo "copy[$path]=missing" >&2
    fi
    failed=1
  done < <(build_copy_specs)

  while IFS= read -r path; do
    [ -n "$path" ] || continue
    local abs_path="$ROOT_DIR/$path"
    if [ -e "$abs_path" ] || [ -L "$abs_path" ]; then
      echo "legacy[$path]=present" >&2
      failed=1
    fi
  done < <(build_removed_legacy_paths)

  if [ "$failed" -ne 0 ]; then
    die "shared surface drift detected; run 'bash tools/sync_agent_canon.sh link-root'"
  fi

  echo "shared surface is in sync"
}

stage_sync_paths() {
  local spec=""
  git -C "$ROOT_DIR" add -A -- "$PREFIX"

  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    git -C "$ROOT_DIR" add -A -- "${spec%%:*}"
  done < <(
    {
      build_link_specs
      build_copy_specs
    }
  )
}

commit_sync_paths_if_needed() {
  local remote_sha="$1"
  local method="$2"

  stage_sync_paths
  if git -C "$ROOT_DIR" diff --cached --quiet; then
    return
  fi

  git -C "$ROOT_DIR" commit \
    -m "chore: sync agent-canon snapshot" \
    -m "agent-canon-remote: $remote_sha" \
    -m "agent-canon-update-method: $method" \
    -m "agent-canon-prefix: $PREFIX"
}

find_commit_by_tree() {
  local tree_sha="$1"
  local history_head="$2"
  local commit=""

  while IFS= read -r commit; do
    if [ "$(git -C "$ROOT_DIR" rev-parse "$commit^{tree}")" = "$tree_sha" ]; then
      echo "$commit"
      return
    fi
  done < <(git -C "$ROOT_DIR" rev-list "$history_head")

  return 1
}

materialize_cached_snapshot_diff() {
  local base_sha="$1"
  local remote_sha="$2"
  local status=""
  local path=""

  while IFS= read -r -d '' status && IFS= read -r -d '' path; do
    case "$status" in
      D)
        rm -f "$ROOT_DIR/$PREFIX/$path"
        ;;
      *)
        git -C "$ROOT_DIR" checkout-index -f -u -- "$PREFIX/$path"
        ;;
    esac
  done < <(git -C "$ROOT_DIR" diff --name-status --no-renames -z "$base_sha" "$remote_sha" --)
}

apply_snapshot_diff() {
  local base_sha="$1"
  local remote_sha="$2"

  git -C "$ROOT_DIR" diff --binary "$base_sha" "$remote_sha" -- | git -C "$ROOT_DIR" apply --cached --directory="$PREFIX"
  materialize_cached_snapshot_diff "$base_sha" "$remote_sha"
}

import_fast_forward_snapshot() {
  local local_split="$1"
  local remote_sha="$2"
  local method="${3:-fast_forward_snapshot_import}"

  if ! git -C "$ROOT_DIR" merge-base --is-ancestor "$local_split" "$remote_sha"; then
    echo "agent_canon_snapshot_import=diverged_history"
    die "snapshot import is unsafe because local shared-canon history diverged from '$REMOTE_NAME/$DEFAULT_BRANCH'; update the proposal branch or merge the shared canon changes before running ensure-latest"
  fi

  if git -C "$ROOT_DIR" diff --quiet "$local_split" "$remote_sha" --; then
    echo "agent_canon_latest=already_current_snapshot"
    cmd_link_root 1
    return
  fi

  echo "agent_canon_update_method=$method"
  apply_snapshot_diff "$local_split" "$remote_sha"
  cmd_link_root 1
  commit_sync_paths_if_needed "$remote_sha" "$method"
}

import_snapshot_preferring_tree_match() {
  local local_split="$1"
  local local_tree="$2"
  local remote_sha="$3"
  local method="$4"
  local matched_commit=""

  if git -C "$ROOT_DIR" merge-base --is-ancestor "$local_split" "$remote_sha"; then
    import_fast_forward_snapshot "$local_split" "$remote_sha" "$method"
    return
  fi

  matched_commit="$(find_commit_by_tree "$local_tree" "$remote_sha" || true)"
  if [ -n "$matched_commit" ]; then
    echo "agent_canon_snapshot_import=tree_match_in_remote_history"
    import_fast_forward_snapshot "$matched_commit" "$remote_sha" "$method"
    return
  fi

  echo "agent_canon_snapshot_import=diverged_history"
  die "snapshot import is unsafe because local shared-canon history diverged from '$REMOTE_NAME/$DEFAULT_BRANCH' and the current prefix tree is not present in remote history; update the proposal branch or merge the shared canon changes before running ensure-latest"
}

import_snapshot_from_prefix_tree() {
  local local_tree="$1"
  local remote_sha="$2"
  local method="$3"
  local local_snapshot=""

  if git -C "$ROOT_DIR" diff --quiet "$local_tree" "$remote_sha" --; then
    echo "agent_canon_latest=already_current_tree"
    cmd_link_root 1
    return
  fi

  local_snapshot="$(find_commit_by_tree "$local_tree" "$remote_sha")" || die "git subtree is unavailable and snapshot import is unsafe because the local prefix tree is not present in remote agent-canon history"
  import_fast_forward_snapshot "$local_snapshot" "$remote_sha" "$method"
}

split_prefix_or_empty() {
  git -C "$ROOT_DIR" subtree split --prefix="$PREFIX" HEAD 2>/dev/null || true
}

has_subtree_metadata() {
  git -C "$ROOT_DIR" log --format=%B --grep="git-subtree-dir: $PREFIX" --max-count=1 HEAD >/dev/null 2>&1
}

print_plan_summary() {
  local branch="$1"
  local remote_url="$2"
  local remote_source="$3"
  local remote_sha="$4"
  local remote_tree="$5"
  local local_tree="$6"
  local local_split="$7"
  local subtree_metadata="$8"
  local route="$9"
  local dirty="${10}"
  local requires_clean="${11}"

  echo "agent_canon_plan_branch=$branch"
  if [ -n "$remote_url" ]; then
    echo "agent_canon_plan_remote_url=$remote_url"
  else
    echo "agent_canon_plan_remote_url=<unset>"
  fi
  echo "agent_canon_plan_remote_source=$remote_source"
  if [ -n "$remote_sha" ]; then
    echo "agent_canon_plan_remote_sha=$remote_sha"
    echo "agent_canon_plan_remote_tree=$remote_tree"
  else
    echo "agent_canon_plan_remote_sha=<unavailable>"
    echo "agent_canon_plan_remote_tree=<unavailable>"
  fi
  echo "agent_canon_plan_local_tree=$local_tree"
  if [ -n "$local_split" ]; then
    echo "agent_canon_plan_local_split=$local_split"
  else
    echo "agent_canon_plan_local_split=unavailable"
  fi
  echo "agent_canon_plan_has_subtree_metadata=$subtree_metadata"
  echo "agent_canon_plan_dirty_worktree=$dirty"
  echo "agent_canon_plan_route=$route"
  echo "agent_canon_plan_requires_clean=$requires_clean"
  echo "agent_canon_plan_apply_command=bash tools/sync_agent_canon.sh ensure-latest $branch"
}

cmd_plan() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local local_tree=""
  local local_split=""
  local remote_tree=""
  local remote_sha=""
  local remote_url=""
  local remote_source="unset"
  local subtree_metadata="no"
  local route="remote_unconfigured"
  local requires_clean="no"
  local dirty="no"

  ensure_prefix_exists
  local_tree="$(git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX")"
  local_split="$(split_prefix_or_empty)"
  if has_subtree_metadata; then
    subtree_metadata="yes"
  fi
  if [ -n "$(git -C "$ROOT_DIR" status --short)" ]; then
    dirty="yes"
  fi

  if [ -n "$PLAN_REMOTE_OVERRIDE_URL" ]; then
    remote_url="$PLAN_REMOTE_OVERRIDE_URL"
    remote_source="plan_override"
  elif git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    remote_url="$(git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME")"
    remote_source="configured"
  else
    remote_url="$(default_remote_url)"
    if [ -n "$remote_url" ]; then
      remote_source="default"
    fi
  fi

  if [ -z "$remote_url" ]; then
    print_plan_summary \
      "$branch" "$remote_url" "$remote_source" "$remote_sha" "$remote_tree" "$local_tree" \
      "$local_split" "$subtree_metadata" "$route" "$dirty" "$requires_clean"
    return
  fi

  git -C "$ROOT_DIR" fetch "$remote_url" "$branch"
  remote_sha="$(git -C "$ROOT_DIR" rev-parse FETCH_HEAD)"
  remote_tree="$(git -C "$ROOT_DIR" rev-parse "$remote_sha^{tree}")"

  if [ "$local_tree" = "$remote_tree" ]; then
    route="already_current_tree"
  elif [ -n "$local_split" ] && [ "$local_split" = "$remote_sha" ]; then
    route="already_current_split"
  elif [ -n "$local_split" ] && git -C "$ROOT_DIR" merge-base --is-ancestor "$remote_sha" "$local_split"; then
    route="local_contains_remote"
  elif [ -n "$local_split" ] && git -C "$ROOT_DIR" merge-base --is-ancestor "$local_split" "$remote_sha"; then
    if [ "$subtree_metadata" = "yes" ]; then
      route="subtree_pull"
    else
      route="snapshot_import_no_subtree_metadata"
    fi
    requires_clean="yes"
  elif [ -n "$local_split" ] && find_commit_by_tree "$local_tree" "$remote_sha" >/dev/null 2>&1; then
    route="snapshot_import_tree_match"
    requires_clean="yes"
  elif [ -n "$local_split" ]; then
    route="diverged_local_history"
    requires_clean="yes"
  elif find_commit_by_tree "$local_tree" "$remote_sha" >/dev/null 2>&1; then
    route="snapshot_import_no_subtree"
    requires_clean="yes"
  else
    route="snapshot_import_unsafe_tree_not_in_remote"
    requires_clean="yes"
  fi

  print_plan_summary \
    "$branch" "$remote_url" "$remote_source" "$remote_sha" "$remote_tree" "$local_tree" \
    "$local_split" "$subtree_metadata" "$route" "$dirty" "$requires_clean"
}

pull_or_import_snapshot() {
  local branch="$1"
  local local_split="$2"
  local remote_sha="$3"
  local local_tree="$4"
  local pull_log=""

  if ! has_subtree_metadata; then
    echo "agent_canon_subtree_pull=skipped_no_subtree_metadata"
    import_snapshot_preferring_tree_match "$local_split" "$local_tree" "$remote_sha" "snapshot_import_no_subtree_metadata"
    return
  fi

  pull_log="$(mktemp)"
  if git -C "$ROOT_DIR" subtree pull --prefix="$PREFIX" "$REMOTE_NAME" "$branch" --squash >"$pull_log" 2>&1; then
    cat "$pull_log"
    rm -f "$pull_log"
    echo "agent_canon_update_method=subtree_pull"
    cmd_link_root 1
    commit_sync_paths_if_needed "$remote_sha" "subtree_pull"
    return
  fi

  cat "$pull_log" >&2
  rm -f "$pull_log"
  echo "agent_canon_subtree_pull=failed"
  import_snapshot_preferring_tree_match "$local_split" "$local_tree" "$remote_sha" "snapshot_import_after_subtree_pull_failure"
}

cmd_add() {
  local remote_url="$1"
  local branch="${2:-$DEFAULT_BRANCH}"
  require_clean_worktree
  ensure_remote "$remote_url"
  git -C "$ROOT_DIR" fetch "$REMOTE_NAME" "$branch"
  git -C "$ROOT_DIR" subtree add --prefix="$PREFIX" "$REMOTE_NAME" "$branch" --squash
  cmd_link_root 1
}

cmd_pull() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local local_split=""
  local local_tree=""
  local remote_sha=""

  require_clean_worktree
  ensure_existing_remote_or_default
  git -C "$ROOT_DIR" fetch "$REMOTE_NAME" "$branch"
  remote_sha="$(git -C "$ROOT_DIR" rev-parse FETCH_HEAD)"
  local_tree="$(git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX")"
  local_split="$(split_prefix_or_empty)"
  if [ -n "$local_split" ]; then
    pull_or_import_snapshot "$branch" "$local_split" "$remote_sha" "$local_tree"
    return
  fi

  echo "agent_canon_local_split=unavailable"
  import_snapshot_from_prefix_tree "$(git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX")" "$remote_sha" "snapshot_import_no_subtree"
}

cmd_ensure_latest() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local local_tree=""
  local local_split=""
  local remote_tree=""
  local remote_sha=""

  ensure_prefix_exists
  ensure_existing_remote_or_default
  git -C "$ROOT_DIR" fetch "$REMOTE_NAME" "$branch"
  remote_sha="$(git -C "$ROOT_DIR" rev-parse FETCH_HEAD)"
  remote_tree="$(git -C "$ROOT_DIR" rev-parse "$remote_sha^{tree}")"
  local_tree="$(git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX")"
  local_split="$(split_prefix_or_empty)"

  if [ -n "$local_split" ]; then
    echo "agent_canon_local_split=$local_split"
  else
    echo "agent_canon_local_split=unavailable"
  fi
  echo "agent_canon_remote=$remote_sha"

  if [ "$local_tree" = "$remote_tree" ]; then
    echo "agent_canon_latest=already_current_tree"
    if [ -n "$(git -C "$ROOT_DIR" status --short)" ]; then
      cmd_check
    else
      cmd_link_root 1
    fi
    return
  fi

  if [ -n "$local_split" ] && [ "$local_split" = "$remote_sha" ]; then
    echo "agent_canon_latest=already_current"
    if [ -n "$(git -C "$ROOT_DIR" status --short)" ]; then
      cmd_check
    else
      cmd_link_root 1
    fi
    return
  fi

  if [ -n "$local_split" ] && git -C "$ROOT_DIR" merge-base --is-ancestor "$remote_sha" "$local_split"; then
    echo "agent_canon_latest=local_contains_remote"
    if [ -n "$(git -C "$ROOT_DIR" status --short)" ]; then
      cmd_check
    else
      cmd_link_root 1
    fi
    return
  fi

  require_clean_worktree
  echo "agent_canon_latest=pulling_remote"
  if [ -n "$local_split" ]; then
    pull_or_import_snapshot "$branch" "$local_split" "$remote_sha" "$local_tree"
  else
    import_snapshot_from_prefix_tree "$local_tree" "$remote_sha" "snapshot_import_no_subtree"
  fi
}

cmd_push() {
  local branch="${1:-$DEFAULT_BRANCH}"
  require_clean_worktree
  require_existing_remote
  [ -d "$ROOT_DIR/$PREFIX" ] || die "prefix '$PREFIX' does not exist"
  git -C "$ROOT_DIR" subtree push --prefix="$PREFIX" "$REMOTE_NAME" "$branch"
}

cmd_status() {
  local remote_url=""
  local spec=""
  if git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    remote_url="$(git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME")"
  fi
  echo "repo_root=$ROOT_DIR"
  echo "prefix=$PREFIX"
  echo "remote_name=$REMOTE_NAME"
  echo "default_branch=$DEFAULT_BRANCH"
  if [ -n "$remote_url" ]; then
    echo "remote_url=$remote_url"
  else
    echo "remote_url=<unset>"
  fi
  if [ -d "$ROOT_DIR/$PREFIX" ]; then
    echo "prefix_status=present"
  else
    echo "prefix_status=missing"
  fi
  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local target="${spec#*:}"
    local abs_path="$ROOT_DIR/$path"
    if [ -L "$abs_path" ] && [ "$(readlink "$abs_path")" = "$target" ]; then
      echo "link[$path]=ok"
    elif [ -e "$abs_path" ]; then
      echo "link[$path]=drift"
    else
      echo "link[$path]=missing"
    fi
  done < <(build_link_specs)

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local source="${spec#*:}"
    local abs_path="$ROOT_DIR/$path"
    local abs_source="$ROOT_DIR/$source"
    if [ -f "$abs_path" ] && [ -f "$abs_source" ] && cmp -s "$abs_path" "$abs_source"; then
      echo "copy[$path]=ok"
    elif [ -e "$abs_path" ]; then
      echo "copy[$path]=drift"
    else
      echo "copy[$path]=missing"
    fi
  done < <(build_copy_specs)
}

main() {
  require_git_repo
  cd "$ROOT_DIR"

  local subcommand="${1:-}"
  case "$subcommand" in
    link-root)
      cmd_link_root
      ;;
    plan)
      cmd_plan "${2:-$DEFAULT_BRANCH}"
      ;;
    check)
      cmd_check
      ;;
    snapshot)
      cmd_snapshot
      ;;
    add)
      [ "${2:-}" ] || die "add requires <remote-url>"
      cmd_add "$2" "${3:-$DEFAULT_BRANCH}"
      ;;
    pull)
      cmd_pull "${2:-$DEFAULT_BRANCH}"
      ;;
    ensure-latest)
      cmd_ensure_latest "${2:-$DEFAULT_BRANCH}"
      ;;
    push)
      cmd_push "${2:-$DEFAULT_BRANCH}"
      ;;
    status)
      cmd_status
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      die "unknown subcommand '$subcommand'"
      ;;
  esac
}

main "$@"
