# Agent Instructions

This file is the template-root runtime entrypoint for Codex and GitHub Copilot.
The shared agent canon lives in `vendor/agent-canon/`, and the root discovery paths are runtime views into that snapshot.

## Read First

- `README.md`
- `documents/WORKFLOW_GUIDE.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `documents/AGENTS_COORDINATION.md`
- `docker/README.md`

## Template Context

- Human-facing primary language is Japanese.
- The default integration branch is `main`.
- Template-default implementation lives in `python/`.
- Template-default environment and runtime guidance live in `docker/`.
- Repo-wide durable rules live in `documents/`.

## Shared Canon

- Shared workflow, skills, subagents, docs, and support scripts are maintained in the vendored canon, not in this wrapper.
- Repo-changing tasks follow the staged flow in `agents/canonical/CODEX_WORKFLOW.md`: requirements -> research -> execution plan -> plan review -> detailed design -> detailed design review -> document flow review -> implementation.
- Keep `plan_reviewer`, `detailed_design_reviewer`, and `document_flow_reviewer` as separate agent instances.
- Long README, workflow, guide, and migration docs should use `agents/skills/long-form-writing.md` and require subagent review before closeout.
- If a shared surface drifts, repair it with `bash scripts/sync_agent_canon.sh link-root`.
- `link-root` restores both symlink views and root files that are intentionally synced as copies.
- If you need to change shared canon itself, treat `vendor/agent-canon/` as the source of truth.
- `.codex/config.toml` is the default shared Codex config; replace the symlink only when a repo-local override is intentional.

## Validation

- `make agent-checks`
- `make ci-quick`
- `make docs-check`
- `python3 -m pytest tests/ -q --tb=short`
