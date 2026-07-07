---
name: agent-eval-accumulation
description: Use when accumulated AgentCanon eval evidence is missing, stale, or failing; runs registered eval producers, validates eval family accumulation, and stores evidence through the log archive instead of hand-writing reports.
---
<!--
@dependency-start
contract skill
responsibility Documents Agent Eval Accumulation for this repository.
upstream design ../../../agents/skills/agent-eval-accumulation.md documents the human-facing skill
upstream design ../../../evidence/agent-evals/README.md defines eval family contracts
upstream design ../../../documents/runtime-log-archive.md defines the archive boundary
upstream implementation ../../../tools/agent_tools/run_accumulated_agent_evals.py runs registered producers
upstream implementation ../../../tools/agent_tools/eval_accumulation_check.py validates accumulated reports
@dependency-end
-->

# Agent Eval Accumulation

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill agent-eval-accumulation --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/agent-eval-accumulation.md`.
1. Start with `python3 tools/agent_tools/eval_accumulation_check.py --root . --compact-out reports/agents/<run-id>/eval-accumulation-before.json --format text`; use the compact JSON and stdout counters as the first evidence.
1. If the checker reports missing eval family reports or stale accumulation gaps, run `python3 tools/agent_tools/run_accumulated_agent_evals.py --root . --run-id <run-id> --report-dir reports/agents/<run-id>` and pass every used skill with repeated `--skill-used <skill>`.
1. Do not hand-generate eval reports under `.agent-canon/log-archive/**` or `agents/evals/results/**`; registered producers own accumulated reports.
1. Read producer stdout / stderr summaries from `reports/agent-eval-runs/<run-id>/`; avoid broad raw archive searches. Treat those stdout / stderr files as transient, summarize the needed lines into the run bundle, then remove them before closeout.
1. Rerun `eval_accumulation_check.py` with `--compact-out reports/agents/<run-id>/eval-accumulation-after.json` and require `EVAL_ACCUMULATION=pass` plus `EVAL_ACCUMULATION_BLOCKING_FINDINGS=0` before using the accumulated evidence as green closeout evidence.
1. If a producer fails, record `workflow_monitor.py --runtime-feedback "source=eval target=<skill-or-workflow-or-tool> action=prompt_repair reason=<producer-failure>"` and repair the target surface before closing the task.
1. If a producer or `eval_accumulation_check.py` fails, record
   `failing_contract`, `observation_level`, `cause_classification`,
   `intent_preservation`, and `evidence` before treating the family as green.
   Use `intent_preservation` for the same-intent repair or escalation route.
   Do not skip producers to pass, delete intended eval/oracle coverage, weaken
   an oracle, downscope validation, or hand-write source-tree substitutes.
   Route producer bugs, oracle/spec mismatches, fixture/environment/stale
   generated artifacts, unrelated failures, and approved-design/user-request
   conflicts to owner repair, residual, or escalation.
1. After producer runs create archive artifacts, use `python3 tools/agent_tools/runtime_log_archive_git.py sync` or `push` so append-only eval evidence is saved on the log archive branch.
1. Run `python3 tools/agent_tools/generated_artifact_guard.py --root .` and require `GENERATED_ARTIFACT_GUARD=pass`; do not leave regeneratable `reports/agent-eval-runs/<run-id>/*.stdout.txt` or `*.stderr.txt` files in the source tree.
