<!--
@dependency-start
contract data
responsibility Defines the answer-free argparse failure normalization packet.
upstream design ../../../../../documents/design/skill-runtime-shim-materialization.md packet contract
downstream implementation ../../../../../tools/runtime/dispatch/agent-canon/src/skill_shim_evaluation.rs packet producer
@dependency-end
-->

# Fresh Shim Failure Argparse Normalization

## Prompt Under Test

A route command returned an argparse usage error. Inspect the adapter and canonical owner,
then report the normalized failure boundary without inventing a command or an execution payload.
Keep the evaluation read-only.

## Canonical Target Files

- `.codex/personal/skills/agent-orchestration/SKILL.md`
- `agents/skills/agent-orchestration.md`

## Prompt Dependency Files

- `tools/runtime/dispatch/agent-canon/src/catalog/skill_routes.rs`
- `tools/runtime/dispatch/agent-canon/src/skill_shim_evaluation.rs`

## Requirements

- distinguish argument errors from route results
- preserve normalized failure semantics
- identify the canonical owner path

## Method

Use one fresh read-only gpt-5.4-mini evaluator at medium host profile.
