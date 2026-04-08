# agent-canon snapshot

このディレクトリは、shared agent canon の committed snapshot です。
将来的には外部 repo `agent-canon` の subtree 取り込み先として使いますが、外部 repo を作る前でも `git clone <template>` 直後に shared canon を参照できるよう、template 側へ実体を含めています。
agent/runtime の最小 surface だけでなく、experiment-oriented な agent set として再配布したい共通規約、review guide、validation / review runner、container runtime helper、registry tool、topic scaffold もここへ寄せます。

含むもの:
- `ROOT_AGENTS.md`
- `CLAUDE.md`
- `.github/AGENTS.md`
- `.github/copilot-instructions.md`
- `.github/workflows/agent-coordination.yml`
- `.codex/config.toml`
- `agents/`
- `.agents/skills/`
- `.claude/agents/`
- `.claude/skills/`
- `.codex/README.md`
- `.codex/agents/`
- `documents/agent-canon-subtree-migration.md`
- `documents/BRANCH_SCOPE.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/academic-writing-workflow.md`
- `documents/paper-writing-workflow.md`
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
- `experiments/_template/`
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
- `scripts/ci/PRE_REVIEW_GUIDE.md`
- `scripts/ci/check_docker_build.sh`
- `scripts/ci/check_experiment_registry.py`
- `scripts/ci/check_server_readiness.py`
- `scripts/ci/container_runtime.py`
- `scripts/ci/pre_review.sh`
- `scripts/ci/run_all_checks.sh`
- `scripts/ci/run_codex_in_repo_container.py`
- `scripts/ci/run_container_pack.py`
- `scripts/ci/run_docs_checks.sh`
- `scripts/ci/run_in_repo_container.py`
- `scripts/ci/run_python_in_dockerfile.py`
- `scripts/experiments/`
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

含まないもの:
- template root entrypoint
  - root `AGENTS.md`
- implementation / experiment / environment 本体
  - template-default implementation と shared canon 以外の `python/`
  - 派生 repo ごとの `experiments/registry.toml`
  - 派生 repo ごとの `experiments/<topic>/`
  - `docker/`
  - shared canon 以外の `notes/`

更新:

```bash
bash scripts/sync_agent_canon.sh link-root
bash scripts/sync_agent_canon.sh check
```

既存の `snapshot` command は後方互換 alias として残しています。

外部 repo ができたら、次で upstream sync へ移れます。

```bash
bash scripts/sync_agent_canon.sh add git@github.com:<org>/agent-canon.git
bash scripts/sync_agent_canon.sh pull
bash scripts/sync_agent_canon.sh push
```
