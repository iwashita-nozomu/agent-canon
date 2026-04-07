---
name: static-validation
description: Use when validating changes, choosing checks, or tightening repo-wide quality gates for code, docs, links, and scripts.
---

# Static Validation

1. Prefer `make ci-quick` for routine validation.
1. Use `make ci` before final integration.
1. For documentation changes, run `make docs-check`.
1. Keep validation instructions in repo docs, not in agent-only prompts.
