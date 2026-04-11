# Shared Runtime Surfaces

この文書は、`vendor/agent-canon/` を source of truth とする runtime surface をまとめます。
template root と派生 repo root では同じ path を使い続けますが、shared canon の正本は vendor 側にあります。

## Surface Types

### symlink view

root では次を symlink view として扱います。

- `AGENTS.md`
- `agents/`
- `.agents/`
- `.claude/`
- `CLAUDE.md`
- `.github/AGENTS.md`
- `.github/copilot-instructions.md`
- `.codex/config.toml`
- `.codex/README.md`
- `.codex/agents`
- `documents/BRANCH_SCOPE.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/academic-writing-workflow.md`
- `documents/adaptive-improvement-workflow.md`
- `documents/notes-lifecycle.md`
- `documents/paper-writing-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `documents/SKILL_IMPLEMENTATION_GUIDE.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- `documents/coding-conventions-experiments.md`
- `documents/experiment-critical-review.md`
- `documents/experiment-registry.md`
- `documents/experiment-report-style.md`
- `documents/experiment-workflow.md`
- `documents/experiment_runner.md`
- `documents/implementation-waterfall-workflow.md`
- `documents/long-form-writing-workflow.md`
- `documents/main-integration-workflow.md`
- `documents/research-workflow.md`
- `documents/workflow-references.md`
- `documents/worktree-lifecycle.md`
- `documents/conventions/python/20_benchmark_policy.md`
- `documents/conventions/python/30_experiment_directory_structure.md`
- `memory/README.md`
- `memory/global`
- `memory/methods`
- `memory/candidates`
- `memory/subagent_loadouts.yaml`
- `notes/experiments/README.md`
- `notes/experiments/REPORT_TEMPLATE.md`
- `notes/experiments/results/README.md`
- `notes/branches/README.md`
- `notes/branches/BRANCH_NOTE_TEMPLATE.md`
- `notes/failures/README.md`
- `notes/failures/FAILURE_NOTE_TEMPLATE.md`
- `notes/github-mirror-procedure.md`
- `notes/guardrails/README.md`
- `notes/guardrails/engineering_avoidances.md`
- `notes/knowledge/README.md`
- `notes/knowledge/KNOWLEDGE_NOTE_TEMPLATE.md`
- `notes/knowledge/benchmark_levels_analysis.md`
- `notes/knowledge/benchmark_vs_experiment.md`
- `notes/knowledge/environment_setup.md`
- `notes/knowledge/experiment_directory_planning.md`
- `notes/knowledge/experiment_operations.md`
- `notes/knowledge/git_mirroring.md`
- `notes/knowledge/literature_intake.md`
- `notes/knowledge/path_resolution.md`
- `notes/knowledge/pyright_operations.md`
- `notes/themes/README.md`
- `notes/themes/THEME_NOTE_TEMPLATE.md`
- `notes/themes/from_another_agent.md`
- `notes/worktrees/README.md`
- `notes/worktrees/WORKTREE_LOG_TEMPLATE.md`
- `tests/agent_tools/__init__.py`
- `tests/agent_tools/test_check_agent_runtime_alignment.py`
- `tests/agent_tools/test_smoke_test_research_perspective_pack.py`
- `tests/tools/test_check_merge_structure.py`
- `tests/tools/test_mirror_skill_shims.py`
- `tests/tools/test_run_managed_experiment.py`
- `tools/`

### synced root copy

次は root 側に regular file を残しますが、正本は vendor 側です。

- `.github/workflows/agent-coordination.yml`
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`

## Editing Rule

- shared runtime surface を直すときは `vendor/agent-canon/` 側を編集します
- root 側の symlink view や copy surface を直接編集しません
- root copy が drift したら `bash tools/sync_agent_canon.sh link-root` で復元します
- drift を確認したいときは `bash tools/sync_agent_canon.sh check` を使います

## Validation

```bash
bash tools/sync_agent_canon.sh check
make agent-checks
make agent-canon-pr-check
```

## Root-Side Interpretation

- `scripts/README.md` と `documents/tools/README.md` は root 側の実行入口です
- `experiments/README.md`、`experiments/_template/`、`experiments/report/README.md`、`experiments/registry.toml`、topic 固有の `experiments/<topic>/`、`reports/`、repo-local note は root 側の正本に残します
- shared surface の ownership や upstream sync は、この文書と `documents/agent-canon-subtree-migration.md` を正本にします
