#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d -t template-fresh-clone-XXXXXX)"
CLONE_DIR="${TMP_DIR}/clone"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "fresh-clone source: ${ROOT_DIR}"
echo "fresh-clone target: ${CLONE_DIR}"

git clone --no-local "${ROOT_DIR}" "${CLONE_DIR}" >/dev/null
cd "${CLONE_DIR}"

for path in AGENTS.md agents .agents .claude .codex/config.toml documents/WORKFLOW_GUIDE.md documents/paper-writing-workflow.md; do
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
assert "services" in data and "workspace" in data["services"], "workspace service missing"
assert data["services"]["workspace"]["working_dir"] == "/workspace"
PY

bash tools/sync_agent_canon.sh check
AGENT_CANON_TEST_REMOTE="${TMP_DIR}/agent-canon-upstream.git"
AGENT_CANON_TEST_WORK="${TMP_DIR}/agent-canon-work"
AGENT_CANON_SPLIT_SHA="$(git subtree split --prefix=vendor/agent-canon HEAD)"
git init --bare "${AGENT_CANON_TEST_REMOTE}" >/dev/null
git push "${AGENT_CANON_TEST_REMOTE}" "${AGENT_CANON_SPLIT_SHA}:refs/heads/main" >/dev/null
git --git-dir="${AGENT_CANON_TEST_REMOTE}" symbolic-ref HEAD refs/heads/main
git clone "${AGENT_CANON_TEST_REMOTE}" "${AGENT_CANON_TEST_WORK}" >/dev/null
(
  cd "${AGENT_CANON_TEST_WORK}"
  printf "fresh clone fallback marker\n" > .fresh-clone-agent-canon-marker
  git add .fresh-clone-agent-canon-marker
  git -c user.name="Fresh Clone Check" -c user.email="fresh-clone-check@example.invalid" commit -m "test: advance agent canon snapshot" >/dev/null
  git push origin main >/dev/null
)
git remote add agent-canon "${AGENT_CANON_TEST_REMOTE}"
git config user.name "Fresh Clone Check"
git config user.email "fresh-clone-check@example.invalid"
bash tools/sync_agent_canon.sh ensure-latest
test -f vendor/agent-canon/.fresh-clone-agent-canon-marker
make agent-checks
make ci-quick

echo "FRESH_CLONE_ACCEPTANCE=pass"
