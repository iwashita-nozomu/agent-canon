# Violation Cases
<!--
@dependency-start
contract reference
responsibility Catalogs cases that should not pass completion under the completion-first AgentCanon review.
upstream design ../README.md completion-first review index
upstream design 03-evidence-and-closeout.md evidence hierarchy and closeout rules
upstream implementation ../../tools/agent_tools/evaluate_agent_run.py current run evaluator
upstream implementation ../../tools/agent_tools/workflow_monitor.py current monitoring helper
@dependency-end
-->

## Reader Map

- Owns the catalog of completion-first false-negative cases that should not
  pass closeout.
- Main path: Purpose, Core false-negative cases, Fixture shape, How to use this
  catalog, and Completion-first invariant.
- Read this when designing eval fixtures or closeout checks that must reject
  weak completion evidence.
- Boundary: this catalog names failure cases; evaluator implementation and
  workflow policy live in the linked tools and completion-first docs.

## Purpose

This chapter lists concrete false-negative cases: situations that may look acceptable under loose token or checklist rules but should fail under a completion-first system.

These cases should become fixtures under a future `evidence/agent-evals/negative_cases/` surface.

## Core false-negative cases

| ID | Case | Why it is dangerous | Required detection |
| --- | --- | --- | --- |
| V001 | `tool_call=make ci static_analysis=pass` appears in monitoring but no command evidence exists | Token-only validation can be fabricated | Behavior event schema requires command, exit code, evidence path, and hashes |
| V002 | Runtime feedback is written only in retrospective | Feedback never enters self-growth repair loop | `runtime_feedback=observed` requires self-growth repair manifest |
| V003 | Prompt contains required keywords but no actionable procedure | Regex eval passes meaningless text | Workflow/skill contract validates states, artifacts, and commands |
| V004 | MCP is unavailable but `mcp_inventory=pass` is recorded | False MCP pass hides runtime failure | MCP status artifact or shell alternate route artifact required |
| V005 | Agent memory is edited but not committed/pushed through AgentCanon | Learning does not propagate | Memory change requires AgentCanon commit/push and superproject pin evidence |
| V006 | Root symlink view is edited directly | Source of truth is bypassed | Surface classification rejects root view direct edit |
| V007 | Research task is closed as scoped change | Research evidence and claim review omitted | Routing validator detects missing research workflow or rejected reason |
| V008 | Debug run supports durable claim | Weak experiment evidence becomes canonical | Claim ledger accepts only formal runs for durable claims |
| V009 | Trivial task skips bundle with no official trivial profile | Ad hoc bypass becomes precedent | Trivial profile defines allowed minimal evidence |
| V010 | Large delivery has no chunk manifest | Review cannot map changes to chunks | Large-delivery profile requires chunk manifest |
| V011 | Skill is declared but not actually read or used | Skill invocation becomes cosmetic | Skill event requires source path and artifact influence |
| V012 | Token-lite mode skips dependency review | Efficiency becomes correctness loss | Token profiles cannot modify closeout gate profile |
| V013 | New tool added without reuse survey | Tool sprawl | Tool catalog requires alternatives and why-new-tool fields |
| V014 | ROOT_AGENTS gets detailed rules duplicated from canonical docs | Entry point becomes bloated and inconsistent | Entry point budget and duplicate-rule scan |
| V015 | Workflow says “must” but no verifier exists | Normative prose is unenforced | Normative rule requires verifier or explicit non-verifiable rationale |
| V016 | Goal loop uses ignored local `goal.md` but no snapshot | Reviewers cannot inspect goal contract | Goal snapshot required in run bundle |
| V017 | Execution path comparison only records `execution_path=preferred` | Trace sequence not compared | Run path comparison validates event sequence and cost |
| V018 | Review finding is marked resolved without fix evidence | Review becomes self-attested | Finding ID maps to fix evidence path and latest diff ref |
| V019 | PR checklist says not affected without scope reason | Human checkbox hides missing validation | PR evidence matrix generated from closeout profile |
| V020 | AgentCanon source change is handled only in Template PR | Shared canon update does not land upstream | AgentCanon source PR evidence required |
| V021 | Skill expected count updated while obsolete skill remains | Count passes but inventory is wrong | Catalog set equality replaces raw expected count |
| V022 | Dockerfile changes without docs/runtime impact review | Runtime docs drift | Runtime change impact matrix required |
| V023 | Local bare mirror treated as canonical source | Wrong remote source of truth | Remote status artifact distinguishes GitHub main, local mirror, pin |
| V024 | Temporary style preference promoted repo-wide | Overfitted durable rule | Promotion requires scope, support count, and counterexample review |
| V025 | False-negative gate fixed only by prompt text | Mechanical failure remains | Tool/schema repair required for false-negative gate |
| V026 | Required artifact exists but has only headings | Empty evidence passes file-existence check | Artifact schema validates minimum content |
| V027 | Parent performs independent diff check | Self-review | Strict profile rejects parent/self reviewer identity |
| V028 | Parent-direct reason is vague and bypasses subagents | Subagent policy becomes cosmetic | Allowed parent-direct reasons are enumerated and scoped |
| V029 | Prompt repair reruns a different eval | Original failure not tested | Baseline and rerun eval IDs must match |
| V030 | Learning items accumulate without retirement | Canon bloat | Learning item needs review-after, expiry, or no-retirement reason |
| V031 | Hypothesis validation has no disconfirming evidence | First-candidate edit bias | Hypothesis artifact requires counterevidence fields |
| V032 | Host validation is treated as canonical container validation | Runtime mismatch | Validation evidence records runtime profile |
| V033 | Experiment artifacts are outside expected result/report layout | Results become hard to audit | Artifact placement checker required |
| V034 | Synced workflow copy edited only at root | Source copy drift | Synced-copy source hash gate |
| V035 | README simplification removes invariant | Navigation improves but authority weakens | Reader path and authority graph cross-check |
| V036 | Self-growth eval added without negative case | No regression prevention | Every self-growth repair adds negative case or exception |
| V037 | Pasted output mixes commands | Evidence is untrustworthy | Command recorder hashes stdout/stderr |
| V038 | Proposal branch SHA confused with main pin SHA | Wrong propagation | Remote status table required |
| V039 | Workflow overlay selected but schedule ignores it | Plan and execution diverge | Routing-to-schedule consistency check |
| V040 | User requested strictness but token-saving shortcut dominates | User priority conflict | Request priority conflict resolver required |

## Fixture shape

Each violation should eventually become a fixture like:

```yaml
id: V001
title: token-only static analysis pass
fixture_type: run_bundle
target_profile: strict
expected_old_status: pass_or_unknown
expected_new_status: fail
failure_reason: tool_call event lacks command-backed evidence
repair_surface: behavior_event.schema.yaml
positive_fixture: V001_positive
```

## How to use this catalog

1. Pick a violation case.
2. Build a minimal fixture that represents it.
3. Confirm the current system would pass or not clearly reject it.
4. Implement a verifier or schema rule.
5. Confirm the fixture fails.
6. Add a positive fixture.
7. Connect the verifier to the relevant closeout profile.

## Completion-first invariant

```text
Every discovered false negative should either become a negative fixture or have a documented reason why it cannot be represented as a fixture.
```
