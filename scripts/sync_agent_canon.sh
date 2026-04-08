#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"
REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
DEFAULT_BRANCH="${AGENT_CANON_BRANCH:-main}"
FORCE_RELINK="${AGENT_CANON_FORCE_RELINK:-0}"

usage() {
  cat <<EOF
Usage:
  bash scripts/sync_agent_canon.sh link-root
  bash scripts/sync_agent_canon.sh check
  bash scripts/sync_agent_canon.sh snapshot
  bash scripts/sync_agent_canon.sh add <remote-url> [branch]
  bash scripts/sync_agent_canon.sh pull [branch]
  bash scripts/sync_agent_canon.sh push [branch]
  bash scripts/sync_agent_canon.sh status

Environment overrides:
  AGENT_CANON_PREFIX
  AGENT_CANON_REMOTE_NAME
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
documents/agent-canon-subtree-migration.md:../${PREFIX}/documents/agent-canon-subtree-migration.md
documents/BRANCH_SCOPE.md:../${PREFIX}/documents/BRANCH_SCOPE.md
documents/AGENTS_COORDINATION.md:../${PREFIX}/documents/AGENTS_COORDINATION.md
documents/academic-writing-workflow.md:../${PREFIX}/documents/academic-writing-workflow.md
documents/adaptive-improvement-workflow.md:../${PREFIX}/documents/adaptive-improvement-workflow.md
documents/notes-lifecycle.md:../${PREFIX}/documents/notes-lifecycle.md
documents/paper-writing-workflow.md:../${PREFIX}/documents/paper-writing-workflow.md
documents/REVIEW_PROCESS.md:../${PREFIX}/documents/REVIEW_PROCESS.md
documents/SHARED_RUNTIME_SURFACES.md:../${PREFIX}/documents/SHARED_RUNTIME_SURFACES.md
documents/SKILL_IMPLEMENTATION_GUIDE.md:../${PREFIX}/documents/SKILL_IMPLEMENTATION_GUIDE.md
documents/WORKFLOW_GUIDE.md:../${PREFIX}/documents/WORKFLOW_GUIDE.md
documents/WORKTREE_SCOPE_TEMPLATE.md:../${PREFIX}/documents/WORKTREE_SCOPE_TEMPLATE.md
documents/coding-conventions-experiments.md:../${PREFIX}/documents/coding-conventions-experiments.md
documents/experiment-critical-review.md:../${PREFIX}/documents/experiment-critical-review.md
documents/experiment-registry.md:../${PREFIX}/documents/experiment-registry.md
documents/experiment-report-style.md:../${PREFIX}/documents/experiment-report-style.md
documents/experiment-workflow.md:../${PREFIX}/documents/experiment-workflow.md
documents/experiment_runner.md:../${PREFIX}/documents/experiment_runner.md
documents/implementation-waterfall-workflow.md:../${PREFIX}/documents/implementation-waterfall-workflow.md
documents/long-form-writing-workflow.md:../${PREFIX}/documents/long-form-writing-workflow.md
documents/main-integration-workflow.md:../${PREFIX}/documents/main-integration-workflow.md
documents/research-workflow.md:../${PREFIX}/documents/research-workflow.md
documents/workflow-references.md:../${PREFIX}/documents/workflow-references.md
documents/worktree-lifecycle.md:../${PREFIX}/documents/worktree-lifecycle.md
documents/conventions/python/20_benchmark_policy.md:../../../${PREFIX}/documents/conventions/python/20_benchmark_policy.md
documents/conventions/python/30_experiment_directory_structure.md:../../../${PREFIX}/documents/conventions/python/30_experiment_directory_structure.md
experiments/README.md:../${PREFIX}/experiments/README.md
experiments/_template:../${PREFIX}/experiments/_template
experiments/report/README.md:../../${PREFIX}/experiments/report/README.md
notes/experiments/README.md:../../${PREFIX}/notes/experiments/README.md
notes/experiments/REPORT_TEMPLATE.md:../../${PREFIX}/notes/experiments/REPORT_TEMPLATE.md
notes/experiments/results/README.md:../../../${PREFIX}/notes/experiments/results/README.md
notes/README.md:../${PREFIX}/notes/README.md
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
tests/agent_tools/test_smoke_test_research_perspective_pack.py:../../${PREFIX}/tests/agent_tools/test_smoke_test_research_perspective_pack.py
tests/tools/test_check_merge_structure.py:../../${PREFIX}/tests/tools/test_check_merge_structure.py
tests/tools/test_mirror_skill_shims.py:../../${PREFIX}/tests/tools/test_mirror_skill_shims.py
tests/tools/test_run_managed_experiment.py:../../${PREFIX}/tests/tools/test_run_managed_experiment.py
scripts/agent_tools:../${PREFIX}/scripts/agent_tools
scripts/check_convention_consistency.py:../${PREFIX}/scripts/check_convention_consistency.py
scripts/check_doc_test_triplet.py:../${PREFIX}/scripts/check_doc_test_triplet.py
scripts/docker_dependency_validator.py:../${PREFIX}/scripts/docker_dependency_validator.py
scripts/push_origin.sh:../${PREFIX}/scripts/push_origin.sh
scripts/requirement_sync_validator.py:../${PREFIX}/scripts/requirement_sync_validator.py
scripts/run_comprehensive_review.sh:../${PREFIX}/scripts/run_comprehensive_review.sh
scripts/run_pytest_with_logs.sh:../${PREFIX}/scripts/run_pytest_with_logs.sh
scripts/ci/check_experiment_registry.py:../../${PREFIX}/scripts/ci/check_experiment_registry.py
scripts/ci/PRE_REVIEW_GUIDE.md:../../${PREFIX}/scripts/ci/PRE_REVIEW_GUIDE.md
scripts/ci/check_docker_build.sh:../../${PREFIX}/scripts/ci/check_docker_build.sh
scripts/ci/check_server_readiness.py:../../${PREFIX}/scripts/ci/check_server_readiness.py
scripts/ci/check_merge_structure.py:../../${PREFIX}/scripts/ci/check_merge_structure.py
scripts/ci/container_runtime.py:../../${PREFIX}/scripts/ci/container_runtime.py
scripts/ci/pre_review.sh:../../${PREFIX}/scripts/ci/pre_review.sh
scripts/ci/run_all_checks.sh:../../${PREFIX}/scripts/ci/run_all_checks.sh
scripts/ci/run_codex_in_repo_container.py:../../${PREFIX}/scripts/ci/run_codex_in_repo_container.py
scripts/ci/run_container_pack.py:../../${PREFIX}/scripts/ci/run_container_pack.py
scripts/ci/run_docs_checks.sh:../../${PREFIX}/scripts/ci/run_docs_checks.sh
scripts/ci/run_in_repo_container.py:../../${PREFIX}/scripts/ci/run_in_repo_container.py
scripts/ci/run_python_in_dockerfile.py:../../${PREFIX}/scripts/ci/run_python_in_dockerfile.py
scripts/experiments/create_experiment_topic.py:../../${PREFIX}/scripts/experiments/create_experiment_topic.py
scripts/experiments/registry_lib.py:../../${PREFIX}/scripts/experiments/registry_lib.py
scripts/experiments/run_managed_experiment.py:../../${PREFIX}/scripts/experiments/run_managed_experiment.py
scripts/experiments/sync_experiment_registry_context.py:../../${PREFIX}/scripts/experiments/sync_experiment_registry_context.py
scripts/setup_worktree.sh:../${PREFIX}/scripts/setup_worktree.sh
scripts/shared/error_handler.py:../../${PREFIX}/scripts/shared/error_handler.py
scripts/sync_agent_canon.sh:../${PREFIX}/scripts/sync_agent_canon.sh
scripts/tools/audit_and_fix_links.py:../../${PREFIX}/scripts/tools/audit_and_fix_links.py
scripts/tools/check_markdown_lint.py:../../${PREFIX}/scripts/tools/check_markdown_lint.py
scripts/tools/check_markdown_math.py:../../${PREFIX}/scripts/tools/check_markdown_math.py
scripts/tools/find_similar_documents.py:../../${PREFIX}/scripts/tools/find_similar_documents.py
scripts/tools/fix_markdown_code_blocks.py:../../${PREFIX}/scripts/tools/fix_markdown_code_blocks.py
scripts/tools/fix_markdown_docs.py:../../${PREFIX}/scripts/tools/fix_markdown_docs.py
scripts/tools/fix_markdown_headers.py:../../${PREFIX}/scripts/tools/fix_markdown_headers.py
scripts/tools/format_markdown.py:../../${PREFIX}/scripts/tools/format_markdown.py
scripts/tools/mirror_skill_shims.py:../../${PREFIX}/scripts/tools/mirror_skill_shims.py
scripts/tools/check_worktree_scopes.sh:../../${PREFIX}/scripts/tools/check_worktree_scopes.sh
scripts/tools/create_worktree.sh:../../${PREFIX}/scripts/tools/create_worktree.sh
scripts/validation/triplet_validator.py:../../${PREFIX}/scripts/validation/triplet_validator.py
scripts/worktree_start.sh:../${PREFIX}/scripts/worktree_start.sh
EOF
}

build_copy_specs() {
  cat <<EOF
.github/workflows/agent-coordination.yml:${PREFIX}/.github/workflows/agent-coordination.yml
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
    if [ -L "$abs_path" ] && [ "$(readlink "$abs_path")" = "$target" ]; then
      continue
    fi
    if [ -e "$abs_path" ]; then
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

  if [ "$failed" -ne 0 ]; then
    die "shared surface drift detected; run 'bash scripts/sync_agent_canon.sh link-root'"
  fi

  echo "shared surface is in sync"
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
  require_clean_worktree
  require_existing_remote
  git -C "$ROOT_DIR" fetch "$REMOTE_NAME" "$branch"
  git -C "$ROOT_DIR" subtree pull --prefix="$PREFIX" "$REMOTE_NAME" "$branch" --squash
  cmd_link_root 1
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
