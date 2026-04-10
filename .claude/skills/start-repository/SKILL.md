---
name: start-repository
description: Use when starting a new repository from this template after clone, including project slug/display-name setup, new bare remote registration, and project-local agent-canon bare repo seeding.
---

# Start Repository

1. Use this skill after `git clone <template> <new-project>` when the user is turning the clone into a new repository.
1. Read `documents/template-bootstrap.md` and `scripts/README.md`.
1. Prefer `bash scripts/start_repository.sh --project-slug <slug> --display-name "<name>"` for clone-time setup.
1. If the user is registering a new project bare repo, let the wrapper call `init_from_template.sh` and seed the project-local `agent-canon` bare repo unless they explicitly opt out with `--skip-agent-canon-bare-repo`.
1. When a custom agent-canon bare repo name is needed, pass `--agent-canon-bare-repo <name>.git`.
1. After committing init changes, run `bash scripts/start_repository.sh --validate-only`.
1. Do not overwrite an existing non-empty `agent-canon` bare repo; stop and ask before changing that remote's history.
