<!--
@dependency-start
responsibility Documents ツール入口 for this repository.
upstream design ../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ../../tools/catalog.yaml structured AgentCanon tool catalog
downstream implementation ../../tools/agent_tools/tool_catalog.py validates catalog/docs consistency
downstream implementation ../../tools/agent_tools/tool_drift.py validates tool/convention trace contracts
@dependency-end
-->

# ツール入口

このディレクトリは、repo で使う補助ツールの入口です。
詳細な機械可読台帳は `tools/catalog.yaml` を正本にし、この文書では
root 側からよく使う実行導線だけを整理します。

agent/worktree helper、review / validation runner、docs-check helper、container runtime helper、experiment scaffold / registry helper のうち shared canon に属するものは `vendor/agent-canon/` が正本です。
ownership と validation は [SHARED_RUNTIME_SURFACES.md](../SHARED_RUNTIME_SURFACES.md) を参照し、この文書では root 側の実行入口だけを案内します。

## AgentCanon Tool Catalog

- `tools/catalog.yaml`
  - canonical tool と compatibility wrapper の構造化カタログです。
- `tools/agent_tools/tool_catalog.py`
  - catalog の schema、path、説明、docs/tests、default wiring、retired legacy 混入を検査し、`--format markdown` で対応表を出します。
- `tools/agent_tools/tool_drift.py`
  - dependency manifest を使い、tool / workflow / PR checklist / convention doc の trace 漏れを検出します。
- `documents/tools/tool-docs.toml`
  - tool 実装と説明文書を一対一で対応させる機械可読 map です。`tool` と `doc` は同じ basename にし、`tool_catalog.py` が path、dependency header、catalog docs wiring を検査します。

## 置き場所の固定ルール

- shared automation の実装は `tools/` に置きます。
- repo-local bootstrap の実装は `scripts/` に置きます。
- agent helper、CI、review、validation、container runner、experiment helper、Markdown helper は `tools/` に置きます。
- template 固有の slug 置換や bare remote 初期化だけを `scripts/` に置きます。
- 過去の `tools/legacy/` 配置は廃止済みです。派生 repo 由来の tool は repo-neutral に昇格するか、元 repo 側に残すか、削除判断を `documents/repo-local-tool-imports.md` に記録します。

## よく使うもの

- `tools/ci/run_all_checks.sh`
  - 主要なチェックをまとめて実行します。
- `tools/ci/pre_review.sh`
  - review 前の基礎 gate をまとめて実行します。
- `tools/ci/run_docs_checks.sh`
  - repo-wide の Markdown 体裁とリンク監査をまとめて実行します。
- `tools/ci/run_container_pack.py`
  - repo 定義の runtime pack を build / smoke します。
- `tools/ci/container_config.py`
  - Dockerfile、runtime pack、devcontainer 生成導線の静的整合を検査します。standalone AgentCanon source で `docker/` と `.devcontainer/` が無い場合は skip します。
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
- `tools/docs/find_redundant_designs.py`
  - `documents/design/` の exact duplicate を検出し、consolidation report を作ります。
- `tools/docs/find_similar_designs.py`
  - `documents/design/` の類似候補を検出します。
- `tools/docs/organize_designs.py`
  - design 文書を submodule 別に整理するための conservative report を作ります。
- `tools/docs/tfidf_similar_docs.py`
  - Markdown 文書の TF-IDF 類似候補と merge draft を作ります。
- `tools/data/jsonl_to_md.py`
  - JSONL の実行結果を Markdown table report に変換します。
- `tools/hlo/summarize_hlo_jsonl.py`
  - HLO JSONL から dialect、tag、operation count の summary JSON を出します。
- `tools/audit/audit_logger.py`
  - agent / repo automation event を JSONL audit log として保存します。
- `tools/worktree_start.sh`
  - worktree kickoff の user-facing 入口です。
- `tools/update_agent_canon.sh`
  - 派生 repo で AgentCanon submodule pin と shared root surface を更新する user-facing 入口です。通常は `make agent-canon-update-plan` で route を確認し、`make agent-canon-update` で適用します。
  - legacy subtree / snapshot route は移行互換のためだけに残し、submodule 化済み repo の通常 path にはしません。
  - source repo が設定されている場合は `refresh-remote -> ensure-latest` の順に進みます。source repo が missing / dirty なら fail-closed で止めます。
  - 派生 repo 側の shared canon 差分を upstream に渡す場合は `make agent-canon-proposal-branch` で branch を確認し、`make agent-canon-push-proposal` で proposal branch へ push します。AgentCanon PR / proposal merge 後に `make agent-canon-ensure-latest` と `bash tools/sync_agent_canon.sh link-root` で template / derived repo へ持ち帰ります。
  - GitHub 管理では `iwashita-nozomu/agent-canon` と template GitHub repo の `main` SHA、local bare mirror SHA、submodule pin を PR 本文に残します。
- `tools/sync_agent_canon.sh`
  - shared agent canon surface の drift check と再同期を行う低レベル入口です。通常の作業者は直接 `pull` せず、task 開始時の `make agent-canon-ensure-latest`、root view 修復の `make agent-canon-links`、drift check の `make agent-canon-check` 経由で使います。
  - `link-root` は symlink view と root copy surface を復元します。`goal.md` は repo-local state なので shared symlink に戻しません。
- `tools/agent_tools/waterfall_gate_check.py`
  - `reports/agents/<run-id>/` の中間 waterfall gate が次段へ進める状態か確認します。
- `tools/agent_tools/goal_loop.py`
  - top-level `goal.md` の exit criteria を正本にし、達成まで iteration command を繰り返します。既定 criteria には依存解析、コード依存抽出、OOP/readability 解析、repo-wide 静的解析 / CI、objective 固有 evidence を含めます。
  - 既定 Backlog は小さな `B1` だけではなく、prompt-to-artifact checklist、reuse / consolidation / deletion survey、cohesive implementation slice、task-relevant validation、`NEXT_ACTION=run_next_iteration` 継続判断までを 1 回目の iteration packet として持ちます。
  - `goal_loop.py init` は default active items と non-default optional items を分けます。`Exit Criteria` と `Backlog` は機械 gate の対象で、`Optional Goal Item Catalog` は必要時に active section へ昇格する候補です。
  - `goal_loop.py plan` は未完了の exit criteria / backlog を `Goal Work Breakdown` として `GW*` work unit へ展開します。implementation 前にこの行を run bundle `schedule.md` へ移し、bare objective から直接実装へ入らないようにします。
- `tools/agent_tools/vector_search.py`
  - tools、skills、workflow、documents、MCP surface を標準ライブラリ TF-IDF vector で横断検索します。
  - exact symbol / path / error message は `rg` を優先し、広い概念や既存 helper の再利用候補探索では `vector_search.py` を併用します。
  - 生成済み embedding index は commit しません。将来 external embedding を足す場合も optional layer とし、index artifact は `reports/` など ignored path に置きます。
  - 例:

```bash
python3 tools/agent_tools/vector_search.py --query "dependency header graph"
python3 tools/agent_tools/vector_search.py --surface tools --query "github cli validation"
```

- `tools/agent_tools/file_surface_inventory.py`
  - root view、submodule pin、AgentCanon source を JSON / Markdown で分類します。
  - `--submodule-aware`、`--root-only`、`--agentcanon-only` で scope を明示します。
- `tools/agent_tools/helper_function_inventory.py`
  - Python helper 関数 / クラスを AST、呼び出し元、side effect、内部 call graph、domain 別の決定論的ルールから列挙し、`auto_helper` と `needs_user_judgment` を分けて JSON / Markdown / text で出します。
- `tools/agent_tools/vendor_skill_adapters.py`
  - AgentCanon 内部の `vendor/skills/manifest.toml` と `vendor/skills/<provider>/<skill>/SKILL.md` を検査し、enabled third-party skill を `.agents/skills/<skill>` の symlink adapter として露出します。
  - `python3 tools/agent_tools/vendor_skill_adapters.py --sync` は missing adapter だけを作成し、unmanaged file は上書きしません。
- `tools/agent_tools/check_dependency_graph.sh`
  - `--list-related --focus <path>` は、変更 path が宣言する dependency edge と、その path を指す incoming edge をすべて列挙します。
- `tools/agent_tools/run_repo_dependency_review.sh`
  - `--list-changed-dependencies` は、現在の changed file ごとに related dependency surface を出力し、reviewer に渡す依存先リストを作ります。
- `tools/agent_tools/review_backlog_scan.sh`
  - file inventory、stale wording search、dependency review、code dependency scan、OOP/readability、`Any`、hardcoded-number、log-helper、convention scans を run bundle へ集約します。
  - 例:

```bash
make review-backlog-scan ARGS="--report-dir reports/agents/<run-id>"
bash tools/agent_tools/review_backlog_scan.sh --report-dir reports/agents/<run-id> --submodule-aware
```

- `tools/oop/python/readability.py`
  - Python source の OOP readability を機械判定します。説明文書は同名の `documents/tools/oop/python/readability.md` です。
- `tools/oop/python/rule_inventory.py`
  - Python OOP policy、checker、reviewer、test、説明文書の配置を確認します。説明文書は同名の `documents/tools/oop/python/rule_inventory.md` です。
- `tools/oop/cpp/readability.py`
  - C / C++ source の OOP readability を機械判定します。説明文書は同名の `documents/tools/oop/cpp/readability.md` です。
- `tools/oop/cpp/rule_inventory.py`
  - C++ OOP policy、checker、reviewer、test、説明文書の配置を確認します。説明文書は同名の `documents/tools/oop/cpp/rule_inventory.md` です。
  - 例:

```bash
python3 tools/oop/python/readability.py --format markdown python tools tests
python3 tools/oop/python/rule_inventory.py --format markdown
python3 tools/oop/cpp/readability.py --format markdown include src tests/cpp
python3 tools/oop/cpp/rule_inventory.py --format markdown
```

- Codex `goals` feature
  - `.codex/config.toml` で有効化する session goal view です。repo-owned durable state は `goal.md`、機械 gate は MCP `goal.loop_status` に置き、使い方は `agents/workflows/codex-goals-workflow.md` を正本にします。`/goal <objective>` を指定した task では、`goal_loop.py plan` の work breakdown と `/plan` の Goal Contract / evidence map を固定してから実装します。
- `mcp/repo_mcp_server.py` の `goal.loop_status`
  - MCP 経由で `goal_loop.py status` を返し、`NEXT_ACTION=run_next_iteration` / `NEXT_ACTION=close_goal_loop` を adaptive loop の機械 gate にします。
- `tools/agent_tools/evaluate_skill_workflow_prompts.py`
  - skill / workflow prompt surface を `agents/evals/skill_workflow_prompt_eval.toml` の frozen eval で検査します。skill を使う run では `--accumulate --run-id <run-id> --skill-used <skill>` を付け、`agents/evals/results/skill-workflow-prompt/` に詳細結果を蓄積します。
  - 蓄積 file は `<eval_run_id>-<status>-<skill-slug>.md` 形式です。`eval_run_id` は `skill-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-sha256-prefix>` で採番され、既存 report を上書きしません。
  - prompt repair 後に `EVAL_STATUS=pass`、`EVAL_AUDIT_STATUS=pass`、`EVAL_GROWTH_CANDIDATES=0` まで rerun します。
  - manifest audit は duplicate eval IDs、duplicate explicit targets、duplicate checklist IDs を growth candidate として fail-closed にします。既存 surface の coverage を増やす場合は並行 eval を足さず、同じ target の eval entry に checklist を統合します。
- `tools/agent_tools/compare_agent_run_paths.py`
  - 2 つの run bundle の `workflow_monitoring.md` から `execution_path`、`route_efficiency`、`static_analysis_feedback` を読み、実行経路差分と非効率経路選択を machine-readable に判定します。
  - `RUN_PATH_COMPARISON=fail`、`SELECTED_INEFFICIENT_ROUTE=yes`、`NEXT_ACTION=repair_skill_workflow_prompt` は behavior eval と adaptive-improvement prompt repair の入力にします。
- `tools/agent_tools/analyze_refactor_surface.py`
  - 大規模 refactor の設計見直しで、Python AST から長すぎる function / class / file と公開 method 過多を検出し、合格 score を出します。
- `tools/agent_tools/check_convention_compliance.py`
  - 規約 source inventory、workflow prohibition wiring、workflow verifier hook、skill-routing hook、convention tool gate wiring を集約検査します。自然言語規約の意味を完全証明する tool ではなく、機械化済み規約が workflow / prompt / CI から外れていないことを検査します。
- `tools/agent_tools/tool_catalog.py`
  - `tools/catalog.yaml` の構造、説明、default wiring、docs/tests、legacy provenance を検査します。
- `tools/agent_tools/tool_drift.py`
  - GitHub PR flow、AgentCanon PR check、dependency review、convention compliance、tool catalog の dependency-header trace を検査します。
- `tools/agent_tools/check_hardcoded_numbers.py`
  - Python / C++ source の裸の数値リテラルを検出します。既定では小さい普遍的な係数だけを許容し、Python の module-level uppercase constant、C++ の `constexpr` constant、行単位の `hardcoded-number-ok` 根拠コメントを許容します。
- `tools/agent_tools/check_static_any.py`
  - Python source の明示的な `typing.Any` を検出します。`Any` import、`Any` annotation、`typing.Any` attribute reference を fail にし、外部境界は `object`、`Mapping[str, object]`、`TypedDict`、または typed dataclass に寄せます。
- `tools/agent_tools/check_log_helper_names.py`
  - Python source のログ用 helper 関数名を検出します。ログを書き出す、emit する、保存する、整形する helper は `_log` から始め、`write_log_*` や `append_log_*` のような prefix を fail にします。
- `tools/oop/python/readability.py` / `tools/oop/cpp/readability.py`
  - Python と C/C++ の OOP readability を言語別 entrypoint で機械判定します。外部 repo、bare 展開、派生 template worktree を読むときは、対象 commit、解析 path、`--exclude vendor --exclude reports` などの除外条件、Markdown / JSON report path を run bundle に残します。
- `tools/agent_tools/check_algorithm_module_public_surface.py`
  - `algorithm_module_protocol` を使う algorithm module の公開面を検査します。標準公開名は `InitializeConfig`、`SolveConfig`、`Problem`、`State`、`Answer`、`Info`、`Algorithm`、`initialize` だけで、余計な `__all__` entry や top-level public 定義を fail にします。
- `tools/agent_tools/check_algorithm_module_nested_contract.py`
  - `algorithm_module_protocol` を使う algorithm module の nested ownership を検査します。module `B` が algorithm module `A` を import して `A.initialize` や `A.Algorithm` を使う場合、`B.InitializeConfig` / `B.SolveConfig` / `B.Info` / `B.Algorithm` がそれぞれ `A.InitializeConfig` / `A.SolveConfig` / `A.Info` / `A.Algorithm` を field として持つことを確認します。
- `tools/experiments/update_latest_result.py`
  - experiment result root の `LATEST.json` と `LATEST.md` を更新し、最新 run、summary、manifest、visual report の入口を固定します。
- `tools/push_origin.sh`
  - commit 後の canonical push 入口です。

## 結果ログと可視化

保存先、summary、可視化 artifact、retention decision は
[result-log-retention-and-visualization.md](../result-log-retention-and-visualization.md)
を正本にします。

よく使う変換:

```bash
python3 tools/data/jsonl_to_md.py <input.jsonl> <output.md>
python3 tools/hlo/summarize_hlo_jsonl.py <hlo.jsonl> > summary.json
dot -V
```

closeout では raw log だけでなく、summary/report path と可視化 path、または
可視化なしの理由を `verification.txt` に残します。

## 補足

- `setup_worktree.sh` などの branch/worktree 補助は例外運用用です。
- 既定運用は `main` であり、通常作業の入口にはしません。

## 参照先

- Template-derived repositories may add a root-local `scripts/README.md` for
  repo bootstrap scripts that are not AgentCanon-owned tools.
- [SHARED_RUNTIME_SURFACES.md](../SHARED_RUNTIME_SURFACES.md)
