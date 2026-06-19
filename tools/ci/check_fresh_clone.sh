#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks that a fresh clone can run the expected repository validations.
# upstream design ../README.md shared automation index
# upstream environment ../../documents/linux-wsl-host-requirements.md documents host tool requirements for fresh clone checks
# @dependency-end

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d -t template-fresh-clone-XXXXXX)"
CLONE_DIR="${TMP_DIR}/clone"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "fresh-clone source: ${ROOT_DIR}"
echo "fresh-clone target: ${CLONE_DIR}"

overlay_current_tree() {
  if ! command -v rsync >/dev/null 2>&1; then
    echo "fresh_clone_overlay=fail"
    echo "fresh_clone_overlay_error=rsync_required"
    echo "fresh_clone_overlay_next_action=install rsync via docker/Dockerfile or host requirements"
    exit 1
  fi
  rsync -a --delete --exclude .git --exclude .state --exclude .cache/huggingface --exclude .cache/llama.cpp --exclude '*.gguf' --exclude '*.safetensors' --exclude 'pytorch_model*.bin' --exclude 'model-*.bin' --exclude vendor/local-llm-server/llama-cpp/cache --exclude vendor/local-llm-server/llama-cpp/models --exclude vendor/local-llm-server/llama-cpp/runtime "${ROOT_DIR}/" "${CLONE_DIR}/" >/dev/null
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
assert data["services"]["workspace"]["working_dir"] == "/workspace"
PY

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
git config user.name "Fresh Clone Check"
git config user.email "fresh-clone-check@example.invalid"
bash tools/update_agent_canon.sh plan | tee "${TMP_DIR}/agent-canon-plan.txt"
grep -Eq "agent_canon_plan_route=(subtree_pull|submodule_update)" "${TMP_DIR}/agent-canon-plan.txt"
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
GIT_EXEC_PATH="${TMP_DIR}/missing-git-exec" bash tools/update_agent_canon.sh apply
test -f vendor/agent-canon/.fresh-clone-agent-canon-no-subtree-marker
make agent-checks
make ci-quick

echo "FRESH_CLONE_ACCEPTANCE=pass"
