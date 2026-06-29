<!--
@dependency-start
contract reference
responsibility Documents ツール入口 for this repository.
upstream design ../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ../runtime-profiles-and-check-matrix.md runtime profile and validation routing policy
upstream design ../../tools/catalog.yaml structured AgentCanon tool catalog
upstream design ../prose-reasoning-graph/dsl-spec.md graph visualization projection contract
downstream implementation ../../tools/agent_tools/tool_catalog.py validates catalog/docs consistency
downstream implementation ../../tools/agent_tools/tool_drift.py validates tool/convention trace contracts
downstream implementation ../../tools/agent_tools/responsibility_scope.py validates responsibility scope ownership
downstream implementation ../../tools/agent_tools/issue_sync.py validates local issue sync state
downstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates eval result accumulation
downstream implementation ../../tools/agent_tools/runtime_log_archive_git.py manages mounted hook/eval/report log archive branches
downstream implementation ../../tools/agent_tools/generated_artifact_guard.py rejects regenerated report outputs left in source tree
downstream implementation ../../tools/agent_tools/check_design_doc_claims.py validates design-document evidence claims
downstream design dependency-tools-and-licenses.md documents dependency tool purposes and license evidence
downstream design ../../tools/user/README.md defines stable user-facing tool entrypoint migration target
downstream design ../../tools/internal/README.md defines skill, workflow, and compatibility helper migration targets
downstream implementation ../../rust/agent-canon/src/local_llm.rs runs local LLM CLI commands
downstream implementation ../../rust/agent-canon/src/semantic_index.rs runs semantic vector index commands
downstream implementation ../../rust/agent-canon/src/structured_analysis.rs runs structured-analysis cache build, document inventory, and DB import commands
downstream implementation ../../rust/agent-canon/src/test_design.rs runs test design resilience diagnostics
downstream implementation ../../tools/agent_tools/file_responsibility_llm.py keeps the Python local LLM compatibility helper
downstream implementation ../../tools/agent_tools/local_llm_eval.py runs local LLM responsibility eval engine
downstream implementation ../../tools/agent_tools/evaluate_report_quality.py runs report quality evals
downstream implementation ../../tools/agent_tools/search.py coordinates purpose-based search providers
downstream implementation ../../tools/agent_tools/search_index.py builds repo-local semantic search cards
downstream implementation ../../tools/agent_tools/prose_reasoning_graph.py builds prose graph projections and handoff packets
downstream implementation ../../tools/agent_tools/compare_agent_run_paths.py compares run-bundle route efficiency
downstream implementation ../../tools/agent_tools/formal_proof.py builds formal-proof scaffold plans
downstream implementation ../../tools/agent_tools/lean_proof_env.py creates Mathlib/Aesop Lean proof environments
downstream implementation ../../tools/agent_tools/tool_proof_coverage.py reports tool proof-obligation coverage
downstream design lean_capability_matrix.md records Lean/Mathlib/Aesop feature routing for proof tasks
downstream implementation ../../tools/agent_tools/jit_canonical_ir.py extracts StableHLO-derived JIT-canonical IR and backend traces
downstream implementation ../../tools/agent_tools/cpp_source_canonical_ir.py extracts C++ source-canonical IR into thin operational IR
downstream implementation ../../tools/agent_tools/operational_ir_to_lean.py renders thin operational IR into Lean evidence definitions
downstream implementation ../../tools/agent_tools/cpp_template_to_lean.py fully expands C++ template source roots into Lean evidence
downstream implementation ../../rust/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR into Lean evidence modules
@dependency-end
-->

# ツール入口

このディレクトリは、repo で使う補助ツールの入口です。
詳細な機械可読台帳は `tools/catalog.yaml` を正本にし、この文書では
root 側からよく使う実行導線だけを整理します。

agent/worktree helper、review / validation runner、docs-check helper、container runtime helper、experiment scaffold / registry helper のうち shared canon に属するものは `vendor/agent-canon/` が正本です。
ownership と validation は [SHARED_RUNTIME_SURFACES.md](../SHARED_RUNTIME_SURFACES.md) を参照し、この文書では root 側の実行入口だけを案内します。
実行する tool は [Runtime Profiles And Check Matrix](../runtime-profiles-and-check-matrix.md) の active profile と changed path で選びます。

## この文書の読み方

この文書は、AgentCanon tool docs の reader-facing hub です。まず Where To Start で構造化 catalog、tool docs map、docs check、tool drift、dependency tool、graph visualization の入口を選びます。次に Tool Catalog と Tool Detail Notes で tool ごとの責務を確認し、Evidence / Assumption Ledger、置き場所の固定ルール、よく使うもの、結果ログと可視化へ進みます。正確な tool registry は prose ではなく `tools/catalog.yaml` と `documents/tools/tool-docs.toml` を優先します。

## Where To Start

This file explains the tool documentation surface. It is not a duplicate
registry. When a task needs the exact command list, read the structured source
first and then return here only for reader-facing context.

| Need | Start Here | Notes |
| --- | --- | --- |
| Decide whether a tool exists, who may call it, or whether it is retired | `tools/catalog.yaml` | Canonical registry for status, audience, placement, docs, tests, and wiring. |
| Find one reader-facing document for a tool | `documents/tools/tool-docs.toml` | One-to-one map validated by `tool_catalog.py`; do not mirror it as prose. |
| Run Markdown, link, math, Mermaid, or runtime-profile docs checks | `tools/bin/agent-canon docs check` | Use `docs format`, `docs fix-math`, or `docs fix-mermaid` only for mechanical repairs. |
| Check tool catalog or drift after docs / tool edits | `tools/agent_tools/tool_catalog.py`, `tools/agent_tools/tool_drift.py` | These are validation commands, not reader navigation lists. |
| Understand dependency tool purpose and license evidence | [Dependency Tools And Licenses](dependency-tools-and-licenses.md) | Human-facing summary of external tools and license evidence. |
| Check design-document claims against code and dependency evidence | [check_design_doc_claims.py](check_design_doc_claims.md) | Use before accepting implementation-backed design prose or structure-refactor handoff claims. |
| Understand root `tools/` execution behavior | `tools/README.md` | Execution-facing hub for the symlink view and common commands. |
| Understand graph visualization outputs | `documents/prose-reasoning-graph/dsl-spec.md`, then the same-named tool doc | Graph HTML, DOT, Mermaid, and dashboard diagrams are DSL projection or adapter artifacts. |

## AgentCanon Tool Catalog

`tools/catalog.yaml` owns the structured catalog. Each effective entry has:

- `audience`: who should call the tool directly: `user`, `agent`, `skill`,
  `workflow`, `maintainer`, or `internal`.
- `placement`: where the implementation or wrapper belongs after migration,
  such as `user_entrypoint`, `skill_helper`, `workflow_helper`,
  `validation_checker`, `ci_gate`, `compatibility_wrapper`, or
  `support_library`.
- docs and test wiring, validated by `tools/agent_tools/tool_catalog.py`.

`tools/user/` and `tools/internal/` are migration targets, not second catalogs.
Existing command paths remain stable until catalog entries, tests, docs, and
callers move together.

## Tool Detail Notes

Detailed tool behavior belongs in the same-named tool document or in
`tools/catalog.yaml`. This hub keeps only the families a reader usually needs
to choose a route:

- Catalog, drift, and pre-edit routing checks: `tool_catalog.py`,
  `tool_drift.py`, `tool_rejection_preflight.py`, `responsibility_scope.py`,
  and `import_responsibility.py`. `tool_rejection_preflight.py` reports a
  `responsibility_scope` gate with the owner scope, class, and protecting tools
  from `responsibility-scope.toml`.
- Runtime evidence and generated output guards: `runtime_log_archive_git.py`,
  `eval_accumulation_check.py`, `run_accumulated_agent_evals.py`, and
  `generated_artifact_guard.py`.
- Repo structure, issue, and PR support: `repo_structure_contract.py`,
  `issue_sync.py`, `github_publish.py`, `classify_path_risk.py`, and
  `render_dependency_manifest_graph.py`.
- Search and prose structure: `agent-canon local-llm ...`,
  `agent-canon semantic-index ...`, `prose_reasoning_graph.py`, and
  `tools/agent_tools/route.py --area search`.
- Proof, algorithm, and test design: `formal_proof.py`, `lean_proof_env.py`,
  `tool_proof_coverage.py`, `jit_canonical_ir.py`,
  `cpp_template_to_lean.py`,
  `agent-canon jit-ir-to-lean`, and `agent-canon test-design check`.

Graph visualization follows the Prose Reasoning Graph DSL projection contract.
`render_dependency_manifest_graph.py`, `semantic_provider_html_report.py`, and
runtime dashboard diagrams are adapters or projections; their domain producers
keep validation authority. Proof and JIT-canonical IR tools provide source facts
that future graph viewers map through the same DSL contract.

## Evidence And Assumption Ledger

- Evidence sources:
  `../structured-analysis/graph-dsl.md`,
  `../prose-reasoning-graph/dsl-spec.md`,
  `../../rust/agent-canon/src/structured_analysis.rs`, and
  `../../tools/agent_tools/render_dependency_manifest_graph.py`.
- Assumption:
  Graph DSL terms in this tool index describe shared storage and projection
  vocabulary. Standard-form / 標準形 terms stay with the design-claim checker
  contract. Individual tools keep pass/fail authority for their native domain.
- Parent-doc alignment:
  `../structured-analysis/graph-dsl.md` owns Graph DSL Core storage. The prose
  reasoning graph DSL owns prose adapter vocabulary used by prose workflows.

When a reader needs exact options, run the command with `--help` or open the
same-named file under `documents/tools/`. Do not expand this README into a
second command manual.

## 置き場所の固定ルール

- shared automation の実装は `tools/` に置きます。
- repo-local bootstrap の実装は `scripts/` に置きます。
- agent helper、CI、review、validation、container runner、experiment helper、Markdown helper は `tools/` に置きます。
- template 固有の slug 置換や bare remote 初期化だけを `scripts/` に置きます。
- 過去の `tools/legacy/` 配置は廃止済みです。派生 repo 由来の tool は repo-neutral に昇格するか、元 repo 側に残すか、削除判断を `documents/repo-local-tool-imports.md` に記録します。

## よく使うもの

- `tools/ci/run_all_checks.sh`
  - full confidence が必要な時に主要なチェックをまとめて実行します。docs-focused / focused code では check matrix に従って個別 check を選びます。
- `tools/ci/pre_review.sh`
  - review 前の基礎 gate をまとめて実行します。
- `tools/bin/agent-canon docs check`
  - Rust の統合 docs checker です。Markdown lint、link、math、Mermaid、bootstrap docs、runtime profile inventory drift をまとめて実行します。
- `tools/agent_tools/check_design_doc_claims.py`
  - design document の claim line を dependency header closure、implementation evidence、parent documents と比較し、Evidence And Assumption Ledger、DSL / standard-form terms、parent-doc alignment を機械的に確認します。
- `tools/ci/run_container_pack.py`
  - repo 定義の runtime pack を build / smoke します。
- `tools/ci/container_config.py`
  - repo-local Dockerfile / runtime pack と AgentCanon-owned devcontainer 生成導線の静的整合を検査します。`docker/` が無くても `.devcontainer/` があれば shared devcontainer source を検査します。
- `tools/ci/scan_secrets.sh`
  - `gitleaks`、`trufflehog`、`detect-secrets` をまとめて実行する公開 repo 向けの secret audit 入口です。既定では current tree と full git history を走査します。scanner は shared devcontainer の `post-create.sh` で導入されます。
  - 例: `bash tools/ci/scan_secrets.sh --root .`、submodule 側は `bash tools/ci/scan_secrets.sh --root vendor/agent-canon`。
- `tools/bin/agent-canon`
  - AgentCanon Rust CLI の stable wrapper です。
    `${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}/agent-canon/bin/agent-canon`
    が devcontainer post-create で install 済みならそれを使い、未 install
    で `cargo` がある場合は `vendor/agent-canon/rust/agent-canon` の source
    から実行します。installed binary が checked-out Rust source より古い場合も
    source から実行し、AgentCanon 最新化後の stale binary を避けます。
  - `rust-migration-audit` の `--root` は AgentCanon source root を指します。
    standalone AgentCanon checkout では `--root .`、template / derived repo
    では `--root vendor/agent-canon` を使います。
  - `rust-migration-plan` も AgentCanon source root を指します。AgentCanon を
    最新化した template / derived repo は、DevContainer を作り直したあと
    `agent-canon rust-migration-plan --root vendor/agent-canon --limit 12` で
    次に Rust 化する tool 候補を確認します。
  - `local-llm classify-responsibility` は単一 file 責務分析の Rust CLI
    入口です。`route-implementation-surface` は実装前に primary owner と
    required pre-edit checks を返します。`search`、`build-index`、`eval`
    もこの CLI surface から呼び、Python 実装は互換 engine として残します。
    `extract-prose-ir` は document / term part prompt を作り、`llama-cli` が
    利用可能な場合は `--llm-jobs` で bounded parallel に実行してから
    deterministic prose IR を出します。
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
- `tools/validation/notebook_quality.py`
  - default notebook directories の `.ipynb` を、細かい test ではなく、説明付きで部分実行しやすい実用 demo として読めるか検査します。
  - Codex hook では changed notebook だけを見て、`assert`、`pytest`、`test_` 関数、保存済み error output、可視化 code 不在を block します。
- `tools/experiments/create_experiment_topic.py`
  - shared topic scaffold から experiment topic を作ります。
- `tools/experiments/sync_experiment_registry_context.py`
  - registry の branch / worktree metadata を同期します。
- `tools/experiments/run_managed_experiment.py`
  - shared managed-runner として server 上の実験 run artifact を初期化し、command / environment / source snapshot、artifact manifest、startup / stdout / stderr log を保存します。
- `tools/experiments/html_artifact_access.py`
  - SSH 越しの HPC / container 上にある HTML artifact を手元 PC のブラウザで見るため、`python3 -m http.server`、SSH tunnel、local URL の command を出します。
- `tools/run_comprehensive_review.sh`
  - Large delivery / maintenance profile で repo 全体の確認をまとめて実行します。
- `tools/run_pytest_with_logs.sh`
  - Python テストをログ付きで実行します。
- `tools/bin/agent-canon docs format`
  - Markdown の機械整形を実行し、同じ入口で隣接 check まで閉じます。
- `tools/docs/fix_markdown_code_blocks.py`
  - 言語未指定の fenced code block を補正します。
- `tools/docs/fix_markdown_headers.py`
  - Markdown header level の飛びを補正します。
- `tools/bin/agent-canon docs fix-math`
  - Markdown 数式記法を単一ドルの inline 形式と二重ドルの display 形式へ機械修正し、隣接 check を実行します。
- `tools/bin/agent-canon docs fix-mermaid`
  - Markdown 内の Mermaid fenced block を補正し、予約語 node id の衝突を避け、隣接 check を実行します。
- `tools/docs/fix_markdown_docs.py`
  - conservatively な Markdown 整形を当てます。
- `tools/docs/find_similar_documents.py`
  - document maintenance profile で重複・統合候補の文書を探します。
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
  - audit profile で agent / repo automation event を JSONL audit log として保存します。
- `tools/worktree_start.sh`
  - worktree kickoff の user-facing 入口です。
- `tools/update_agent_canon.sh`
  - 派生 repo で AgentCanon submodule pin と shared root surface を更新する user-facing 入口です。通常は `make agent-canon-update-plan` で route を確認し、`make agent-canon-latest` で tool-first に適用します。
  - `latest` は safe な AgentCanon `main` 更新、legacy eval / hook log parking、root view check、親 repo update TODO routing / acknowledge まで進めます。dirty submodule が legacy `agents/evals/results/` だけなら `runtime_log_archive_git.py import-legacy|import-eval-results --delete-source` で `.agent-canon/log-archive/legacy-import/` へ退避してから続行します。新規蓄積は `.agent-canon/log-archive/` を使い、source tree の `agents/evals/results/` を新規作成しません。pending TODO が残る場合も更新コマンドは成功終了し、`AGENT_CANON_LATEST_TOOL_RESULT=updated_with_pending_todos` と `NEXT_ACTION=apply_agent_canon_update_todos_then_rerun_latest` を出します。runtime source、local shared-canon branch、diverged history、merge conflict は消さず、`AGENT_CANON_LATEST_WORKFLOW`、`AGENT_CANON_LATEST_CONFLICT_COMMAND`、`NEXT_ACTION=run_agentcanon_conflict_workflow` を出して agent workflow に渡します。dirty state を伴う通常運用では、手作業 stash ではなく `merge-main-into-current-preserve-dirty` を使います。
  - Local bare / proposal / snapshot refresh route は user-facing command から外しています。submodule 化済み repo の通常 path は GitHub branch と AgentCanon PR です。
  - 派生 repo 側の shared canon 差分を upstream に渡す場合は、`vendor/agent-canon/` 内で commit し、`bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty` で GitHub `main` を current branch に取り込み、validation 後にその branch を GitHub へ push して AgentCanon PR を開きます。
  - AgentCanon PR merge 後に `make agent-canon-ensure-latest` で template / derived repo へ持ち帰ります。この target は `make agent-canon-latest` と同じ high-level route です。
  - GitHub 管理では `iwashita-nozomu/agent-canon` と template GitHub repo の `main` SHA、AgentCanon PR URL、submodule pin を PR 本文に残します。
- `tools/agent_tools/agent_canon_update_todos.py`
  - AgentCanon pin 更新後に、親 repo の agent が先に消化する TODO を `vendor/agent-canon/documents/agent-canon-update-tasks.toml` から抽出します。
  - 親 repo の進捗は `.agent-canon/update-state.toml` にだけ残し、生成された pending view は `.agent-canon/.gitignore` で ignored にします。
  - `pending` は停止ではなくルーティングです。`plan --write` で TODO view を出し、`complete` または `defer` で解決記録を残してから `acknowledge` で `tasks_applied_through` を進めます。
- `tools/rebuild_agent_tools.sh`
  - AgentCanon pin 更新後に `${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}` 配下の compiled AgentCanon tools を source commit に合わせます。
  - uncommitted Rust source が installed binary より新しい場合も再ビルドし、作業中の CLI smoke が stale binary を使わないようにします。
  - `make agent-canon-ensure-latest`、`make agent-canon-latest`、`make agent-canon-update` は同じ high-level latest route に入り、その safe path から自動的に呼ばれます。
  - `AGENT_CANON_TOOL_REBUILD_RUST=skipped_missing_cargo` が出た場合は、DevContainer 内で再実行するか Rust toolchain を用意してから `make agent-canon-rebuild-tools` を実行します。
- `tools/install_llama_cpp.sh`
  - llama.cpp を `${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}` 配下に build し、`llama-cli` と `llama-server` を公開します。
  - PostCreate では `--allow-fetch` で取得と build を行い、AgentCanon update 後の rebuild では既存 checkout を再コンパイルします。
  - Local LLM の llama.cpp build は CPU-only です。`AGENT_CANON_LLAMA_CPP_CUDA=auto|1|cuda` は互換入力として受け付けますが、GPU build には切り替えません。
  - `AGENT_CANON_LLAMA_CPP_CMAKE_ARGS` は追加 CMake flags、`AGENT_CANON_LLAMA_CPP_BUILD_JOBS` は build 並列数です。GPU accelerator を有効化する CMake flags は CPU-only policy violation として失敗させます。
  - CPU-only CMake flag の組み合わせは build cache key として記録されます。source が新しくなくても設定が変わった場合は `already_current` にせず再ビルドします。
  - 既定 model selector は `ggml-org/SmolLM3-3B-GGUF:Q4_K_M` です。model weights は lazy fetch で、repo にコミットしません。
- `tools/agent_tools/route.py`
  - 長い候補 tool / skill 名を短い route area へ解決します。
  - 例: `profile_surface_resolver.py` は `route.py --area surface`、`$runtime-capability-routing` は `route.py --area runtime` として扱います。
  - 新しい public tool / skill を足す前に `python3 tools/agent_tools/route.py --name <candidate>` で既存 route に畳めるか確認します。
- `tools/sync_agent_canon.sh`
  - shared agent canon surface の drift check と再同期を行う低レベル入口です。通常の作業者は直接 `pull` せず、task 開始時の latest route、root view 修復の link-root route、drift check の `bash tools/sync_agent_canon.sh check` 経由で使います。
  - `link-root` は symlink view と root copy surface を復元します。`goal.md` は repo-local state なので shared symlink に戻しません。
- `tools/agent_tools/waterfall_gate_check.py`
  - `reports/agents/<run-id>/` の中間 waterfall gate が次段へ進める状態か確認します。
- `tools/agent_tools/goal_loop.py`
  - top-level `goal.md` の exit criteria を正本にし、達成まで iteration command を繰り返します。既定 criteria には依存解析、コード依存抽出、OOP/readability 解析、repo-wide 静的解析 / CI、objective 固有 evidence を含めます。
  - 既定 Backlog は `B1` 単体だけではなく、prompt-to-artifact checklist、reuse / consolidation / deletion survey、cohesive implementation slice、task-relevant validation、`NEXT_ACTION=run_next_iteration` 継続判断までを 1 回目の iteration packet として持ちます。
  - `goal_loop.py init` は default active items と non-default optional items を分けます。`Exit Criteria` と `Backlog` は機械 gate の対象で、`Optional Goal Item Catalog` は必要時に active section へ昇格する候補です。
  - `goal_loop.py plan` は未完了の exit criteria / backlog を `Goal Work Breakdown` として `GW*` work unit へ展開します。implementation 前にこの行を run bundle `schedule.md` へ移し、bare objective から直接実装へ入らないようにします。
- `tools/agent_tools/vector_search.py`
  - tools、skills、workflow、documents、MCP surface を標準ライブラリ TF-IDF vector で横断検索します。
  - exact symbol / path / error message は `git grep` または直接 path 確認を使い、広い概念や既存 helper の再利用候補探索では `vector_search.py` を併用します。
  - `--context` は search hit を dependency header の upstream / downstream に展開し、Python AST の direct call graph から focus 関数の callee / caller context も出します。
  - `--dependency-depth` で複数 hop を辿り、`--symbol` で特定 Python 関数 / class / method を context seed にできます。
  - 生成済み embedding index は commit しません。将来 external embedding を足す場合も optional layer とし、index artifact は `reports/` など ignored path に置きます。
  - SQLite-backed semantic candidates が必要な場合は `agent-canon semantic-index` を使います。
  - 例:

```bash
agent-canon local-llm search --purpose "dependency header graph tool"
agent-canon local-llm search --purpose "github cli validation" --providers llm,tool,vector
python3 tools/agent_tools/route.py --area search
python3 tools/agent_tools/vector_search.py --query "dependency header graph"
python3 tools/agent_tools/vector_search.py --surface tools --query "github cli validation"
python3 tools/agent_tools/vector_search.py --surface . --query "solver logging" --context
python3 tools/agent_tools/vector_search.py --surface python --query "initialize info" --context --symbol initialize
```

- `tools/agent_tools/file_surface_inventory.py`
  - root view、submodule pin、AgentCanon source を JSON / Markdown で分類します。
  - `--submodule-aware`、`--root-only`、`--agentcanon-only` で scope を明示します。
- `agent-canon structured-analysis build --root . --profile manual`
  - user-home cache に `prose_graph.sqlite` と `diagnostics.sqlite` を作り、
    source file から中間表現 DB と warning DB を再生成します。`--out-dir`
    を指定した場合は、その artifact root に `document_inventory.json`、
    `exports/document_inventory.md`、`structured_analysis_build.json`、
    `exports/structured_analysis_summary.md` を出力します。
- `agent-canon structured-analysis graph-contract --db <prose_graph.sqlite>`
  - Graph DSL Core の storage contract に対して、materialized DB の table、row、
    layer、edge endpoint、JSON payload、diagnostic target を検査します。`--db`
    なしでは contract summary と layer registry を出します。
  - Graph projection vocabulary は source-truth anchor / source span、
    lower graph / lower text unit、typed relation、projection view /
    derived projection、reader-state、macro-claim、node record / nodes
    table、edge record / edges table、`payload_json` を共通語彙として扱います。
- `agent-canon structured-analysis document-inventory --root .`
  - Markdown / text 文書を棚卸しし、runtime mirror、generated evidence、closed issue record、missing dependency manifest、重複見出しなどの非正本候補を正本候補と一緒に出します。
  - 文書整理では `$document-canon-cleanup` と組み合わせ、候補 report を削除 authority ではなく triage evidence として扱います。
- `tools/agent_tools/reference_materializer.py`
  - consulted PDF / HTML source を Markdown に変換し、`references/external/` に source URL、content hash、抽出方法、抽出テキストを残します。
  - `reference_capture_guard.py` の未登録 URL block を解消する canonical tool です。PDF の代わりに同等 HTML を参照した場合も、HTML source URL を Markdown reference に登録します。
- `.codex/hooks/cause_investigation_guard.py`
  - `PreToolUse` で `apply_patch` や編集系 shell / python が code path を触る直前だけ cause investigation evidence を要求します。
  - `Observation:`、`Hypothesis:` / `Root Cause:`、`Expected Fix Surface:` / `Selected Surface:`、`Validation Before Edit:` / `Support Evidence:` を含む run artifact、issue、または design note が無い code edit を block し、log に `cause_evidence_status` と `code_paths` を残します。
- `tools/agent_tools/helper_function_inventory.py`
  - Python helper 関数 / クラスを AST、呼び出し元、side effect、内部 call graph、domain 別の機能ベース rule から列挙し、`auto_helper`、`needs_user_judgment`、`redundant_helper` を分けて JSON / Markdown / text で出します。
  - `redundant_helper` は identity return、pass-through call wrapper、normalized body が重複する helper 実装を表し、`redundancy_rule` と `redundant_with` を出します。
  - `searchable_name`、`name_search_rule`、`matched_role_name_tokens` は、AST から推定した role と identifier 内の role/action token の対応を出します。`--only-name-gaps` は、責務検索で見つけやすい名前へ寄せる review 対象だけを抽出します。
  - `--changed --baseline-ref HEAD` は変更 Python file だけを報告対象にし、baseline に既に存在した finding を除外します。hook や refactor review では既存 backlog を毎回 block せず、新規 finding だけを見るために使います。
  - `helper_first_guard.py` は `helper_function_inventory.py --changed --baseline-ref HEAD --format json` の record を読み、test / docs / issue / responsibility-scope などの ownership evidence がない helper-like function 追加を block します。log には accepted / blocked の両方を分析できる `helper_candidate_records` と、blocking subset の `helper_first_records` を残し、prompt / skill eval の改善材料にします。
  - `library_implementation_guard.py` は `vendor/**`、`site-packages`、`node_modules`、`responsibility-scope.toml` の `external_dependency` scope を protected library implementation として扱い、既存 file の直接 rewrite を block します。外部実装は wrapper / adapter、fork / upstream patch、または manifest-backed vendor import で扱います。
- `tools/agent_tools/vendor_skill_adapters.py`
  - AgentCanon 内部の `vendor/skills/manifest.toml` と `vendor/skills/<provider>/<skill>/SKILL.md` を検査し、enabled third-party skill を `.agents/skills/<skill>` の symlink adapter として露出します。
  - GitHub 由来の skill では `provider`、`upstream` owner、`vendor/skills/<provider>/<skill-id>/` source path の一致を検査し、外部 repo が root や canonical skill path に直接入るのを防ぎます。
  - `python3 tools/agent_tools/vendor_skill_adapters.py --sync` は missing adapter だけを作成し、unmanaged file は上書きしません。
- `tools/agent_tools/check_dependency_graph.sh`
  - `--list-related --focus <path>` は、変更 path が宣言する dependency edge と、その path を指す incoming edge をすべて列挙します。
  - GitHub path-constraint root copy は、`vendor/agent-canon` がある場合に AgentCanon source context で dependency path を解決します。
- `tools/agent_tools/run_repo_dependency_review.sh`
  - `--list-changed-dependencies` は、現在の changed file ごとに related dependency surface を出力し、reviewer に渡す依存先リストを作ります。
- `tools/agent_tools/review_backlog_scan.sh`
  - standalone AgentCanon、template root、derived repo の repo-cross inspection run です。
  - goal / maintainer / audit profile の tool であり、通常の owner-bounded route では required gate にしません。
  - file inventory、stale wording search、dependency review、code dependency scan、OOP/readability、`Any`、hardcoded-number、log-helper、convention scans を run bundle へ集約します。
  - 既定で `agent-canon semantic-index` も実行し、responsibility-scoped merge candidates、thin docs、任意の long-query search を review artifact として JSONL 保存し、`eval-output` の JSON report も残します。LLM embedding provider が明示された場合だけ provider-comparison report も保存します。
  - template / derived repo では `--submodule-aware` を既定にし、root surface と `vendor/agent-canon` source を別 scope として扱います。
  - PR readiness 前に、出力された inventory と dependency graph から、AgentCanon-owned source、template/root local state、synced copy、symlink view、GitHub path-constraint copy、project-owned artifact のどれを編集 / 検証するかを明示します。
  - 例:

```bash
make review-backlog-scan ARGS="--report-dir reports/agents/<run-id>/cross_repo_inspection --submodule-aware"
bash tools/agent_tools/review_backlog_scan.sh \
  --report-dir reports/agents/<run-id>/cross_repo_inspection \
  --submodule-aware
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
  - `.codex/config.toml` で有効化する session goal view です。repo-owned durable state は `goal.md`、機械 gate は `goal_loop.py status` に置き、使い方は `agents/workflows/codex-goals-workflow.md` を正本にします。`/goal <objective>` を指定した task では、`goal_loop.py plan` の work breakdown と `/plan` の Goal Contract / evidence map を固定してから実装します。
- `tools/agent_tools/evaluate_skill_workflow_prompts.py`
  - skill / workflow prompt surface を `evidence/agent-evals/skill_workflow_prompt_eval.toml` の frozen eval で検査します。skill を使う run では `--accumulate --run-id <run-id> --skill-used <skill>` を付け、`.agent-canon/log-archive/eval-results/skill-workflow-prompt/` に詳細結果を蓄積します。agent が読む場合は `--compact-out <path>.json` を併用し、stdout ではなく compact JSON の統計を読んでから必要な artifact へ drill down します。
  - hook JSONL、eval report、Codex runtime summary、`reports/agents/` の agent run report は `git@github.com:iwashita-nozomu/agent-canon-log.git` を `.agent-canon/log-archive/` に mount して蓄積します。branch / push 手順は `documents/runtime-log-archive.md` を正本にし、通常操作は `tools/agent_tools/runtime_log_archive_git.py sync` を使います。個別修復時の subcommand set は `tools/agent_tools/runtime_log_archive_git.py` が所有します。
  - `generate_agent_improvement_guide.py` は `memory/`、mounted `.agent-canon/log-archive/eval-results/skill-workflow-prompt/`、mounted hook archive、`issues/open|closed/` を読んで PR / branch push 用の改善指南書を生成します。生成は read-only で、skill usage、hook event、tool name、checker target、protocol feedback token の不足をまとめ、実修正は local Codex に渡します。
  - `generate_agent_runtime_dashboard.py` は同じ evidence tree を人間が見るための dashboard にします。正本ログの場所、hook namespace、entry 数、skill usage、prompt route 候補、human feedback、eval report family、issue 数を Markdown に出し、GitHub Actions では AgentCanon repo の Step Summary と artifact にだけ出します。agent がログ分析するときは `--compact-out` で token-light summary、generated drilldown、prompt/token rolling trend を生成し、通常分析では raw JSONL を開かずそれを読みます。token 利用は lifetime total だけではなく recent moving average と coverage status で判断します。足りない詳細は raw log 検索ではなく dashboard tool の追加 summary として生成し、raw JSONL は tool 実装、schema debugging、corruption audit の explicit rationale がある場合だけ使います。
  - `run_accumulated_agent_evals.py` は同じ evidence tree の required eval family を機械的に追記する入口です。role、skill/workflow prompt、local LLM、workflow-selection、report-quality の各 eval を `--accumulate` で実行し、標準出力は log file に捕捉します。
  - `eval_accumulation_check.py` は同じ evidence tree の構造 gate です。hook JSONL、skill eval report、local LLM eval report、unique id、ignore rule を検査し、改善指南書が読めない evidence を早期に止めます。agent-facing run では `--compact-out <path>.json` を使い、finding 全件は JSON summary 側へ逃がします。
  - `evaluate_workflow_selection.py` は `evidence/agent-evals/workflow_selection_eval.toml` の固定 prompt case で workflow routing を検査します。`--accumulate` を付けた run は `.agent-canon/log-archive/eval-results/workflow-selection/` に詳細結果を蓄積します。
  - `evaluate_codex_agent_roles.py` は subagent role TOML ごとに `explorer` read-only、reviewer findings-first、`spark_worker` bounded implementation、禁止事項、model cost bucket、task routing、token / latency / retry / parent intervention / format violation / output-used metrics の受け口を検査します。agent-facing run では `--compact-out <path>.json` を使い、model matrix と finding detail は artifact で読む運用にします。
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
- `tools/agent_tools/skill_tool_commands.py`
  - `.agents/skills/*/SKILL.md` の `## Tool Commands` 入口を同期・検査し、`show --skill <skill>` で runtime skill と human skill canon から command packet を表示します。
- `tools/agent_tools/tool_catalog.py`
  - `tools/catalog.yaml` の構造、説明、default wiring、docs/tests、legacy provenance を検査します。
- `tools/agent_tools/tool_drift.py`
  - GitHub PR flow、AgentCanon PR check、dependency review、skill/workflow prompt eval、runtime alignment、skill mirror parity、convention compliance、tool catalog の dependency-header trace を検査します。
- `tools/agent_tools/check_hardcoded_numbers.py`
  - Python / C++ source の裸の数値リテラルを検出します。既定では汎用的な係数だけを許容し、Python の module-level uppercase constant、C++ の `constexpr` constant、行単位の `hardcoded-number-ok` 根拠コメントを許容します。
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
- `tools/bin/agent-canon python-algorithm-contract-check`
  - Python AST を JSON として抽出し、Rust 側で `algorithm_module_protocol` module の standard public surface、callable `Algorithm`、nested ownership、concrete `Info` schema を検査します。親 algorithm 側の nested field は特定 module 名に固定せず、import された amp module alias と `*.Algorithm` / `*.SolveConfig` / `*.Info` / `*.initialize` の AST usage から自動推定します。
- `tools/experiments/update_latest_result.py`
  - experiment result root の `LATEST.json` と `LATEST.md` を更新し、最新 run、summary、manifest、visual report の入口を固定します。
- `tools/experiments/publish_result_branch.py`
  - `main` などの source checkout で作成した `experiments/<topic>/result/<run_name>/` と `experiments/report/<run_name>.md` を、checkout を切り替えず `experiment-results/<topic>` などの result branch へ保存します。
  - 標準形は `python3 tools/experiments/publish_result_branch.py --result-dir experiments/<topic>/result/<run_name> --branch experiment-results/<topic>` です。remote へ保存する場合だけ `--push` を足します。
- `tools/push_origin.sh`
  - 旧 shell push 実装の退役入口です。GitHub publish / PR 作業は `tools/agent_tools/github_publish.py` を使います。

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
