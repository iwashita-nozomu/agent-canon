# Completion-First AgentCanon Review
<!--
@dependency-start
contract reference
responsibility Indexes the completion-first AgentCanon improvement review.
upstream design ../AGENTS.md AgentCanon runtime and closeout expectations
upstream design ../agents/workflows/agent-learning-workflow.md agent self-growth workflow
upstream design ../agents/workflows/adaptive-improvement-workflow.md adaptive improvement loop
upstream implementation ../tools/agent_tools/task_close.py current closeout evaluator
upstream implementation ../tools/agent_tools/evaluate_agent_run.py current run evaluator
@dependency-end
-->

This directory contains a chapterized review of the proposed AgentCanon improvement plan.
The key correction is that **completion judgment rules and completion-verifier tooling must come before agent settings, tools, MCP, workflow, skill, and documentation changes**.

## Current status

This directory is a design and backlog review surface. It is not currently an
active closeout verifier, hook, CI gate, or task-close input. The checklist
chapters intentionally name future target surfaces such as
`agents/canonical/closeout_profiles.yaml`,
`tools/agent_tools/completion_verifier.py`, and
`tools/agent_tools/generate_completion_report.py`; those files must exist and
be wired into validation before this review can be treated as a runtime
completion gate.

The previous framing placed agent settings at the top. This review changes the order:

1. Define completion first.
2. Define verifier tools and evidence schemas.
3. Then configure agents, runtime profiles, MCP, workflows, skills, and self-growth loops to satisfy that completion definition.

## Explanation chapters

- [00 Completion-first principle](explanation/00-completion-first-principle.md)
- [01 Priority layers](explanation/01-priority-layers.md)
- [02 Self-growth state machine](explanation/02-self-growth-state-machine.md)
- [03 Evidence and closeout](explanation/03-evidence-and-closeout.md)
- [04 Violation cases](explanation/04-violation-cases.md)
- [05 Implementation roadmap](explanation/05-implementation-roadmap.md)

## Checklist chapters

- [00 Priority order](checklist/00-priority-order.md)
- [01 P-1 completion gate](checklist/01-p-minus-one-completion-gate.md)
- [02 P0-P2 mechanical foundation](checklist/02-p0-p2-mechanical-foundation.md)
- [03 P3 self-growth](checklist/03-p3-self-growth.md)
- [04 P4-P6 canon/template/contracts](checklist/04-p4-p6-canon-template-contracts.md)
- [05 P7-P8 research/audit/retirement](checklist/05-p7-p8-research-audit-retirement.md)
- [06 Violation fixtures](checklist/06-violation-fixtures.md)

## Review stance

This is intentionally not a convenience-first document. It is a strictness-first and contradiction-resistance review. The goal is to make the repo harder to accidentally mark complete when required evidence, reviewer independence, MCP alternate route status, or self-growth replay evidence is missing.

## Central thesis

AgentCanon should behave less like a large rulebook and more like a small operating system for agent work:

- completion profiles define what done means,
- verifier tools decide whether done is true,
- runtime and agent settings exist to satisfy those profiles,
- workflows and skills expose machine-readable contracts,
- self-growth repairs are replay-tested,
- obsolete rules are retired instead of only accumulating.
