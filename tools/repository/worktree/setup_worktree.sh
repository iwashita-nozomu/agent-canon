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
echo "MIGRATION_TARGET=tools/repository/workspace/repository_topic_clone.py prepare" >&2
echo "NEXT_ACTION=parent/same-repository: use tools/repository/workspace/repository_topic_clone.py prepare ... --checkout-mode linked-worktree; dependency repository: use tools/repository/workspace/repository_topic_clone.py prepare ... --checkout-mode independent-clone" >&2
exit 2
