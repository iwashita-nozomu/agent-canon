---
name: pr-processing
description: "Use when processing GitHub pull requests or issue queues: inventory open PRs, preserve PR Essence in bodies and run bundles, resolve conflicts, order merges, update branch protection evidence, merge only with authority, triage stale issues, and sync AgentCanon source PRs with parent pin PRs."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"8aafac56a9bbd82a09f2ef330311fe32323b014228132f487b25ca992795a51e"} -->

<!--
@dependency-start
contract skill
responsibility Exposes pr-processing for runtime discovery.
upstream design ../../../../agents/skills/pr-processing.md owner
@dependency-end
-->

# pr-processing

## Canonical Skill

Canonical workflow and policy: [pr-processing](../../../../agents/skills/pr-processing.md).

1. Read the canonical owner before applying this skill.
