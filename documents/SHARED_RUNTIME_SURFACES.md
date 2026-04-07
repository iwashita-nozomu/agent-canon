# Shared Runtime Surfaces

この文書は、`vendor/agent-canon/` を source of truth とする runtime surface をまとめます。
product root では同じ path を使い続けますが、shared canon の正本は vendor 側にあります。

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
- `documents/agent-canon-subtree-migration.md`
- `documents/BRANCH_SCOPE.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/REVIEW_PROCESS.md`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/SKILL_IMPLEMENTATION_GUIDE.md`
- `documents/WORKFLOW_GUIDE.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- `documents/coding-conventions-experiments.md`
- `documents/experiment-critical-review.md`
- `documents/experiment-registry.md`
- `documents/experiment-report-style.md`
- `documents/experiment-workflow.md`
- `documents/experiment_runner.md`
- `documents/implementation-waterfall-workflow.md`
- `documents/research-workflow.md`
- `documents/workflow-references.md`
- `documents/worktree-lifecycle.md`
- `documents/conventions/python/20_benchmark_policy.md`
- `documents/conventions/python/30_experiment_directory_structure.md`
- `experiments/README.md`
- `experiments/_template`
- `experiments/report/README.md`
- `notes/experiments/README.md`
- `notes/experiments/REPORT_TEMPLATE.md`
- `notes/experiments/results/README.md`
- `notes/knowledge/benchmark_vs_experiment.md`
- `notes/knowledge/experiment_directory_planning.md`
- `notes/knowledge/experiment_operations.md`
- `notes/themes/from_another_agent.md`
- `notes/worktrees/README.md`
- `notes/worktrees/WORKTREE_LOG_TEMPLATE.md`
- `tests/agent_tools/__init__.py`
- `tests/agent_tools/test_smoke_test_research_perspective_pack.py`
- `tests/tools/test_mirror_skill_shims.py`
- `tests/tools/test_run_managed_experiment.py`
- `scripts/agent_tools/`
- `scripts/check_convention_consistency.py`
- `scripts/check_doc_test_triplet.py`
- `scripts/docker_dependency_validator.py`
- `scripts/requirement_sync_validator.py`
- `scripts/run_comprehensive_review.sh`
- `scripts/ci/check_experiment_registry.py`
- `scripts/ci/PRE_REVIEW_GUIDE.md`
- `scripts/ci/check_docker_build.sh`
- `scripts/ci/check_server_readiness.py`
- `scripts/ci/container_runtime.py`
- `scripts/ci/pre_review.sh`
- `scripts/ci/run_all_checks.sh`
- `scripts/ci/run_codex_in_repo_container.py`
- `scripts/ci/run_container_pack.py`
- `scripts/ci/run_docs_checks.sh`
- `scripts/ci/run_in_repo_container.py`
- `scripts/ci/run_python_in_dockerfile.py`
- `scripts/experiments/create_experiment_topic.py`
- `scripts/experiments/registry_lib.py`
- `scripts/experiments/run_managed_experiment.py`
- `scripts/experiments/sync_experiment_registry_context.py`
- `scripts/setup_worktree.sh`
- `scripts/shared/error_handler.py`
- `scripts/sync_agent_canon.sh`
- `scripts/tools/audit_and_fix_links.py`
- `scripts/tools/check_markdown_lint.py`
- `scripts/tools/check_markdown_math.py`
- `scripts/worktree_start.sh`
- `scripts/tools/check_worktree_scopes.sh`
- `scripts/tools/create_worktree.sh`
- `scripts/tools/mirror_skill_shims.py`
- `scripts/validation/triplet_validator.py`

### synced root copy

次は root 側に regular file を残しますが、正本は vendor 側です。

- `.github/workflows/agent-coordination.yml`

## Editing Rule

- shared runtime surface を直すときは `vendor/agent-canon/` 側を編集します
- root 側の symlink view や copy surface を直接編集しません
- root copy が drift したら `bash scripts/sync_agent_canon.sh link-root` で復元します
- drift を確認したいときは `bash scripts/sync_agent_canon.sh check` を使います

## Validation

```bash
bash scripts/sync_agent_canon.sh check
make agent-checks
```

## Product-Side Interpretation

- `scripts/README.md` と `documents/tools/README.md` は product 側の実行入口です
- `experiments/registry.toml`、topic 固有の `experiments/<topic>/`、product 固有 note は root 側の正本に残します
- shared surface の ownership や upstream sync は、この文書と `documents/agent-canon-subtree-migration.md` を正本にします
