#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Rejects legacy setup worktree repository automation.
# upstream design README.md shared automation index
# @dependency-end

set -euo pipefail

echo "SETUP_WORKTREE_FORWARDER=deprecated" >&2
echo "SETUP_WORKTREE_FORWARDER_SEVERITY=fix-now" >&2
echo "CALLER_CHAIN=${BASH_SOURCE[*]}" >&2
echo "MIGRATION_TARGET=current-checkout run bundle + team_manifest.yaml write scope" >&2
echo "NEXT_ACTION=do not create a branch worktree; bootstrap the run with tools/agent_tools/bootstrap_agent_run.py and serialize colliding writers in the current checkout" >&2
exit 2
