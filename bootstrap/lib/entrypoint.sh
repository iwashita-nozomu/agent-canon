#!/usr/bin/env bash
# Fixed bootstrap adapter. All lifecycle policy belongs to bootstrap_runtime.py.
set -euo pipefail

bootstrap_python_entrypoint() {
  local repository_root=$1
  shift
  exec python3 "$repository_root/tools/agent_tools/bootstrap_runtime.py" \
    --repository-root "$repository_root" "$@"
}
