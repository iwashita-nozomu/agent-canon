---
name: devcontainer-exec
description: "Use only when an explicitly selected existing project Dev Container needs a targeted command through devcontainer exec; AgentCanon's shared tools and LSPs use agent-canon-bootstrap, and project tests use the project Docker/test runner."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"ac02df0f9b66adbfd033f93f3c25fa93ab3b34f88a306c43e9a33c2b380ceac1"} -->

<!--
@dependency-start
contract skill
responsibility Exposes devcontainer-exec for runtime discovery.
upstream design ../../../../agents/skills/devcontainer-exec.md owner
@dependency-end
-->

# devcontainer-exec

## Canonical Skill

Canonical workflow and policy: [devcontainer-exec](../../../../agents/skills/devcontainer-exec.md).

1. Read the canonical owner before applying this skill.
