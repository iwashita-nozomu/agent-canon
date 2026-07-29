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
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill experiment-review --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
<!-- skill-tool-commands:end -->

1. Read `agents/skills/experiment-review.md`.
1. Review from the registered experiment entry before reading implementation detail:
   `experiments/registry.toml` -> topic `README.md` -> `config.yaml` -> `run.py` -> notebook.
1. Confirm the topic inner entrypoint is not confused with setup tooling:
   `python3 tools/experiments/run_managed_experiment.py --topic <topic> --variant formal -- python3 experiments/<topic>/run.py` is the canonical user-facing run route.
1. Confirm the topic code and checked-in config do not set GPU visibility, JAX
   platform, allocator, preallocation, `max_workers: 1`, or equivalent serial
   throttles unless the user explicitly requested an environment-contract change.
1. Confirm caller-owned environment is preserved by topic-created subprocesses:
   notebook execution and workers should inherit `os.environ.copy()` or default
   inheritance instead of replacing GPU/JAX runtime settings.
1. Confirm registered commands, when present, provide the topic `run.py` inner
   command to the managed runner. Confirm the managed run writes `summary.json`,
   `cases.jsonl`, config snapshot, case artifacts, and notebook output under
   `experiments/<topic>/result/<run_name>/`.
1. Confirm the notebook reads run artifacts and has a Japanese Markdown
   explanation immediately above each visualization cell.
1. Report findings first, grouped by severity. Treat registered commands that
   bypass topic `run.py`, environment hard-coding in topic code, or child
   subprocess environment reset as fix-now findings.
