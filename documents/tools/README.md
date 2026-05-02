<!--
@dependency-start
responsibility Documents ツール入口 for this repository.
upstream design ../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# ツール入口

このディレクトリは、repo で使う補助ツールの入口です。
詳細な台帳ではなく、いま残すべき実行導線だけを整理します。

agent/worktree helper、review / validation runner、docs-check helper、container runtime helper、experiment scaffold / registry helper のうち shared canon に属するものは `vendor/agent-canon/` が正本です。
ownership と validation は [SHARED_RUNTIME_SURFACES.md](../SHARED_RUNTIME_SURFACES.md) を参照し、この文書では root 側の実行入口だけを案内します。

## 置き場所の固定ルール

- shared automation の実装は `tools/` に置きます。
- repo-local bootstrap の実装は `scripts/` に置きます。
- agent helper、CI、review、validation、container runner、experiment helper、Markdown helper は `tools/` に置きます。
- template 固有の slug 置換や bare remote 初期化だけを `scripts/` に置きます。

## よく使うもの

- `tools/ci/run_all_checks.sh`
  - 主要なチェックをまとめて実行します。
- `tools/ci/pre_review.sh`
  - review 前の基礎 gate をまとめて実行します。
- `tools/ci/run_docs_checks.sh`
  - repo-wide の Markdown 体裁とリンク監査をまとめて実行します。
- `tools/ci/run_container_pack.py`
  - repo 定義の runtime pack を build / smoke します。
- `tools/ci/run_in_repo_container.py`
  - repo workspace を mount した container command を実行します。
- `tools/ci/run_codex_in_repo_container.py`
  - nested Codex を canonical container 内で起動します。
- `tools/ci/python_env_policy.py`
  - host では `.venv` を禁止し、container では canonical `.venv` だけを許可する machine-readable helper です。
- `tools/ci/check_server_readiness.py`
  - main server host の readiness を確認します。
- `tools/ci/check_experiment_registry.py`
  - shared experiment registry contract の entrypoint と command を確認します。
- `tools/experiments/create_experiment_topic.py`
  - shared topic scaffold から experiment topic を作ります。
- `tools/experiments/sync_experiment_registry_context.py`
  - registry の branch / worktree metadata を同期します。
- `tools/experiments/run_managed_experiment.py`
  - shared managed-runner として server 上の実験 run artifact を初期化します。
- `tools/run_comprehensive_review.sh`
  - repo 全体の確認をまとめて実行します。
- `tools/run_pytest_with_logs.sh`
  - Python テストをログ付きで実行します。
- `tools/docs/check_markdown_lint.py`
  - Markdown の体裁確認です。
- `tools/docs/audit_and_fix_links.py`
  - Markdown のリンク監査です。
- `tools/docs/fix_markdown_code_blocks.py`
  - 言語未指定の fenced code block を補正します。
- `tools/docs/fix_markdown_headers.py`
  - Markdown header level の飛びを補正します。
- `tools/docs/format_markdown.py`
  - 軽い整形だけをまとめて当てます。
- `tools/docs/fix_markdown_docs.py`
  - conservatively な Markdown 整形を当てます。
- `tools/docs/find_similar_documents.py`
  - 重複・統合候補の文書を探します。
- `tools/worktree_start.sh`
  - worktree kickoff の user-facing 入口です。
- `tools/sync_agent_canon.sh`
  - shared agent canon surface の drift check と再同期です。task 開始時は `ensure-latest` で upstream `agent-canon` の最新を確認します。
- `tools/agent_tools/waterfall_gate_check.py`
  - `reports/agents/<run-id>/` の中間 waterfall gate が次段へ進める状態か確認します。
- `tools/agent_tools/goal_loop.py`
  - top-level `goal.md` の exit criteria を正本にし、達成まで iteration command を繰り返します。既定 criteria には依存解析、コード依存抽出、OOP/readability 解析、repo-wide 静的解析 / CI、objective 固有 evidence を含めます。
  - `goal_loop.py plan` は未完了の exit criteria / backlog を `Goal Work Breakdown` として `GW*` work unit へ展開します。implementation 前にこの行を run bundle `schedule.md` へ移し、bare objective から直接実装へ入らないようにします。
- Codex `goals` feature
  - `.codex/config.toml` で有効化する session goal view です。repo-owned durable state は `goal.md`、機械 gate は MCP `goal.loop_status` に置き、使い方は `agents/workflows/codex-goals-workflow.md` を正本にします。`/goal <objective>` を指定した task では、`goal_loop.py plan` の work breakdown と `/plan` の Goal Contract / evidence map を固定してから実装します。
- `mcp/repo_mcp_server.py` の `goal.loop_status`
  - MCP 経由で `goal_loop.py status` を返し、`NEXT_ACTION=run_next_iteration` / `NEXT_ACTION=close_goal_loop` を adaptive loop の機械 gate にします。
- `tools/agent_tools/evaluate_skill_workflow_prompts.py`
  - skill / workflow prompt surface を `agents/evals/skill_workflow_prompt_eval.toml` の frozen eval で検査し、prompt repair 後に `EVAL_STATUS=pass` まで rerun します。
- `tools/agent_tools/analyze_refactor_surface.py`
  - 大規模 refactor の設計見直しで、Python AST から長すぎる function / class / file と公開 method 過多を検出し、合格 score を出します。
- `tools/agent_tools/analyze_oop_readability.py`
  - Python / C++ の OOP readability を機械判定します。外部 repo や派生 template snapshot を読むときは、対象 commit、解析 path、`--exclude vendor --exclude reports` などの除外条件、Markdown / JSON report path を run bundle に残します。
- `tools/push_origin.sh`
  - commit 後の canonical push 入口です。

## 補足

- `setup_worktree.sh` などの branch/worktree 補助は例外運用用です。
- 既定運用は `main` であり、通常作業の入口にはしません。

## 参照先

- [scripts/README.md](../../scripts/README.md)
- [SHARED_RUNTIME_SURFACES.md](../SHARED_RUNTIME_SURFACES.md)
- [TOOLS_DIRECTORY.md](TOOLS_DIRECTORY.md)
