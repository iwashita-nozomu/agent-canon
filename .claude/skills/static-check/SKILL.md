---
name: static-check
description: Use this skill when you need fast validation of code, docs, tests, or environment health.
---

# Static Check

1. Read `agents/skills/static-check.md`.
1. Classify the change surface first: agent/runtime, code, docs, or Docker/environment.
1. If skill, runtime, or mirror files changed, run `make agent-checks` before the other gates.
1. Prefer `make ci-quick`, `make docs-check`, and `make docker-build-check` over ad hoc commands.
1. Record which gates passed, failed, or were intentionally not run.
1. If deeper repo-specific gate selection matters, also read `agents/skills/static-validation.md`.
