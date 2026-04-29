<!--
@dependency-start
responsibility Documents ツール目録 for this repository.
upstream design ../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# ツール目録

テンプレートとして残す主要ツールだけを列挙します。
shared review / validation / container helper の source of truth は `vendor/agent-canon/` です。

## CI・検証

- `tools/ci/run_all_checks.sh`
- `tools/ci/pre_review.sh`
- `tools/ci/run_docs_checks.sh`
- `tools/ci/run_container_pack.py`
- `tools/ci/run_in_repo_container.py`
- `tools/ci/run_python_in_dockerfile.py`
- `tools/ci/run_codex_in_repo_container.py`
- `tools/ci/check_server_readiness.py`
- `tools/ci/check_experiment_registry.py`
- `tools/experiments/create_experiment_topic.py`
- `tools/experiments/sync_experiment_registry_context.py`
- `tools/experiments/run_managed_experiment.py`
- `tools/run_comprehensive_review.sh`
- `tools/run_pytest_with_logs.sh`
- `tools/push_origin.sh`

## 文書整備

- `tools/docs/check_markdown_lint.py`
- `tools/docs/check_markdown_math.py`
- `tools/docs/audit_and_fix_links.py`
- `tools/docs/fix_markdown_code_blocks.py`
- `tools/docs/fix_markdown_docs.py`
- `tools/docs/fix_markdown_headers.py`
- `tools/docs/find_similar_documents.py`
- `tools/docs/format_markdown.py`

## agent 補助

shared agent/worktree surface の ownership は `documents/SHARED_RUNTIME_SURFACES.md` を正本にします。
- `tools/sync_agent_canon.sh`
- `tools/agent_tools/analyze_refactor_surface.py`

## 例外運用

- `tools/setup_worktree.sh`
- `tools/worktree_start.sh`
- `tools/docs/create_worktree.sh`

これらは branch/worktree を使う特別な場合だけ使います。
