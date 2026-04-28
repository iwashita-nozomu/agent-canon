# Shared Runtime Surfaces

<!--
@dependency-start
upstream design ../tools/sync_agent_canon.sh shared surface link specification
upstream design ./agent-canon-subtree-migration.md subtree ownership model
downstream implementation ../tools/sync_agent_canon.sh enforces this surface list
downstream design ./object-oriented-design.md listed shared coding policy surface
@dependency-end
-->

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
- `mcp/`
- `documents/BRANCH_SCOPE.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/DOCSTRING_GUIDE.md`
- `documents/FILE_CHECKLIST_OPERATIONS.md`
- `documents/README.md`
- `documents/object-oriented-design.md`
- `documents/dependency-manifest-design.md`
- `documents/notes-lifecycle.md`
- `documents/REVIEW_PROCESS.md`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/SKILL_IMPLEMENTATION_GUIDE.md`
- `documents/TROUBLESHOOTING.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- `documents/agent-canon-subtree-migration.md`
- `documents/coding-conventions-cpp.md`
- `documents/coding-conventions-experiments.md`
- `documents/coding-conventions-house-style.md`
- `documents/coding-conventions-logging.md`
- `documents/coding-conventions-project.md`
- `documents/coding-conventions-python.md`
- `documents/coding-conventions-reviews.md`
- `documents/coding-conventions-testing.md`
- `documents/experiment-critical-review.md`
- `documents/experiment-registry.md`
- `documents/experiment-report-style.md`
- `documents/experiment_runner.md`
- `documents/cpp-build-layout.md`
- `documents/linux-wsl-host-requirements.md`
- `documents/remote-execution-repo-contract.md`
- `documents/server-host-contract.md`
- `documents/template-bootstrap.md`
- `documents/worktree-lifecycle.md`
- `documents/conventions/README.md`
- `documents/conventions/common/01_principles.md`
- `documents/conventions/common/02_naming.md`
- `documents/conventions/common/03_comments.md`
- `documents/conventions/common/04_operators.md`
- `documents/conventions/common/05_docs.md`
- `documents/conventions/python/01_scope.md`
- `documents/conventions/python/04_type_annotations.md`
- `documents/conventions/python/06_comments.md`
- `documents/conventions/python/07_type_checker.md`
- `documents/conventions/python/09_file_roles.md`
- `documents/conventions/python/11_naming.md`
- `documents/conventions/python/15_jax_rules.md`
- `documents/conventions/python/20_benchmark_policy.md`
- `documents/conventions/python/30_experiment_directory_structure.md`
- `documents/design/README.md`
- `documents/design/protocols.md`
- `documents/templates/README.md`
- `documents/templates/remote_execution_repo.template.toml`
- `documents/templates/remote_execution_target.template.toml`
- `documents/templates/server_host_inventory.template.md`
- `documents/templates/server_runtime_layout.template.toml`
- `documents/tools/README.md`
- `documents/tools/TOOLS_DIRECTORY.md`
- `memory/README.md`
- `memory/USER_PREFERENCES.md`
- `memory/AGENT_PHILOSOPHY.md`
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
- `tests/agent_tools/test_check_mcp_inventory.py`
- `tests/agent_tools/test_work_log.py`
- `tests/agent_tools/test_smoke_test_research_perspective_pack.py`
- `tests/tools/test_check_merge_structure.py`
- `tests/tools/test_check_markdown_math.py`
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
- workflow canon は `agents/workflows/` にあり、root では `agents/` symlink view 経由で参照します
- `experiments/README.md`、`experiments/_template/`、`experiments/report/README.md`、`experiments/registry.toml`、topic 固有の `experiments/<topic>/`、`reports/`、repo-local note は root 側の正本に残します
- shared surface の ownership や upstream sync は、この文書と `documents/agent-canon-subtree-migration.md` を正本にします
