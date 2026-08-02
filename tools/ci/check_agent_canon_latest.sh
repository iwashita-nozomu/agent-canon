#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks agent canon latest CI readiness.
# upstream design ../README.md shared automation index
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines PR-first propagation after dirty shared-canon checks
# upstream design ../../agents/workflows/derived-agent-canon-diff-workflow.md defines branch route for derived shared-canon diffs
# upstream implementation ../agent_tools/update_lifecycle_contract.py owns G4/G5 readback evidence identity.
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../lib/repo_paths.sh"
ROOT_DIR="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"
CANON_TOOLS_ROOT="$(agent_canon_tools_root "$ROOT_DIR")"
cd "$ROOT_DIR"
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"

if [[ -n "${AGENT_CANON_LATEST_GATE_BUNDLE:-}" ]]; then
  PYTHONPATH="${CANON_TOOLS_ROOT}/agent_tools${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${AGENT_CANON_LATEST_GATE_BUNDLE}" <<'PY'
import json
import sys
from pathlib import Path
from update_lifecycle_contract import validate_gate_chain

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
values = payload.get("gate_verdicts") if isinstance(payload, dict) else None
if not isinstance(values, list):
    raise SystemExit("agent_canon_latest_gate_bundle:gate_verdicts_missing")
validate_gate_chain(
    values,
    expected_gate_ids=("G4", "G5"),
    require_pass=True,
)
print("AGENT_CANON_LATEST_GATE_RECEIPTS=consumed")
print("AGENT_CANON_LATEST_GATE_ORDER=G4,G5")
print("AGENT_CANON_LATEST=pass")
print("AGENT_CANON_LATEST_ROUTE=lifecycle_readback_receipt")
PY
  exit 0
fi

PLAN_RC=0
plan_output="$(bash "${CANON_TOOLS_ROOT}/update_agent_canon.sh" plan 2>&1)" || PLAN_RC=$?
printf '%s\n' "$plan_output"

parse_plan_value() {
  local key="$1"
  printf '%s\n' "$plan_output" | awk -F= -v key="$key" '$1==key {print $0}' | tail -n1 | sed "s/^${key}=//"
}

route="$(parse_plan_value "agent_canon_plan_route")"
dirty_worktree="$(parse_plan_value "agent_canon_plan_dirty_worktree")"
dirty_update_surface="$(parse_plan_value "agent_canon_plan_dirty_update_surface")"
prefix_mode="$(parse_plan_value "agent_canon_plan_prefix_mode")"
remote_sha="$(parse_plan_value "agent_canon_plan_remote_sha")"
remote_url="$(parse_plan_value "agent_canon_plan_remote_url")"
submodule_worktree_head="$(parse_plan_value "agent_canon_plan_submodule_worktree_head")"
submodule_worktree_status="$(parse_plan_value "agent_canon_plan_submodule_worktree_status")"
submodule_parent_pin="$(parse_plan_value "agent_canon_plan_submodule_parent_pin")"
if [ -z "${prefix_mode:-}" ]; then
  if [ -f "${ROOT_DIR}/.gitmodules" ] && git -C "$ROOT_DIR" config -f .gitmodules --get submodule.vendor/agent-canon.path >/dev/null 2>&1; then
    prefix_mode="submodule"
  fi
fi
if [ "${prefix_mode:-}" = "submodule" ] && [ -z "${remote_url:-}" ]; then
  remote_url="$(git -C "$ROOT_DIR" config -f .gitmodules --get submodule.vendor/agent-canon.url 2>/dev/null || true)"
fi
if [ "${prefix_mode:-}" = "submodule" ] && [ -z "${submodule_parent_pin:-}" ]; then
  submodule_parent_pin="$(git -C "$ROOT_DIR" rev-parse ":$PREFIX" 2>/dev/null || true)"
fi
if [ "${prefix_mode:-}" = "submodule" ] && [ -z "${submodule_worktree_head:-}" ]; then
  submodule_worktree_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD 2>/dev/null || true)"
fi
if [ "${prefix_mode:-}" = "submodule" ]; then
  if [ "${#submodule_parent_pin}" -ne 40 ] \
    || [ "${#submodule_worktree_head}" -ne 40 ] \
    || [ -z "${submodule_worktree_status:-}" ]; then
    submodule_parent_pin="$(git -C "$ROOT_DIR" rev-parse ":$PREFIX" 2>/dev/null || true)"
    submodule_worktree_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD 2>/dev/null || true)"
  fi
fi
if [ "${prefix_mode:-}" = "submodule" ] && [ -z "${dirty_worktree:-}" ]; then
  submodule_worktree_status="$(git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all 2>/dev/null || true)"
  if [ -n "$submodule_worktree_status" ]; then
    dirty_worktree="yes"
  else
    dirty_worktree="no"
  fi
fi
if [ "${prefix_mode:-}" = "submodule" ] && [ -z "${dirty_update_surface:-}" ]; then
  dirty_update_surface="no"
fi

if [ "${PLAN_RC:-0}" -ne 0 ] && [ -z "$route" ]; then
  route="plan_incomplete_with_prefix_data_only"
fi
submodule_worktree_clean="not_applicable"
if [[ "${prefix_mode:-}" == "submodule" ]]; then
  if [[ "${dirty_worktree:-}" == "yes" ]]; then
    submodule_worktree_clean="no"
    if [[ -z "${submodule_worktree_status:-}" ]]; then
      submodule_worktree_status="dirty"
    fi
  elif [[ "${dirty_worktree:-}" == "no" ]]; then
    submodule_worktree_clean="yes"
    if [[ -z "${submodule_worktree_status:-}" ]]; then
      submodule_worktree_status="clean"
    fi
  elif [[ "${submodule_worktree_status:-}" == "clean" ]]; then
    submodule_worktree_clean="yes"
  elif [[ "${submodule_worktree_status:-}" == "dirty" ]]; then
    submodule_worktree_clean="no"
  fi
fi

emit_submodule_worktree_evidence() {
  if [[ "${prefix_mode:-}" != "submodule" ]]; then
    return
  fi
  echo "AGENT_CANON_LATEST_SUBMODULE_WORKTREE_HEAD=${submodule_worktree_head}"
  echo "AGENT_CANON_LATEST_SUBMODULE_WORKTREE_CLEAN=${submodule_worktree_clean}"
  echo "AGENT_CANON_LATEST_SUBMODULE_PARENT_PIN=${submodule_parent_pin:-unavailable}"
  echo "AGENT_CANON_LATEST_SUBMODULE_REMOTE_URL=${remote_url:-unavailable}"
}

emit_submodule_pin_integrity_block() {
  local reason="$1"
  local route_value="$2"
  echo "AGENT_CANON_LATEST=fail"
  echo "AGENT_CANON_LATEST_REASON=$reason"
  echo "AGENT_CANON_LATEST_ROUTE=${route_value:-unknown}"
  emit_submodule_worktree_evidence
  echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
  echo "AGENT_CANON_LATEST_PARENT_PIN_PENDING=yes"
  echo "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_then_commit_updated_submodule_pin_with_request_evidence"
  echo "AGENT_CANON_LATEST_DEPENDENCY_ROUTE=python3 tools/agent_tools/dependency_module_change.py --root . prepare --module ${PREFIX} --branch <source-branch> --owner-evidence <owner-evidence>"
  echo "AGENT_CANON_LATEST_REASON=$reason"
  exit 1
}

emit_submodule_pin_remote_reachable() {
  local remote_url_value="${1:-}"
  local pin_ref="${2:-}"
  if [ -z "${remote_url_value:-}" ] || [ -z "${pin_ref:-}" ]; then
    return 1
  fi
  if ! git -C "$ROOT_DIR/$PREFIX" cat-file -e "$pin_ref^{commit}" 2>/dev/null; then
    return 1
  fi

  local normalized_remote="$remote_url_value"
  local remote_path="$normalized_remote"
  if [[ "$remote_path" == file://* ]]; then
    remote_path="${remote_path#file://}"
  fi
  if [[ "$normalized_remote" == /* || "$normalized_remote" == ./* || "$normalized_remote" == ../* || -d "$remote_path" ]]; then
    git -C "$remote_path" cat-file -e "$pin_ref^{commit}" >/dev/null 2>&1 || return 1
  else
    if ! git -C "$ROOT_DIR/$PREFIX" fetch --no-write-fetch-head "$normalized_remote" "$pin_ref" >/dev/null 2>&1; then
      return 1
    fi
  fi

  if ! git -C "$ROOT_DIR/$PREFIX" cat-file -e "$pin_ref^{commit}" >/dev/null 2>&1; then
    return 1
  fi
  echo "AGENT_CANON_LATEST_SUBMODULE_PIN_REMOTE_REACHABLE=yes"
  return 0
}

ensure_submodule_latest_integrity() {
  local route_value="${1:-unknown}"
  local parent_pin="$submodule_parent_pin"
  local worktree_head="$submodule_worktree_head"
  local remote_sha_match=""

  if [ -z "$parent_pin" ] || [ "${#parent_pin}" -ne 40 ]; then
    parent_pin="$(git -C "$ROOT_DIR" rev-parse ":$PREFIX" 2>/dev/null || true)"
  fi
  if [ -z "$worktree_head" ] || [ "${#worktree_head}" -ne 40 ]; then
    worktree_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD 2>/dev/null || true)"
  fi

  if [ "$parent_pin" != "$worktree_head" ]; then
    emit_submodule_pin_integrity_block "submodule-gitlink-worktree-mismatch" "$route_value"
  fi
  if ! emit_submodule_pin_remote_reachable "$remote_url" "$parent_pin"; then
    echo "AGENT_CANON_LATEST_SUBMODULE_PIN_REMOTE_REACHABLE=no"
    emit_submodule_pin_integrity_block "submodule-pinned-commit-unreachable-from-configured-remote" "$route_value"
  fi
  echo "AGENT_CANON_LATEST_SUBMODULE_PIN_REMOTE_REACHABLE=yes"
}

if [[ "${prefix_mode:-}" == "submodule" ]]; then
  ensure_submodule_latest_integrity "${route:-unknown}"
fi

case "$route" in
  already_current_tree|already_current_split|already_current_submodule)
    echo "AGENT_CANON_LATEST=pass"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    emit_submodule_worktree_evidence
    ;;
  deferred_branch_pr)
    echo "AGENT_CANON_LATEST=pass"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    emit_submodule_worktree_evidence
    echo "AGENT_CANON_LATEST_GATE=deferred_branch_pr"
    echo "AGENT_CANON_LATEST_NEXT_ACTION=after_agentcanon_PR_merge_rerun_make_agent-canon-ensure-latest"
    echo "AgentCanon parent pin is a clean pushed branch head ahead of remote main; treating latest as deferred to the AgentCanon PR workflow." >&2
    ;;
  local_contains_remote)
    echo "AGENT_CANON_LATEST=pass"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    echo "AGENT_CANON_LATEST_PARENT_PIN_PENDING=yes"
    emit_submodule_worktree_evidence
    echo "AGENT_CANON_LATEST_AUTO_REPAIR=skipped_read_only_check"
    echo "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_then_commit_updated_submodule_pin_with_request_evidence"
    echo "AGENT_CANON_LATEST_UPDATE_METHOD=run_make_agent-canon-ensure-latest"
    echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
    ;;
  *)
    if [[ "${prefix_mode:-}" == "submodule" ]] && [ "$submodule_parent_pin" != "$submodule_worktree_head" ]; then
      emit_submodule_pin_integrity_block "submodule-gitlink-worktree-mismatch" "${route:-unknown}"
    fi
    if [[ "${prefix_mode:-}" == "submodule" && "${submodule_worktree_clean}" == "yes" ]]; then
      echo "AGENT_CANON_LATEST=pass"
      echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
      emit_submodule_worktree_evidence
      echo "AGENT_CANON_LATEST_PARENT_PIN_PENDING=yes"
      echo "AGENT_CANON_LATEST_AUTO_REPAIR=skipped_read_only_check"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_then_commit_updated_submodule_pin_with_request_evidence"
      echo "AgentCanon submodule worktree is clean and already at remote main; set AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> and run 'make agent-canon-ensure-latest' to stage the parent gitlink pin." >&2
      exit 0
    fi
    if [[ "${prefix_mode:-}" == "submodule" && "${submodule_worktree_clean}" == "no" ]]; then
      echo "AGENT_CANON_LATEST=pass"
      echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
      echo "AGENT_CANON_LATEST_GATED_BY=dirty_submodule_worktree_update_preserved"
      emit_submodule_worktree_evidence
      echo "AGENT_CANON_LATEST_PARENT_PIN_PENDING=yes"
      echo "AGENT_CANON_LATEST_AUTO_REPAIR=skipped_read_only_check"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_with_dirty_worktree_preserved"
      echo "AgentCanon submodule worktree has local dirt; unknown/unchanged non-materialization changes are allowed for read-only gates. Preserve dirty state if proceeding with update." >&2
      exit 0
    fi
    echo "AGENT_CANON_LATEST=fail"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    emit_submodule_worktree_evidence
    if [[ "${dirty_update_surface:-${dirty_worktree:-}}" == "yes" && "${prefix_mode:-}" == "submodule" ]]; then
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=commit_agentcanon_branch_then_open_agent-canon_PR_then_after_merge_run_make_agent-canon-ensure-latest_with_request_evidence"
      echo "AGENT_CANON_LATEST_DEPENDENCY_ROUTE=python3 tools/agent_tools/dependency_module_change.py --root . prepare --topic <topic> --module ${PREFIX} --branch <source-branch> --owner-evidence <owner-evidence>"
      echo "Route shared-canon local changes through a topic workspace branch and PR, then bring back only the clean pin with 'make agent-canon-ensure-latest'." >&2
    elif [[ "${dirty_worktree:-}" == "yes" && "${prefix_mode:-}" == "submodule" ]]; then
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_parent_dirty_outside_update_surface_ok_with_request_evidence"
      echo "Parent worktree has unrelated dirty paths, but the AgentCanon update surface is clean; set AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> and run 'make agent-canon-ensure-latest' before rerunning CI." >&2
    else
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_or_merge_agent-canon_PR_first_with_request_evidence"
      echo "Set AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> and run 'make agent-canon-ensure-latest' after cleaning the worktree, or merge the shared-canon changes upstream first." >&2
    fi
    exit 1
    ;;
esac
