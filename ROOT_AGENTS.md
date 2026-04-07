# Agent Instructions

This file is the product-root runtime entrypoint for Codex and GitHub Copilot.
The shared agent canon lives in `vendor/agent-canon/`, and the root discovery paths are runtime views into that snapshot.

## Read First

- `README.md`
- `documents/WORKFLOW_GUIDE.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `documents/AGENTS_COORDINATION.md`
- `docker/README.md`

## Product Context

- Human-facing primary language is Japanese.
- The default integration branch is `main`.
- Product implementation lives in `python/`.
- Product environment and runtime guidance live in `docker/`.
- Product-level durable rules live in `documents/`.

## Shared Canon

- Shared workflow, skills, subagents, docs, and support scripts are maintained in the vendored canon, not in this wrapper.
- If a shared surface drifts, repair it with `bash scripts/sync_agent_canon.sh link-root`.
- `link-root` restores both symlink views and root files that are intentionally synced as copies.
- If you need to change shared canon itself, treat `vendor/agent-canon/` as the source of truth.
- `.codex/config.toml` is the default shared Codex config; replace the symlink only when a product-specific override is intentional.

## Validation

- `make agent-checks`
- `make ci-quick`
- `make docs-check`
