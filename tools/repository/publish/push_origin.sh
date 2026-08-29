#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Retires the former shell Git push implementation in favor of the gh-backed publish tool.
# upstream implementation agent_tools/github_publish.py publishes GitHub branches and pull requests.
# upstream design ../agents/workflows/agent-canon-pr-workflow.md defines the canonical publish route.
# upstream design ../documents/tools/github_publish.md documents the replacement command.
# @dependency-end

set -euo pipefail

cat >&2 <<'EOF'
tools/push_origin.sh no longer performs GitHub publish work.

Use the gh-backed tool instead, and pass the current user task explicitly:

  python3 tools/agent_tools/github_publish.py push \
    --user-task "<current user task>" \
    --repo <owner/name>

For PR work:

  python3 tools/agent_tools/github_publish.py publish-pr \
    --user-task "<current user task>" \
    --repo <owner/name> \
    --title "<title>" \
    --body-file <body.md>

This entrypoint requires the verified gh repository and origin remote route.
EOF

exit 2
