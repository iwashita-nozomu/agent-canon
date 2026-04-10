---
name: start-repository
description: Use when starting a new repository from this template after clone, including project slug/display-name setup, new bare remote registration, and project-local agent-canon bare repo seeding.
---

# Start Repository

1. Use this skill after `git clone <template> <new-project>` when the user is turning the clone into a new repository.
1. Read `documents/template-bootstrap.md` and `scripts/README.md`.
1. Prefer `bash scripts/init_from_template.sh --project-slug <slug> --display-name "<name>"` for clone-time setup.
1. If the user is registering a new project bare repo, let `init_from_template.sh` also seed the project-local `agent-canon` bare repo unless they explicitly opt out with `--skip-agent-canon-bare-repo`.
1. When a custom agent-canon bare repo name is needed, pass `--agent-canon-bare-repo <name>.git`.
1. After initialization, run `make agent-canon-ensure-latest` to confirm the seeded `agent-canon` remote matches `vendor/agent-canon/`.
1. Then run `make fresh-clone-check` and `make ci-quick`.
1. Do not overwrite an existing non-empty `agent-canon` bare repo; stop and ask before changing that remote's history.
