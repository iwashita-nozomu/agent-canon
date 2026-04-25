#!/usr/bin/env bash
# @dependency-start
# @dependency-end

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

plan_output="$(bash tools/update_agent_canon.sh plan)"
printf '%s\n' "$plan_output"

route="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_route=/{print $2}')"

case "$route" in
  already_current_tree|already_current_split|local_contains_remote)
    echo "AGENT_CANON_LATEST=pass"
    ;;
  *)
    echo "AGENT_CANON_LATEST=fail"
    echo "Run 'make agent-canon-ensure-latest' after cleaning the worktree, or merge the shared-canon changes upstream first." >&2
    exit 1
    ;;
esac
