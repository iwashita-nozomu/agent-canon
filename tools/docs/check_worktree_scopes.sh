#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks worktree scopes documentation quality.
# upstream design ../README.md shared automation index
# @dependency-end

set -euo pipefail
# Check each git worktree for WORKTREE_SCOPE.md and report.  Runtime output is
# external by construction; missing or unsafe roots fail before enumeration.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
export PYTHONPATH="${ROOT_DIR}/python${PYTHONPATH:+:${PYTHONPATH}}"
RUN_DIR="$({
  ROOT_DIR="${ROOT_DIR}" "${PYTHON_BIN}" - <<'PY'
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.environ["ROOT_DIR"])
from tools.agent_tools.runtime_artifacts import (  # noqa: E402
    RuntimeArtifactError,
    runtime_artifact_boundary,
)

try:
    boundary = runtime_artifact_boundary(
        Path(os.environ["ROOT_DIR"]),
        os.environ.get("AGENT_CANON_RUNTIME_ROOT"),
        create=True,
    )
    parent = boundary.ensure_directory(Path("tasks") / "worktree-scopes")
    print(tempfile.mkdtemp(prefix="run-", dir=str(parent)))
except RuntimeArtifactError as exc:
    print(f"runtime_root_error: {exc}", file=sys.stderr)
    raise SystemExit(2)
PY
} )"
OUT="${RUN_DIR}/worktree_scope_report.txt"
echo "Worktree scope check" > "$OUT"
git worktree list --porcelain | awk '/worktree /{print $2}' | while read -r wt; do
  echo "Worktree: $wt" >> "$OUT"
  if [ -f "$wt/WORKTREE_SCOPE.md" ]; then
    echo "  OK: WORKTREE_SCOPE.md present" >> "$OUT"
  else
    echo "  MISSING: WORKTREE_SCOPE.md" >> "$OUT"
  fi
done
echo "Report written to $OUT"
cat "$OUT"
