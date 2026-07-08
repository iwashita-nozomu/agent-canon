---
name: agent-learning
description: Use when agent-side working philosophy, interaction lessons, task retrospectives, repeated routing misses, missed skill invocation, or recurrence-prevention feedback should be logged without mixing them into user preferences.
---
<!--
@dependency-start
contract skill
responsibility Documents Agent Learning for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Agent Learning

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill agent-learning --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/agent-learning.md`.
1. Read `agents/workflows/agent-learning-workflow.md`.
1. Treat plain `agent-learning` or `$agent-learning` in a user request as an explicit skill invocation, not only a candidate signal.
1. Select this skill for user / reviewer feedback about agent behavior, repeated misses, missed skill invocation, over-constrained routing, recurrence prevention, "こういう止まり方", task retrospectives, or agent-side memory updates.
1. Separate user preference from agent-side learning.
1. Record observable behavior with `python3 tools/agent_tools/workflow_monitor.py --report-dir reports/agents/<run-id> --behavior-event "..."`, including skill invocation, subagent routing, tool gates, prompt evals, review feedback, subagent lifecycle, and diff-check decisions.
1. Record user or reviewer feedback observed during actual use with `python3 tools/agent_tools/workflow_monitor.py --report-dir reports/agents/<run-id> --runtime-feedback "source=<user|reviewer|eval> target=<skill-or-workflow-or-eval> action=<prompt_repair|eval_update|memory_record|no_op>"`, then update the targeted skill prompt, workflow prompt, eval, or memory note before closeout.
1. When feedback says the currently used skill is weak, shallow, late, or misrouted, treat the active skill as the first repair candidate and confirm the owner before editing. Before turning feedback into a durable rule, calibrate the strength of the change; prefer scoped guidance or examples when one observation does not justify a hard rule. Reserve hard rules for invariant, checker-backed, or repeatedly observed failures. If the skill prompt changes, update both the discoverable runtime `SKILL.md` and the canonical `agents/skills/<skill>.md` owner, then update or verify the matching prompt eval.
1. Treat user or reviewer feedback about passing tests by simplification, revert, intended-behavior deletion, oracle weakening, or over-weighting test planning until owning code repair stalls as active skill feedback for `test-design` and the implementation workflow. Record it with `workflow_monitor.py --runtime-feedback` targeting `test-design` or the implementation workflow and `action=prompt_repair|eval_update`, then resolve it through prompt, eval, or tool repair. Do not close it as memory-only.
1. Treat user or reviewer feedback that algorithm repair started from test
   edits, expected-value changes, tolerance changes, or oracle changes before
   the algorithm contract and code-side repair route were fixed as active skill
   feedback for `computational-optimization`, `algorithm-proof-exploration`,
   `test-design`, and the implementation workflow. Resolve it by repairing the
   prompts so algorithm contract, public entrypoint, recurrence or state
   transition, invariant, stopping or acceptance rule, failure semantics, and
   selected code repair route come before test changes.
1. Treat feedback about excessive input tokens, repeated context loading, duplicated raw logs, or broad prose being passed into the model as active routing/context-skill feedback first. Repair the selected skill by preserving owner/dependency evidence while routing structure reading through the protocol-owned `Structure Intake Packet` and moving duplicated or bulky raw material to artifacts plus structured summaries; do not convert the feedback into a blanket rule to omit needed context.
1. Before closeout, run `python3 tools/agent_tools/evaluate_agent_run.py --report-dir reports/agents/<run-id> --behavior-manifest evidence/agent-evals/agent_behavior_eval.toml --write` and resolve any feedback actions.
1. Use `$result-artifact-writeout` when eval, hook, or skill feedback results need durable writeout; keep raw evidence, summary, manifest, and unique artifact path separate.
1. Log concise evidence-backed observations with `tools/agent_tools/log_agent_learning.py`.
1. If memory files changed, run `python3 tools/agent_tools/persist_agent_memory.py --commit --push` and, from a template superproject, also close the `vendor/agent-canon` pin with `--commit-superproject --push-superproject` or an equivalent explicit commit.
1. Keep raw chat out of notes; record source, evidence, scope, and confidence.
1. Promote only stable items into `AGENTS.md`, workflow docs, or guardrails.
