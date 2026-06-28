---
name: experiment-review
description: Use when reviewing experiment topics, run.py files, experiment registries, GPU/JAX environment ownership, notebook artifacts, or experiment README/report readiness.
---
<!--
@dependency-start
contract skill
responsibility Documents Experiment Review for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/experiment-review.md human-facing experiment review checklist
upstream design ../../../agents/skills/experiment-lifecycle.md experiment lifecycle workflow
@dependency-end
-->

# Experiment Review

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill experiment-review --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

1. Read `agents/skills/experiment-review.md`.
1. Review from the registered experiment entry before reading implementation detail:
   `experiments/registry.toml` -> topic `README.md` -> `config.yaml` -> `run.py` -> notebook.
1. Confirm the topic entrypoint is not confused with setup tooling:
   `/usr/bin/python experiments/<topic>/run.py` with no CLI options is the canonical run command.
1. Confirm the topic code and checked-in config do not set GPU visibility, JAX
   platform, allocator, preallocation, `max_workers: 1`, or equivalent serial
   throttles unless the user explicitly requested an environment-contract change.
1. Confirm caller-owned environment is preserved by topic-created subprocesses:
   notebook execution and workers should inherit `os.environ.copy()` or default
   inheritance instead of replacing GPU/JAX runtime settings.
1. Confirm registered commands, when present, call the topic `run.py` entrypoint
   directly. Confirm the direct run
   writes `summary.json`, `cases.jsonl`, config snapshot, case artifacts, and
   notebook output under `experiments/<topic>/result/<run_name>/`.
1. Confirm the notebook reads run artifacts and has a Japanese Markdown
   explanation immediately above each visualization cell.
1. Report findings first, grouped by severity. Treat registered commands that
   bypass topic `run.py`, environment hard-coding in topic code, or child
   subprocess environment reset as fix-now findings.
