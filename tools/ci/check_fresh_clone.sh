#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks fresh-clone bootstrap, AgentCanon update, and runtime surfaces.
# upstream design ../README.md shared automation index
# upstream design ../../documents/agent-canon/agent-canon-update-route.md owns update materialization acceptance
# upstream environment ../../documents/contracts/linux-wsl-host-requirements.md documents host tool requirements for fresh clone checks
# upstream implementation ../agent_tools/update_lifecycle_contract.py owns source projection aggregation and validation.
# upstream implementation ./check_agent_canon_pr.py owns the authoritative G2 materializer API.
# upstream implementation ../agent_tools/github_publish.py owns the authoritative G3 materializer API.
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../lib/repo_paths.sh"
ROOT_DIR="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"
CANON_TOOLS_ROOT="$(agent_canon_source_tools_root "$ROOT_DIR")"
FRESH_CLONE_SOURCE_ROOT="$(git -C "${CANON_TOOLS_ROOT}" rev-parse --show-toplevel)"
AGENT_CANON_BOUNDARY_SCRIPT="${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py"
if [[ "${AGENT_CANON_CHILD_PURPOSE:-}" == "fresh-clone-script" ]]; then
  python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" verify-child \
    --root "${ROOT_DIR}" \
    --source-root "${FRESH_CLONE_SOURCE_ROOT}" \
    --purpose fresh-clone-script \
    --consume >/dev/null
else
  exec python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" exec-parent-bound \
    --root "${ROOT_DIR}" \
    --source-root "${FRESH_CLONE_SOURCE_ROOT}" \
    --purpose fresh-clone-script \
    --issue-handoff \
    -- bash "${BASH_SOURCE[0]}" "$@"
fi
unset AGENT_CANON_CHILD_HANDOFF AGENT_CANON_HANDOFF_AUDIENCE AGENT_CANON_CHILD_PURPOSE

PARENT_TMP_CANDIDATE="${AGENT_CANON_PARENT_TMP_ROOT:-${ROOT_DIR}/.agent-canon/tmp/fresh-clone}"
PARENT_TMP_ROOT="$(python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
  ensure-dir --root "${ROOT_DIR}" --candidate "${PARENT_TMP_CANDIDATE}" --purpose fresh-clone)"
parent_ensure_dir() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    ensure-dir --root "${ROOT_DIR}" --candidate "$1" --purpose "${2:-fresh-clone}"
}
parent_temp_dir() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    temp-dir --root "${ROOT_DIR}" --candidate "$1" --prefix "$2" --purpose "${3:-fresh-clone}"
}
parent_write_file() {
  local candidate="$1" content="${2-}"
  printf '%s' "$content" | python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    write --root "${ROOT_DIR}" --candidate "$candidate" --purpose "${3:-fresh-clone}" >/dev/null
}
parent_capture_subprocess() {
  local candidate="$1"
  shift
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    capture-subprocess --root "${ROOT_DIR}" --candidate "${candidate}" \
    --purpose fresh-clone -- "$@"
}
run_parent_bound_update() {
  local source_root="$1" update_script="$2"
  shift 2
  AGENT_CANON_ACTIVE_REPOSITORY_ROOT="${ROOT_DIR}" \
    python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" exec-parent-bound \
    --root "${ROOT_DIR}" \
    --source-root "${source_root}" \
    --purpose agent-canon-update-script \
    --issue-handoff \
    -- bash "${update_script}" "$@"
}
run_parent_bound_sync() {
  local source_root="$1" sync_script="$2"
  shift 2
  AGENT_CANON_ACTIVE_REPOSITORY_ROOT="${ROOT_DIR}" \
    python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" exec-parent-bound \
    --root "${ROOT_DIR}" \
    --source-root "${source_root}" \
    --purpose agent-canon-sync-script \
    --issue-handoff \
    -- bash "${sync_script}" "$@"
}
capture_parent_bound_update() {
  local candidate="$1" source_root="$2" update_script="$3"
  shift 3
  parent_capture_subprocess "${candidate}" \
    env AGENT_CANON_ACTIVE_REPOSITORY_ROOT="${ROOT_DIR}" \
      python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" exec-parent-bound \
      --root "${ROOT_DIR}" \
      --source-root "${source_root}" \
      --purpose agent-canon-update-script \
      --issue-handoff \
      -- bash "${update_script}" "$@"
}
parent_git_config_add() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    git-config-add --root "${ROOT_DIR}" --candidate "$1" --key "$2" --value "$3" \
    --purpose "${4:-fresh-clone}" >/dev/null
}
parent_remove_file() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    remove-file --root "${ROOT_DIR}" --candidate "$1" --purpose "${2:-fresh-clone}" >/dev/null
}
parent_remove_tree() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    remove-tree --root "${ROOT_DIR}" --candidate "$1" --purpose "${2:-fresh-clone}" >/dev/null
}
parent_copy_file() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    copy --root "${ROOT_DIR}" --source "$1" --candidate "$2" --purpose "${3:-fresh-clone}" >/dev/null
}
parent_copy_tree() {
  local source="$1" candidate="$2"
  shift 2
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    copy-tree --root "${ROOT_DIR}" --source "${source}" --candidate "${candidate}" \
    --exclude .git --exclude .state --exclude .agent-canon "$@" \
    --purpose fresh-clone >/dev/null
}
TMP_DIR="$(parent_temp_dir "${PARENT_TMP_ROOT}" template-fresh-clone)"
TOPIC_ROOT="${TMP_DIR}/workspace/fresh-clone"
CLONE_DIR="${TOPIC_ROOT}/agent-canon"
CLONE_TOOLS_ROOT=""
CLONE_SOURCE_ROOT=""
GIT_TEMP_CONFIG="${TMP_DIR}/safe.directory.gitconfig"
ORIGINAL_GIT_CONFIG_GLOBAL="${GIT_CONFIG_GLOBAL-}"
FRESH_CLONE_CLEANUP_DONE=0

add_safe_directory_to_config() {
  local repo_dir="$1"
  parent_git_config_add "${GIT_TEMP_CONFIG}" safe.directory "${repo_dir}"
}

cleanup() {
  if [ "${FRESH_CLONE_CLEANUP_DONE}" -eq 1 ]; then
    return 0
  fi
  FRESH_CLONE_CLEANUP_DONE=1
  if [ -n "${ORIGINAL_GIT_CONFIG_GLOBAL-}" ]; then
    export GIT_CONFIG_GLOBAL="${ORIGINAL_GIT_CONFIG_GLOBAL}"
  else
    unset GIT_CONFIG_GLOBAL
  fi
  parent_remove_tree "${TMP_DIR}"
}

cleanup_on_signal() {
  local signal_name="$1"
  local exit_code="$2"
  cleanup
  case "${signal_name}" in
    "INT") exit 130 ;;
    "TERM") exit 143 ;;
    "HUP") exit 129 ;;
    *) exit "${exit_code}" ;;
  esac
}

trap cleanup EXIT
trap 'cleanup_on_signal INT 130' INT
trap 'cleanup_on_signal TERM 143' TERM
trap 'cleanup_on_signal HUP 129' HUP

parent_write_file "${GIT_TEMP_CONFIG}" ""
export GIT_CONFIG_GLOBAL="${GIT_TEMP_CONFIG}"
add_safe_directory_to_config "${CLONE_DIR}"

TOPIC_ROOT="$(parent_ensure_dir "${TMP_DIR}/workspace/fresh-clone")"

echo "fresh-clone source: ${ROOT_DIR}"
echo "fresh-clone target: ${CLONE_DIR}"

overlay_current_tree() {
  parent_copy_tree "${ROOT_DIR}" "${CLONE_DIR}" --exclude reports
}

attach_submodule_main_to_staged_pin() {
  local submodule_path="$1"
  local index_entry=""
  local pinned_mode="" pinned_oid="" pinned_stage="" pinned_path=""
  local branch="" head_oid="" main_oid="" upstream="" status=""

  [[ -z "$(git ls-files --unmerged -- "$submodule_path")" ]] || {
    echo "fresh_clone_submodule_attach=unmerged_parent_prefix" >&2
    return 1
  }
  index_entry="$(git ls-files --stage -- "$submodule_path")"
  read -r pinned_mode pinned_oid pinned_stage pinned_path <<<"$index_entry"
  if [[ "$(printf '%s\n' "$index_entry" | awk 'NF { count += 1 } END { print count + 0 }')" -ne 1 \
    || "$pinned_mode" != "160000" || "$pinned_stage" != "0" \
    || "$pinned_path" != "$submodule_path" ]]; then
    echo "fresh_clone_submodule_attach=missing_stage0_gitlink" >&2
    return 1
  fi
  status="$(git -C "$submodule_path" status --short --untracked-files=all)"
  branch="$(git -C "$submodule_path" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  head_oid="$(git -C "$submodule_path" rev-parse HEAD)"
  if [[ -n "$status" || -n "$branch" || "$head_oid" != "$pinned_oid" ]]; then
    echo "fresh_clone_submodule_attach=invalid_initial_state" >&2
    return 1
  fi
  if ! git -C "$submodule_path" show-ref --verify --quiet refs/remotes/origin/main; then
    echo "fresh_clone_submodule_attach=missing_origin_main" >&2
    return 1
  fi
  main_oid="$(git -C "$submodule_path" rev-parse --verify refs/heads/main 2>/dev/null || true)"
  if [[ -n "$main_oid" ]]; then
    git -C "$submodule_path" branch -f main "$pinned_oid" >/dev/null
    git -C "$submodule_path" switch main >/dev/null
  else
    git -C "$submodule_path" switch -c main "$pinned_oid" >/dev/null
  fi
  git -C "$submodule_path" branch --set-upstream-to=origin/main main >/dev/null

  branch="$(git -C "$submodule_path" symbolic-ref --quiet --short HEAD)"
  head_oid="$(git -C "$submodule_path" rev-parse HEAD)"
  upstream="$(git -C "$submodule_path" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}')"
  status="$(git -C "$submodule_path" status --short --untracked-files=all)"
  echo "FRESH_CLONE_SUBMODULE_BRANCH=${branch}"
  echo "FRESH_CLONE_SUBMODULE_HEAD=${head_oid}"
  echo "FRESH_CLONE_SUBMODULE_PIN=${pinned_oid}"
  echo "FRESH_CLONE_SUBMODULE_UPSTREAM=${upstream}"
  if [[ "$branch" != "main" || "$head_oid" != "$pinned_oid" || "$upstream" != "origin/main" \
    || -n "$status" ]]; then
    echo "fresh_clone_submodule_attach=readback_mismatch" >&2
    return 1
  fi
  echo "FRESH_CLONE_SUBMODULE_STATUS=clean"
}

resolve_clone_tools_root_or_fail() {
  local repo_root="$1"
  local resolved=""
  local diagnostics=""

  if ! diagnostics="$(agent_canon_source_tools_root "${repo_root}" 2> >(cat >&2))"; then
    echo "fresh_clone_tools_root=missing" >&2
    echo "fresh_clone_tools_root_reason=agent_canon_source_tools_root_failed" >&2
    printf '%s\n' "${diagnostics}" >&2
    exit 1
  fi
  resolved="${diagnostics}"
  printf '%s' "${resolved}"
}

assert_update_plan_acceptance() {
  local plan_path="$1"
  local allowed_routes="$2"

  grep -Eq "agent_canon_plan_route=(${allowed_routes})" "${plan_path}"
  if grep -q '^agent_canon_plan_prefix_mode=submodule$' "${plan_path}"; then
    grep -q '^agent_canon_plan_requires_clean=no$' "${plan_path}"
    grep -q '^agent_canon_plan_unresolved_merge_conflict=no$' "${plan_path}"
    grep -q '^agent_canon_plan_merge_conflict=no$' "${plan_path}"
    grep -q '^agent_canon_plan_merge_conflict_type=none$' "${plan_path}"
    grep -q '^agent_canon_plan_materialization_collision=no$' "${plan_path}"
    grep -q '^agent_canon_plan_acceptance_predicate=materialization_merge_conflict_or_unpreservable_materialization_collision$' "${plan_path}"
  fi
}

git clone --no-local "${ROOT_DIR}" "${CLONE_DIR}" >/dev/null
overlay_current_tree
cd "${CLONE_DIR}"
if git config -f .gitmodules --get submodule.vendor/agent-canon.path >/dev/null 2>&1; then
  if [ -L "${CLONE_DIR}/vendor/agent-canon" ]; then
    parent_remove_file "${CLONE_DIR}/vendor/agent-canon"
  else
    parent_remove_tree "${CLONE_DIR}/vendor/agent-canon"
  fi
  if ! submodule_init_output="$(git -c protocol.file.allow=always submodule update --init --recursive vendor/agent-canon 2>&1)"; then
    echo "fresh_clone_submodule_init=failed"
    echo "fresh_clone_submodule_init_reason=submodule_update_failed"
    printf '%s\n' "${submodule_init_output}"
    exit 1
  fi
  attach_submodule_main_to_staged_pin "vendor/agent-canon"
fi
CLONE_TOOLS_ROOT="$(resolve_clone_tools_root_or_fail "${CLONE_DIR}")"
CLONE_SOURCE_ROOT="$(git -C "${CLONE_TOOLS_ROOT}" rev-parse --show-toplevel)"
if [[ -n "$(git status --short)" ]]; then
  git config user.name "Fresh Clone Check"
  git config user.email "fresh-clone-check@example.invalid"
  git add -A
  git commit -m "test: overlay current working tree for fresh clone check" >/dev/null
fi

python3 -m json.tool .devcontainer/devcontainer.json >/dev/null

parent_projection_mode=false
if git config -f .gitmodules --get submodule.vendor/agent-canon.path >/dev/null 2>&1 \
  && [ -d vendor/agent-canon ]; then
  parent_projection_mode=true
fi
if [ "$parent_projection_mode" = false ]; then
  runtime_compose_generator="${CLONE_DIR}/.devcontainer/generate-runtime-compose.sh"
  if [ ! -f "${runtime_compose_generator}" ]; then
    runtime_compose_generator="${CLONE_DIR}/vendor/agent-canon/.devcontainer/generate-runtime-compose.sh"
  fi
  test -f "${runtime_compose_generator}"
  AGENT_CANON_DEVCONTAINER_REPO_ROOT=. \
  AGENT_CANON_DOCKER_COMPOSE_OUTPUT=.agent-canon/docker-compose.generated.yml \
    bash "${runtime_compose_generator}" >/dev/null
  python3 - <<'PY'
from __future__ import annotations

from pathlib import Path
import yaml

compose_path = Path(".agent-canon/docker-compose.generated.yml")
data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
assert data["name"].endswith("-devcontainer"), "compose project name missing"
assert "services" in data and "workspace" in data["services"], "workspace service missing"
expected_working_dir = f"/workspace/{Path.cwd().name}"
assert data["services"]["workspace"]["working_dir"] == expected_working_dir
PY
fi

if [ "$parent_projection_mode" = true ]; then
  FRESH_CLONE_RUNTIME_SURFACES=(
    AGENTS.md
    .codex/config.toml
    tools/agent-canon
    vendor/agent-canon
  )
  AGENT_CANON_COMMIT_REQUEST_WORKFLOW_PATH=vendor/agent-canon/agents/workflows/agent-canon-pr-workflow.md
  echo "FRESH_CLONE_PARENT_PROJECTION=enabled"
else
  echo "FRESH_CLONE_AGENT_CANON_MODE=standalone"
  echo "FRESH_CLONE_PARENT_PROJECTION=not-applicable"
  echo "FRESH_CLONE_REPOSITORY_CI_OWNER=repository_ci_job"
  FRESH_CLONE_RUNTIME_SURFACES=(
    AGENTS.md
    agents
    .agents
    .codex/config.toml
    .codex/hooks.json
    agents/workflows/README.md
    agents/workflows/paper-writing-workflow.md
  )
  AGENT_CANON_COMMIT_REQUEST_WORKFLOW_PATH=agents/workflows/agent-canon-pr-workflow.md
  for path in "${FRESH_CLONE_RUNTIME_SURFACES[@]}"; do
    if [ ! -e "${path}" ]; then
      echo "missing runtime surface: ${path}" >&2
      exit 1
    fi
  done

  COMMIT_REQUEST_EVIDENCE_DIGEST="$(sha256sum "${AGENT_CANON_COMMIT_REQUEST_WORKFLOW_PATH}" | awk '{print $1}')"
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:${COMMIT_REQUEST_EVIDENCE_DIGEST}"
  export AGENT_CANON_COMMIT_REQUEST_EVIDENCE
  echo "fresh-clone commit request evidence: ${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}"

  echo "FRESH_CLONE_ACCEPTANCE=pass"
  exit 0
fi

for path in "${FRESH_CLONE_RUNTIME_SURFACES[@]}"; do
  if [ ! -e "${path}" ]; then
    echo "missing runtime surface: ${path}" >&2
    exit 1
  fi
done

COMMIT_REQUEST_EVIDENCE_DIGEST="$(sha256sum "${AGENT_CANON_COMMIT_REQUEST_WORKFLOW_PATH}" | awk '{print $1}')"
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:${COMMIT_REQUEST_EVIDENCE_DIGEST}"
export AGENT_CANON_COMMIT_REQUEST_EVIDENCE
echo "fresh-clone commit request evidence: ${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}"

run_parent_bound_sync \
  "${CLONE_SOURCE_ROOT}" \
  "${CLONE_TOOLS_ROOT}/sync_agent_canon.sh" \
  check
AGENT_CANON_TEST_REMOTE="${TMP_DIR}/agent-canon-upstream.git"
AGENT_CANON_TEST_WORK="${TMP_DIR}/agent-canon-work"
git init --bare "${AGENT_CANON_TEST_REMOTE}" >/dev/null
if git config -f .gitmodules --get submodule.vendor/agent-canon.path >/dev/null 2>&1; then
  git -C vendor/agent-canon push "${AGENT_CANON_TEST_REMOTE}" "HEAD:refs/heads/main" >/dev/null
else
  AGENT_CANON_SPLIT_SHA="$(git subtree split --prefix=vendor/agent-canon HEAD 2>/dev/null \
    || git subtree split --ignore-joins --prefix=vendor/agent-canon HEAD)"
  git push "${AGENT_CANON_TEST_REMOTE}" "${AGENT_CANON_SPLIT_SHA}:refs/heads/main" >/dev/null
fi
git --git-dir="${AGENT_CANON_TEST_REMOTE}" symbolic-ref HEAD refs/heads/main
git clone --no-local "${AGENT_CANON_TEST_REMOTE}" "${AGENT_CANON_TEST_WORK}" >/dev/null
add_safe_directory_to_config "${AGENT_CANON_TEST_WORK}"
(
  cd "${AGENT_CANON_TEST_WORK}"
  printf "fresh clone update marker\n" > .fresh-clone-agent-canon-marker
  git add .fresh-clone-agent-canon-marker
  git -c user.name="Fresh Clone Check" -c user.email="fresh-clone-check@example.invalid" commit -m "test: advance agent canon snapshot" >/dev/null
  git push origin main >/dev/null
)
if git config -f .gitmodules --get submodule.vendor/agent-canon.path >/dev/null 2>&1; then
  git config -f .gitmodules submodule.vendor/agent-canon.url "${AGENT_CANON_TEST_REMOTE}"
  git submodule sync vendor/agent-canon >/dev/null
  git -C vendor/agent-canon remote set-url origin "${AGENT_CANON_TEST_REMOTE}"
  git -C vendor/agent-canon fetch --force origin \
    "refs/heads/main:refs/remotes/origin/main" >/dev/null
else
  git remote add agent-canon "${AGENT_CANON_TEST_REMOTE}"
fi

materialize_current_lifecycle_projection() {
  local candidate_sha=""
  local candidate_tree_sha=""
  local publication_sha=""
  local publication_tree_sha=""
  local packet_path="${AGENT_CANON_TEST_WORK}/.agent-canon/update-lifecycle/state/source-publication-ready.json"
  local source_namespace="${AGENT_CANON_TEST_WORK}/.agent-canon/update-lifecycle"
  local target_namespace="${PWD}/.agent-canon/update-lifecycle"

  candidate_sha="$(git -C vendor/agent-canon rev-parse HEAD)"
  candidate_tree_sha="$(git -C vendor/agent-canon rev-parse HEAD^{tree})"
  publication_sha="$(git -C "${AGENT_CANON_TEST_WORK}" rev-parse HEAD)"
  publication_tree_sha="$(git -C "${AGENT_CANON_TEST_WORK}" rev-parse HEAD^{tree})"

  PYTHONPATH="${AGENT_CANON_TEST_WORK}/tools/agent_tools:${AGENT_CANON_TEST_WORK}/tools/ci" \
    python3 - "${packet_path}" "${candidate_sha}" "${candidate_tree_sha}" \
      "${publication_sha}" "${publication_tree_sha}" "${ROOT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

from check_agent_canon_pr import (
    GENERATED_COMPLETENESS_CHECK_IDS,
    materialize_generated_completeness_receipt,
)
from github_publish import materialize_pr_identity_gate
from parent_root_side_effects import (
    ParentRootAttestationRequest,
    ParentRootSideEffectBoundary,
)
from update_lifecycle_contract import (
    SourceProjectionGateOwnerApis,
    materialize_fresh_clone_source_projection_packet,
    validate_source_projection_packet,
)

packet_path = Path(sys.argv[1])
root_dir = Path(sys.argv[6])
packet = materialize_fresh_clone_source_projection_packet(
    candidate_sha=sys.argv[2],
    candidate_tree_sha=sys.argv[3],
    publication_sha=sys.argv[4],
    publication_tree_sha=sys.argv[5],
    gate_owner_apis=SourceProjectionGateOwnerApis(
        generated_completeness_check_ids=GENERATED_COMPLETENESS_CHECK_IDS,
        materialize_generated_completeness_receipt=materialize_generated_completeness_receipt,
        materialize_pr_identity_gate=materialize_pr_identity_gate,
    ),
)
validate_source_projection_packet(packet)
boundary = ParentRootSideEffectBoundary()
attestation = boundary.attest(
    ParentRootAttestationRequest(cwd=root_dir, explicit_root=root_dir, purpose="fresh-clone-packet")
)
boundary.write_parent_owned_file(
    attestation,
    packet_path,
    (json.dumps(packet, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    "fresh-clone-packet",
)
print("AGENT_CANON_FRESH_CLONE_SOURCE_PACKET=valid")
PY

(
  cd "${AGENT_CANON_TEST_WORK}"
  AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval \
  AGENT_CANON_DESTRUCTIVE_GIT_REASON="fresh clone acceptance uses a disposable temporary repository" \
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE="${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}" \
    run_parent_bound_update \
      "${AGENT_CANON_TEST_WORK}" \
      "${AGENT_CANON_TEST_WORK}/tools/update_agent_canon.sh" \
      latest
)

for lifecycle_path in \
  state/current-transaction \
  projection-queue/queue.accepted.json \
  projection-queue/frontier.accepted.json \
  evidence/g4.parent-projection-integrity.json; do
  test -f "${source_namespace}/${lifecycle_path}"
  parent_ensure_dir "${target_namespace}/$(dirname "${lifecycle_path}")"
  parent_copy_file "${source_namespace}/${lifecycle_path}" "${target_namespace}/${lifecycle_path}"
done

PYTHONPATH="${CLONE_TOOLS_ROOT}/agent_tools" \
  python3 - "${target_namespace}" <<'PY'
import json
import sys
from pathlib import Path

from update_lifecycle_contract import (
    binding_identity,
    validate_dependency_frontier,
    validate_gate_verdict,
    validate_queue_receipt,
)

namespace = Path(sys.argv[1])
queue = validate_queue_receipt(
    json.loads((namespace / "projection-queue/queue.accepted.json").read_text(encoding="utf-8"))
)
frontier = validate_dependency_frontier(
    json.loads((namespace / "projection-queue/frontier.accepted.json").read_text(encoding="utf-8"))
)
g4 = validate_gate_verdict(
    json.loads((namespace / "evidence/g4.parent-projection-integrity.json").read_text(encoding="utf-8"))
)
marker = json.loads((namespace / "state/current-transaction").read_text(encoding="utf-8"))
if set(marker) != {"schema", "transaction_id", "queue_receipt_id", "frontier_id"}:
    raise SystemExit("fresh_clone:current_transaction_marker_invalid")
if marker["schema"] != "agent-canon.update-lifecycle-current-transaction.v1":
    raise SystemExit("fresh_clone:current_transaction_marker_invalid")
if queue["state"] != "accepted" or queue["queue_receipt_id"] != marker["queue_receipt_id"]:
    raise SystemExit("fresh_clone:queue_identity_invalid")
if frontier["frontier_state"] != "accepted" or frontier["frontier_id"] != marker["frontier_id"]:
    raise SystemExit("fresh_clone:frontier_identity_invalid")
if binding_identity(queue["binding"]) != binding_identity(frontier["binding"]):
    raise SystemExit("fresh_clone:queue_frontier_binding_invalid")
if (
    g4["gate_id"] != "G4"
    or g4["verdict"] != "pass"
    or binding_identity(g4["binding"]) != binding_identity(frontier["binding"])
    or frontier["acceptance_evidence_ref"] not in g4["ordered_input_evidence_refs"]
):
    raise SystemExit("fresh_clone:g4_identity_invalid")
print("AGENT_CANON_FRESH_CLONE_LIFECYCLE=valid")
PY
}

git config user.name "Fresh Clone Check"
git config user.email "fresh-clone-check@example.invalid"
materialize_current_lifecycle_projection
capture_parent_bound_update \
  "${TMP_DIR}/agent-canon-plan.txt" \
  "${CLONE_SOURCE_ROOT}" \
  "${CLONE_TOOLS_ROOT}/update_agent_canon.sh" \
  plan
assert_update_plan_acceptance \
  "${TMP_DIR}/agent-canon-plan.txt" \
  "already_current_submodule|deferred_branch_pr|subtree_pull|submodule_update"
AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval \
AGENT_CANON_DESTRUCTIVE_GIT_REASON="fresh clone acceptance uses a disposable temporary repository" \
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}" \
  run_parent_bound_update \
    "${CLONE_SOURCE_ROOT}" \
    "${CLONE_TOOLS_ROOT}/update_agent_canon.sh" \
    apply
test -f vendor/agent-canon/.fresh-clone-agent-canon-marker
(
  cd "${AGENT_CANON_TEST_WORK}"
  printf "fresh clone no-subtree update marker\n" > .fresh-clone-agent-canon-no-subtree-marker
  git add .fresh-clone-agent-canon-no-subtree-marker
  git -c user.name="Fresh Clone Check" -c user.email="fresh-clone-check@example.invalid" commit -m "test: advance agent canon without subtree" >/dev/null
  git push origin main >/dev/null
)
parent_ensure_dir "${TMP_DIR}/missing-git-exec"
GIT_EXEC_PATH="${TMP_DIR}/missing-git-exec" \
  capture_parent_bound_update \
    "${TMP_DIR}/agent-canon-no-subtree-plan.txt" \
    "${CLONE_SOURCE_ROOT}" \
    "${CLONE_TOOLS_ROOT}/update_agent_canon.sh" \
    plan
assert_update_plan_acceptance \
  "${TMP_DIR}/agent-canon-no-subtree-plan.txt" \
  "deferred_branch_pr|snapshot_import_tree_match|snapshot_import_no_subtree|submodule_update"
AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval \
AGENT_CANON_DESTRUCTIVE_GIT_REASON="fresh clone acceptance uses a disposable temporary repository" \
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}" \
GIT_EXEC_PATH="${TMP_DIR}/missing-git-exec" \
  run_parent_bound_update \
    "${CLONE_SOURCE_ROOT}" \
    "${CLONE_TOOLS_ROOT}/update_agent_canon.sh" \
    apply
test -f vendor/agent-canon/.fresh-clone-agent-canon-no-subtree-marker
make -C "${CLONE_DIR}" agent-canon-check
echo "FRESH_CLONE_REPOSITORY_CI_OWNER=repository_ci_job"

echo "FRESH_CLONE_ACCEPTANCE=pass"
