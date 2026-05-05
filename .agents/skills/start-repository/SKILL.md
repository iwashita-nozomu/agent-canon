---
name: start-repository
description: Use when starting a new repository from this template after clone, including project slug/display-name setup, new bare remote registration, and project-local agent-canon bare repo seeding.
---
<!--
@dependency-start
responsibility Documents Start Repository for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Start Repository

1. Use this skill after `git clone <template> <new-project>` when the user is turning the clone into a new repository.
1. Read `documents/template-bootstrap.md`, `documents/agent-canon-github-remote.md`, and `scripts/README.md`.
1. Prefer `bash scripts/start_repository.sh --project-slug <slug> --display-name "<name>"` for clone-time setup.
1. Treat GitHub `https://github.com/iwashita-nozomu/agent-canon.git` as the AgentCanon source of truth. Use project-local bare repos only as proposal / mirror surfaces.
1. If the user is registering a new project bare repo, let the wrapper call `init_from_template.sh` and `tools/update_agent_canon.sh register-local-bare`; otherwise pass `--skip-agent-canon-bare-repo` so the GitHub canonical submodule remains the active remote.
1. A repo-specific proposal branch such as `canon-proposal/<project-slug>` is needed only when a project-local bare repo is intentionally registered.
1. When a custom agent-canon bare repo name is needed, pass `--agent-canon-bare-repo <name>.git`.
1. After committing init changes, run `bash scripts/start_repository.sh --validate-only`.
1. Do not overwrite an existing non-empty `agent-canon` bare repo; stop and ask before changing that remote's history.
