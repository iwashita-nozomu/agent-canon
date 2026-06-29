# Priority Layers
<!--
@dependency-start
contract reference
responsibility Explains the revised completion-first priority layers for AgentCanon improvement.
upstream design ../README.md completion-first review index
upstream design 00-completion-first-principle.md completion-first rationale
upstream design ../../agents/TASK_WORKFLOWS.md workflow family routing
upstream design ../../agents/skills/README.md public skill surface
@dependency-end
-->

## Reader Map

Use this document to answer how the completion-first improvement layers are
ordered and which question each layer owns. Start with Overview for the full
P-1 through P8 map, then read each priority layer in order when planning work.
The final dependency section explains why lower layers must serve completion
judgment instead of redefining it.

## Overview

The improvement plan uses priority layers. The corrected ordering places completion judgment before agent settings.

The layers are:

| Priority | Area | Primary question |
| --- | --- | --- |
| P-1 | Completion judgment rules and completion-verifier tooling | What does done mean, and which tool decides it? |
| P0 | Agent settings and runtime invariants | How should agents run to satisfy completion profiles? |
| P1 | Tool, evidence, and verifier implementation | Which tools produce trusted evidence? |
| P2 | MCP, goal loop, and alternate route evidence | How do MCP and alternate route states affect completion? |
| P3 | Self-growth state machine | How does feedback become verified repair? |
| P4 | Surface ownership and AgentCanon sync | Which repo surface owns each change? |
| P5 | Workflow and skill contracts | Which workflows and skills are machine-checkable? |
| P6 | Template bootstrap, Docker, CI, and PR evidence | How does the system propagate to template-derived repos? |
| P7 | Research, experiment, claim, and docs rigor | Which claims are supported by formal evidence? |
| P8 | Audit, metrics, and retirement | How does the canon avoid permanent growth without cleanup? |

## P-1: Completion judgment

P-1 defines the target. It should introduce:

- `DEFINITION_OF_DONE.md`,
- `closeout_profiles.yaml`,
- `completion_verifier.py`,
- artifact schemas,
- behavior event schemas,
- validation evidence schemas,
- negative fixture policy,
- manual unlock prohibition,
- completion report generation.

The most important P-1 rule is that completion must not be self-attested. A Markdown field saying `unlocked` is not authoritative. A verifier-produced report is authoritative.

## P0: Agent settings and runtime invariants

P0 comes after P-1. Agent settings should answer: what runtime shape best satisfies the selected completion profile?

Examples:

- `self_growth` requires replay and eval evidence.
- `strict` requires reviewer independence.
- `release` requires fresh clone and remote/pin evidence.
- `advisory` must not fabricate repo validation evidence.

P0 should not define done. It should configure agents to achieve done.

P0 target artifacts:

- `runtime_config_matrix.yaml`,
- task catalog profile mappings,
- agent mode policy,
- role write policy,
- subagent lifecycle policy,
- MCP requirement policy.

## P1: Tool and evidence implementation

P1 implements the tools that make P-1 enforceable.

A good P1 tool does not merely print a pass token. It produces evidence with enough structure to be audited later.

Required evidence patterns:

```yaml
tool_call:
  command: make ci
  cwd: /workspace
  runtime_profile: container-default
  exit_code: 0
  stdout_sha256: ...
  stderr_sha256: ...
  evidence_path: reports/agents/<run>/validation/make-ci.json
```

P1 should prioritize:

- `record_validation_evidence.py`,
- `validate_behavior_events.py`,
- `validate_artifact_schema.py`,
- `validate_routing_decision.py`,
- `validate_surface_classification.py`,
- profile-aware `task_close.py`.

## P2: MCP and goal loop

MCP should be useful but honest. It must not be treated as passed when it is unavailable.

Completion should distinguish:

```text
mcp_status=pass
mcp_status=fail
mcp_status=shell_alternate route
mcp_status=not_applicable
```

For goal-driven and self-growth tasks, `goal_loop.py` or the MCP `goal.loop_status` equivalent should control whether a task can close.

If `NEXT_ACTION=run_next_iteration`, completion must fail. If `NEXT_ACTION=close_goal_loop`, completion may continue to the remaining closeout gates.

## P3: Self-growth

Self-growth starts only after completion profiles and evidence schemas exist. Otherwise it becomes prose accumulation.

The self-growth state machine is:

```text
Observe -> Diagnose -> Repair -> Evaluate -> Replay -> Promote -> Retire
```

A self-growth change is not complete because a memory file was edited. It is complete when the failure that triggered the learning is represented by a negative case, the repair passes eval, and the positive replay passes.

## P4: Surface ownership and AgentCanon sync

AgentCanon is used both as a standalone repo and as a submodule in Template/derived repos. Therefore completion must know which surface owns each changed file.

Changed paths should be classified as:

- `repo_local`,
- `agent_canon_source`,
- `root_symlink_view`,
- `synced_copy`,
- `generated`,
- `external_reference`,
- `unknown`.

`unknown` should fail strict completion. Direct edits to root symlink views should fail unless routed through the source surface.

## P5: Workflow and skill contracts

Workflow and skill documents are currently strong prose surfaces. They should become contract surfaces.

A workflow contract should define:

- allowed task shapes,
- required artifacts,
- required commands,
- required reviewers,
- state transitions,
- forbidden shortcuts,
- default closeout profile.

A skill contract should define:

- use when,
- do not use when,
- required artifacts,
- escalation target,
- completion impact.

## P6: Template propagation

Template must propagate the completion-first system into derived repos.

P6 targets:

- bootstrap replacement manifest,
- unresolved template token scan,
- CPU/CUDA Docker profile split,
- dynamic devcontainer secret mounts,
- PR evidence matrix,
- executable audit profiles,
- fresh clone evidence.

## P7: Research, experiment, claim, and docs rigor

P7 comes after the mechanical foundation. It prevents durable claims from being supported by weak evidence.

Required additions:

- `claim_ledger.md`,
- `source_ledger.md`,
- `run_manifest.json` with `run_type=formal|debug|smoke`,
- formal-run-only claim policy,
- long-form contradiction scan.

## P8: Audit, metrics, and retirement

Self-growth without retirement becomes self-bloat.

P8 introduces:

- `growth_metrics.json`,
- `learning_retirement_report.md`,
- duplicate rule detection,
- audit profiles,
- expiry or review-after metadata for durable rules.

## Dependency between layers

The key dependencies are:

```text
P-1 defines done.
P0 configures agents to target done.
P1 builds evidence tools for done.
P2 connects MCP/goal status to done.
P3 makes feedback repair subject to done.
P4 ensures the right repo surface owns done.
P5 turns workflow/skill prose into checkable contracts.
P6 propagates done into derived repos.
P7 applies done to claims and experiments.
P8 audits whether done is still useful.
```
