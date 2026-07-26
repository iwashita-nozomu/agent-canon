#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks fresh-clone bootstrap, AgentCanon update, and runtime surfaces.
# upstream design ../README.md shared automation index
# upstream environment ../../documents/linux-wsl-host-requirements.md documents host tool requirements for fresh clone checks
# upstream implementation ../agent_tools/update_lifecycle_contract.py owns source projection aggregation and validation.
# upstream implementation ./check_agent_canon_pr.py owns the authoritative G2 materializer API.
# upstream implementation ../agent_tools/github_publish.py owns the authoritative G3 materializer API.
# @dependency-end

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d -t template-fresh-clone-XXXXXX)"
TOPIC_ROOT="${TMP_DIR}/workspace-fresh-clone"
CLONE_DIR="${TOPIC_ROOT}/agent-canon"
trap 'rm -rf "${TMP_DIR}"' EXIT

mkdir -p "${TOPIC_ROOT}"

echo "fresh-clone source: ${ROOT_DIR}"
echo "fresh-clone target: ${CLONE_DIR}"

overlay_current_tree() {
  if ! command -v rsync >/dev/null 2>&1; then
    echo "fresh_clone_overlay=fail"
    echo "fresh_clone_overlay_error=rsync_required"
    echo "fresh_clone_overlay_next_action=install rsync via docker/Dockerfile or host requirements"
    exit 1
  fi
  rsync -a --delete --exclude .git --exclude .state "${ROOT_DIR}/" "${CLONE_DIR}/" >/dev/null
}

git clone --no-local "${ROOT_DIR}" "${CLONE_DIR}" >/dev/null
git config --global --add safe.directory "${CLONE_DIR}"
overlay_current_tree
cd "${CLONE_DIR}"
if git config -f .gitmodules --get submodule.vendor/agent-canon.path >/dev/null 2>&1; then
  rm -rf vendor/agent-canon
  git -c protocol.file.allow=always submodule update --init --recursive vendor/agent-canon
fi
if [[ -n "$(git status --short)" ]]; then
  git config user.name "Fresh Clone Check"
  git config user.email "fresh-clone-check@example.invalid"
  git add -A
  git commit -m "test: overlay current working tree for fresh clone check" >/dev/null
fi

for path in AGENTS.md agents .agents .codex/config.toml .codex/hooks.json agents/workflows/README.md agents/workflows/paper-writing-workflow.md; do
  if [ ! -e "${path}" ]; then
    echo "missing runtime surface: ${path}" >&2
    exit 1
  fi
done

COMMIT_REQUEST_EVIDENCE_DIGEST="$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')"
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:${COMMIT_REQUEST_EVIDENCE_DIGEST}"
echo "fresh-clone commit request evidence: ${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}"

python3 -m json.tool .devcontainer/devcontainer.json >/dev/null
bash .devcontainer/generate-runtime-compose.sh >/dev/null
python3 - <<'PY'
from __future__ import annotations

from pathlib import Path
import yaml

compose_path = Path(".devcontainer/docker-compose.generated.yml")
data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
assert data["name"].endswith("-devcontainer"), "compose project name missing"
assert "services" in data and "workspace" in data["services"], "workspace service missing"
expected_working_dir = f"/workspace/{Path.cwd().name}"
assert data["services"]["workspace"]["working_dir"] == expected_working_dir
PY

parent_projection_mode=false
if git config -f .gitmodules --get submodule.vendor/agent-canon.path >/dev/null 2>&1 \
  || [ -d vendor/agent-canon ]; then
  parent_projection_mode=true
fi
if [ "$parent_projection_mode" = false ]; then
  echo "FRESH_CLONE_AGENT_CANON_MODE=standalone"
  echo "FRESH_CLONE_PARENT_PROJECTION=not-applicable"
  echo "FRESH_CLONE_REPOSITORY_CI_OWNER=repository_ci_job"
  echo "FRESH_CLONE_ACCEPTANCE=pass"
  exit 0
fi

bash tools/sync_agent_canon.sh check
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
git config --global --add safe.directory "${AGENT_CANON_TEST_WORK}"
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
      "${publication_sha}" "${publication_tree_sha}" <<'PY'
import json
import sys
from pathlib import Path

from check_agent_canon_pr import (
    GENERATED_COMPLETENESS_CHECK_IDS,
    materialize_generated_completeness_receipt,
)
from github_publish import materialize_pr_identity_gate
from update_lifecycle_contract import (
    SourceProjectionGateOwnerApis,
    materialize_fresh_clone_source_projection_packet,
    validate_source_projection_packet,
)

packet_path = Path(sys.argv[1])
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
packet_path.parent.mkdir(parents=True, exist_ok=True)
packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("AGENT_CANON_FRESH_CLONE_SOURCE_PACKET=valid")
PY

(
  cd "${AGENT_CANON_TEST_WORK}"
  AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=agent_canon_workflow \
  AGENT_CANON_BRANCH_WORKTREE_REASON="fresh clone acceptance materializes the canonical source lifecycle" \
  AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval \
  AGENT_CANON_DESTRUCTIVE_GIT_REASON="fresh clone acceptance uses a disposable temporary repository" \
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE="${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}" \
    bash tools/update_agent_canon.sh latest
)

for lifecycle_path in \
  state/current-transaction \
  projection-queue/queue.accepted.json \
  projection-queue/frontier.accepted.json \
  evidence/g4.parent-projection-integrity.json; do
  test -f "${source_namespace}/${lifecycle_path}"
  mkdir -p "${target_namespace}/$(dirname "${lifecycle_path}")"
  cp "${source_namespace}/${lifecycle_path}" "${target_namespace}/${lifecycle_path}"
done

PYTHONPATH="${PWD}/tools/agent_tools" \
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
bash tools/update_agent_canon.sh plan | tee "${TMP_DIR}/agent-canon-plan.txt"
grep -Eq "agent_canon_plan_route=(subtree_pull|submodule_update)" "${TMP_DIR}/agent-canon-plan.txt"
AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=agent_canon_workflow \
AGENT_CANON_BRANCH_WORKTREE_REASON="fresh clone acceptance exercises the canonical submodule update workflow" \
AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval \
AGENT_CANON_DESTRUCTIVE_GIT_REASON="fresh clone acceptance uses a disposable temporary repository" \
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}" \
  bash tools/update_agent_canon.sh apply
test -f vendor/agent-canon/.fresh-clone-agent-canon-marker
(
  cd "${AGENT_CANON_TEST_WORK}"
  printf "fresh clone no-subtree update marker\n" > .fresh-clone-agent-canon-no-subtree-marker
  git add .fresh-clone-agent-canon-no-subtree-marker
  git -c user.name="Fresh Clone Check" -c user.email="fresh-clone-check@example.invalid" commit -m "test: advance agent canon without subtree" >/dev/null
  git push origin main >/dev/null
)
mkdir -p "${TMP_DIR}/missing-git-exec"
GIT_EXEC_PATH="${TMP_DIR}/missing-git-exec" bash tools/update_agent_canon.sh plan | tee "${TMP_DIR}/agent-canon-no-subtree-plan.txt"
grep -Eq "agent_canon_plan_route=(snapshot_import_tree_match|snapshot_import_no_subtree|submodule_update)" "${TMP_DIR}/agent-canon-no-subtree-plan.txt"
AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=agent_canon_workflow \
AGENT_CANON_BRANCH_WORKTREE_REASON="fresh clone acceptance exercises the canonical submodule update workflow" \
AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval \
AGENT_CANON_DESTRUCTIVE_GIT_REASON="fresh clone acceptance uses a disposable temporary repository" \
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}" \
GIT_EXEC_PATH="${TMP_DIR}/missing-git-exec" \
  bash tools/update_agent_canon.sh apply
test -f vendor/agent-canon/.fresh-clone-agent-canon-no-subtree-marker
make agent-checks
echo "FRESH_CLONE_REPOSITORY_CI_OWNER=repository_ci_job"

echo "FRESH_CLONE_ACCEPTANCE=pass"
