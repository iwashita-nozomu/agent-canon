---
name: save-experiment-results
description: Save and publish experiment run results with branch-safe retention. Use when Codex needs to preserve experiments/<topic>/result/<run_name>, create or verify experiment result manifests, write experiment reader reports, publish to experiment-results/<topic>, prevent overwrites, or keep failed/partial experiment runs as durable evidence.
---
<!--
@dependency-start
contract skill
responsibility Documents Save Experiment Results runtime skill for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/save-experiment-results.md human-facing save-experiment-results skill
upstream design ../../../agents/skills/experiment-lifecycle.md experiment lifecycle workflow
upstream design ../../../agents/skills/result-artifact-writeout.md durable raw/result/report artifact writeout
downstream implementation ../../../tools/experiments/publish_result_branch.py publishes formal result branches
@dependency-end
-->

# Save Experiment Results

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill save-experiment-results --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

1. Read `agents/skills/save-experiment-results.md`.
1. Start from an existing `experiments/<topic>/result/<run_name>/`. If it is
   missing, return to `$experiment-lifecycle`; do not invent a saved result from
   chat notes or report prose.
1. Write a retention plan before touching a result branch: topic, run name,
   result directory, source branch, source commit, source dirty state, result
   branch, remote publish decision, overwrite policy, and report path.
1. Preserve raw machine-readable run artifacts before deriving Markdown,
   tables, or HTML. Missing standard artifacts become explicit limitations.
1. Save failed, skipped, blocked, and partial runs with status, exit code,
   blocker, partial artifact list, and next action. They are not disposable.
1. Do not overwrite a detailed result directory. Use a new run name,
   append-only manifest entry, or a recorded cleanup task with owner and reason.
1. Keep source changes and result retention on separate branch lanes. Code,
   config, protocol, skill, tool, workflow, or report-generator changes stay on
   source branches/PRs; formal result artifacts go to
   `experiment-results/<topic>` via `publish_result_branch.py`.
1. Treat dirty-source runs as retainable but not formal success evidence. Record
   affected paths and `experiment_formal_status=not_formal_dirty_source`; rerun
   from a committed source branch or merged commit before marking the result
   formal.
1. Before creating or updating the result branch, record
   `branch_creation_reason=<reason>` and `result_branch=<branch>` in the run
   bundle, manifest, report, or PR body.
1. Add `--push` only when the retention plan calls for remote storage.
1. If a reader-facing report is requested, also use `$report-writing`; this
   skill owns raw retention and branch-safe publication, not scientific
   interpretation quality.
1. Close out with `experiment_result_save=complete`, result paths, source commit,
   dirty-state evidence, formal status, result branch, raw manifest, report
   path, and overwrite policy.
