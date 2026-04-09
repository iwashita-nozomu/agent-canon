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
make agent-checks
make ci-quick

echo "FRESH_CLONE_ACCEPTANCE=pass"
