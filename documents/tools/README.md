<!--
@dependency-start
responsibility Documents ツール入口 for this repository.
upstream design ../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ../runtime-profiles-and-check-matrix.md runtime profile and validation routing policy
upstream design ../../tools/catalog.yaml structured AgentCanon tool catalog
downstream implementation ../../tools/agent_tools/tool_catalog.py validates catalog/docs consistency
downstream implementation ../../tools/agent_tools/tool_drift.py validates tool/convention trace contracts
downstream implementation ../../tools/agent_tools/responsibility_scope.py validates responsibility scope ownership
downstream implementation ../../tools/agent_tools/issue_sync.py validates local issue sync state
downstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates eval result accumulation
downstream implementation ../../tools/agent_tools/runtime_log_archive_git.py manages mounted hook/eval/report log archive branches
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
downstream implementation ../../tools/agent_tools/formal_proof.py builds formal-proof scaffold plans
downstream design ../prose-reasoning-graph/dsl-spec.md defines prose graph DSL vocabulary
@dependency-end
-->

# ツール入口

このディレクトリは、repo で使う補助ツールの入口です。
詳細な機械可読台帳は `tools/catalog.yaml` を正本にし、この文書では
root 側からよく使う実行導線だけを整理します。

agent/worktree helper、review / validation runner、docs-check helper、container runtime helper、experiment scaffold / registry helper のうち shared canon に属するものは `vendor/agent-canon/` が正本です。
ownership と validation は [SHARED_RUNTIME_SURFACES.md](../SHARED_RUNTIME_SURFACES.md) を参照し、この文書では root 側の実行入口だけを案内します。
実行する tool は [Runtime Profiles And Check Matrix](../runtime-profiles-and-check-matrix.md) の active profile と changed path で選びます。

## AgentCanon Tool Catalog

- `tools/catalog.yaml`
  - canonical、compatibility wrapper、optional、maintainer-only、retired tool の構造化カタログです。
- `tools/agent_tools/tool_catalog.py`
  - catalog の schema、path、説明、docs/tests、default wiring、retired legacy 混入を検査し、`--format markdown` で対応表を出します。
- `tools/agent_tools/tool_drift.py`
  - dependency manifest を使い、tool / workflow / PR checklist / convention doc の trace 漏れを検出します。
- `tools/agent_tools/responsibility_scope.py`
  - top-level `responsibility-scope.toml` を検査し、runtime、issues、eval、tooling、GitHub、vendor の責務範囲と protecting tool を固定します。
- `tools/agent_tools/import_responsibility.py`
  - Python import の未使用 alias、wildcard import、local import の responsibility-scope 越境を検査します。
  - 越境許可は repo top-level `responsibility-scope.toml` の `[[import_rule]]` に書き、reviewer の推測にしません。
- `tools/agent_tools/issue_sync.py`
  - `issues/open|closed/` の required field、status、filename、closed issue の `resolved_by` を検査し、GitHub Issue mirror の作成 plan と read-only drift check を出します。通常 CI では offline validation、PR の issue mirror workflow では GitHub read-only check を使います。
- `tools/agent_tools/eval_accumulation_check.py`
  - mounted runtime log archive の hook JSONL と skill eval report を検査し、AgentCanon-owned evidence が上書きされず読める状態か確認します。source tree の `agents/evals/results/` は正規の読み書き場所ではありません。
- `tools/agent_tools/runtime_log_archive_git.py`
  - mounted log archive の ensure / status / import / agent report archive / push 操作を担当します。置き場確認は `status` の `RUNTIME_LOG_ARCHIVE_REPORTS_*` 行を見ます。通常は `sync` が `reports/agents/` を `.agent-canon/log-archive/agent-reports/<repo-key>/` on `logs/<repo-key>` へ同期します。`archive-agent-report --report-dir reports/agents/<run-id>` は特定 run bundle を `.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/<snapshot-id>/` に immutable snapshot し、`index.jsonl` を機械的に追記します。hook/eval result の構造検査は `eval_accumulation_check.py` を使い、旧 log-management checker の互換 wrapper は置きません。
- `tools/agent_tools/run_accumulated_agent_evals.py`
  - registered eval family の producer をまとめて `--accumulate` で実行し、stdout / stderr は `reports/agent-eval-runs/<run-id>/` に退避します。PR / CI gate はこの tool を先に走らせてから `eval_accumulation_check.py` で archive 構造を検査します。agent が eval report を手書きする経路は使いません。
- `tools/agent_tools/github_publish.py`
  - `gh` で GitHub repo を確認し、`origin` が同じ `owner/name` を指す場合だけ branch push、PR create/update、PR checks を実行します。`--user-task` は必須で、literal URL push、remote 推測、`.git/config` alternate route は使いません。GitHub publish / PR evidence はこの tool と PR gate の責務であり、非重大 hook finding では止めません。
- `tools/agent_tools/repo_structure_contract.py`
  - `documents/repo-structure-contract.toml` を正本にして、top-level から `tree -a -J` で取得した directory / file 構成を AgentCanon-supported profile と比較します。保存済み `tree -J` JSON も `--tree-json` で読めます。期待 path、ignore、profile detection、unexpected top-level severity は tool code ではなく TOML contract から解決します。
- `tools/agent_tools/render_dependency_manifest_graph.py`
  - `check_dependency_graph.sh --graph-tsv` の edge artifact から Markdown summary と Graphviz DOT を生成します。大規模 review では raw edge listing の前にこの report を読みます。
- `tools/agent_tools/classify_path_risk.py`
  - changed path list から docs / Python / Docker / GitHub / shared-canon / full-confidence 候補を分類し、targeted validation command を出します。`.github/workflows/path-risk-check-matrix-smoke.yml` もこの classifier を使います。
- `tools/agent_tools/formal_proof.py`
  - 自然言語の数学的 claim、または `--python-symbol path.py::qualname` の Python AST source から `proof_status=scaffold_only_unverified` の plan、既存 proof search query、literature query、proof assistant stub、checker command を作ります。AST route は対象 module を import / execute しません。`--out-dir` には Python library 配布に残せる `*_proof_trace.py` module も生成します。外部検索は `$literature-survey` へ渡し、証明済み判定は Lean / Isabelle / Coq / SMT の実行 log だけに委ねます。
- `agent-canon test-design check`
  - Rust CLI の test design 診断入口です。既存 test の oracle 不在、private detail 結合、mock call 過指定、全文 output / error prose 固定、sleep、unseeded randomness、property / metamorphic 候補を compact finding として出します。`fix-now` は修正対象、`review` と `design-hint` は `$test-design` の計画入力です。説明文書は [test_design.md](test_design.md) です。
- `agent-canon local-llm classify-responsibility`
  - Rust CLI の正本入口です。llama.cpp と小型 GGUF model を使い、単一 file の責務分析だけを advisory に行います。repo-wide 解析、依存 closure、CI pass/fail には使いません。
- `agent-canon local-llm route-implementation-surface`
  - 実装前の置き場所 router です。`--request-file`、`--request-stdin`、または
    `--request` で依頼文を渡し、repo / directory / tool / skill / workflow /
    root instruction / document / report surface の primary owner、candidate
    paths、forbidden paths、required pre-edit checks を compact text または
    JSON で返します。
  - llama.cpp が使えない場合は環境構築ミスとして
    `IMPLEMENTATION_SURFACE_ROUTER=error` と修復 action を返し、implementation
    path の選択へ進ませません。
- `agent-canon local-llm extract-prose-ir`
  - 複数 document と複数 term を受け取り、LocalLLM 向け part に分割して prose intermediate representation JSON を作ります。
  - 返す単位は単語 list ではなく、document responsibility、section role、term context、corpus hints、`dsl_seed`、`parts[]` です。
  - `--document-batch-size` と `--term-batch-size` で分割幅を指定し、merge 済み JSON は `--json-out` に保存します。
- `agent-canon local-llm eval`
  - `evidence/agent-evals/local_llm_responsibility_eval.toml` を読み、Local LLM 単一 file 責務分析の prompt と任意の model-backed output を eval します。既定は prompt-only です。
- `tools/agent_tools/evaluate_report_quality.py`
  - `evidence/agent-evals/report_quality_eval.toml` を読み、report-writing skill と report reviewer route が Report Quality Checklist を落としていないかを eval します。必要なときだけ `--accumulate` で append-only report を保存します。
- `tools/agent_tools/evaluate_codex_agent_roles.py`
  - `.codex/agents/*.toml` の期待動作、禁止動作、model / reasoning bucket、cheap-first routing、optional runtime metric JSONL を role 単位で eval します。
- `tools/agent_tools/prose_reasoning_graph.py`
  - Markdown/plain text を SQLite-backed prose graph に取り込み、projection、
    diagnostics、natural-language explanation、split/merge/bridge/reorder
    operation、既存 writing/review skill への handoff packet を出します。
  - list / table / figure / equation の候補は keyword や閾値ではなく、`presentation`
    layer の feature subgraph として materialize してから
    `presentation_format_candidate` diagnostic に接続します。
  - DB 作成の既定は
    `${AGENT_CANON_PROSE_GRAPH_HOME:-$HOME/.cache/agent-canon/prose-reasoning-graph}`。
    run-local DB などが必要な場合だけ `--db` で明示します。
  - DSL vocabulary and validation are defined in
    [Prose Reasoning Graph DSL Specification](../prose-reasoning-graph/dsl-spec.md).
- `agent-canon local-llm search`
  - `--purpose` を受け取り、text、LLM semantic card、TF-IDF vector、tool catalog、dependency header、Python code fact を協調させて候補 path と evidence を返します。
- `agent-canon local-llm build-index`
  - LLM search provider 用の `.agent-canon/search-index/` を生成します。生成 index は repo-local ignored state で commit しません。
- `agent-canon semantic-index`
  - text-like file を安定 node に分け、provider-scoped dense vector を SQLite に保存します。
  - `build`、`embed-provider`、`search`、`context-pack`、`responsibility-tree`、`similar`、`merge-candidates`、`natural-relations`、`discourse-relations`、`thin-docs`、`compare-providers`、`eval`、`eval-output` を持つ候補生成 tool です。
  - `embed-provider` は既存 node に LLM embedding provider の vector を追加し、`compare-providers` は deterministic baseline と LLM provider の候補 ranking delta を診断します。LLM label や ownership authority は生成しません。
  - `search` は `--query`、`--query-file`、`--query-stdin` を受けます。長い user request は file / stdin で渡し、agent が JSON 全体や長い query echo を読む必要がないように `--top-k` と `--format text` または `--format jsonl` を使います。
  - `context-pack` は agent handoff 用に、上位候補を path、line range、score、responsibility bucket、短い excerpt の bounded evidence cell へ圧縮します。
  - `responsibility-tree` は SQLite 内の node vector を directory vector に集約し、現在の indexable repo tree と DB file tree の directory 差分を JSON report と exit code で検査します。
  - `similar` は横断 alignment evidence を許可し、`merge-candidates` は full repo 入力のまま同じ responsibility scope / surface kind / document topic / node kind 内だけを候補化します。runtime mirror と eval/report log は統合候補にしません。
  - `natural-relations` は pair の両方向で "A is a kind of B" の自然さを score 化し、`equivalent`、`unrelated`、片方向包含を SQLite に保存します。
  - `discourse-relations` は profile 別に近傍 paragraph/block のつながりを score 化し、`therefore` / `because` のような surface phrase の違いと `reason_to_result` のような relation primitive を分けて SQLite に保存します。構造計画の evidence であり、文章・policy・統合判断の authority ではありません。
  - `thin-docs` は低内容量、高い単一 target 類似度、参照密度、wrapper 語彙から薄い文書候補を出し、root entrypoint は `keep_entrypoint` として削除候補から分けます。
  - `eval-output` は review JSONL artifact 自体を検査し、result count、responsibility metadata、thin-doc action、long-query echo の欠落を検出します。
  - `tools/agent_tools/semantic_provider_html_report.py` は `compare-providers` JSON を self-contained HTML に描画します。先頭図は `Provider Delta To Shared Candidate Logic` で、provider 差分は診断 evidence、責務 bucket / candidate logic が authority であることを明示します。
  - 生成 DB の既定は `~/.cache/agent-canon/semantic-index/<repo-key>/` です。repo-local cache が必要な場合だけ `--db` で明示し、commit しません。削除・統合の authority にはしません。
- `agent-canon structured-analysis build --root . --profile manual`
  - git-visible file tree を `artifact` layer、directory responsibility projection を
    README と child artifact responsibility からの derived graph、document-canon
    cleanup finding を `document-canon` layer として user-home cache の SQLite DB に
    materialize し、解析 warning を別の `diagnostics.sqlite` に保存します。DevContainer
    post-create でも warning-only で走り、repo tree は書き換えません。
  - `directory_responsibility_low_child_coverage` は README responsibility が child artifact
    responsibilities を十分に代表していない候補です。自動 rewrite ではなく
    `directory_responsibility_verification` route に渡します。
- `agent-canon structured-analysis document-inventory --root .`
  - document-canon cleanup の canonical Rust entrypoint です。runtime mirror、generated evidence、closed issue record、missing dependency manifest、重複見出し、stale document name を棚卸しします。
  - `agent-canon structured-analysis import-document-inventory --db <graph.sqlite> --json <inventory.json>` で同じ結果を SQLite の `document-canon` layer に取り込み、レポ root から一文までの graph trace と接続します。
- `tools/agent_tools/route.py --area search`
  - 検索 tool 名を知らない agent / reviewer 向けの短い入口です。`search.py` と `search_index.py` の command を返します。
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
  - full confidence が必要な時に主要なチェックをまとめて実行します。small docs / focused code では check matrix に従って個別 check を選びます。
- `tools/ci/pre_review.sh`
  - review 前の基礎 gate をまとめて実行します。
- `tools/bin/agent-canon docs check`
  - Rust の統合 docs checker です。Markdown lint、link、math、Mermaid、bootstrap docs、runtime profile inventory drift をまとめて実行します。
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
  - `jupyter/` や `notebooks/` の `.ipynb` を、細かい test ではなく、説明付きで部分実行しやすい実用 demo として読めるか検査します。
  - Codex hook では changed notebook だけを見て、`assert`、`pytest`、`test_` 関数、保存済み error output、可視化 code 不在を block します。
- `tools/experiments/create_experiment_topic.py`
  - shared topic scaffold から experiment topic を作ります。
- `tools/experiments/sync_experiment_registry_context.py`
  - registry の branch / worktree metadata を同期します。
- `tools/experiments/run_managed_experiment.py`
  - shared managed-runner として server 上の実験 run artifact を初期化します。
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
  - legacy `WORKTREE_SCOPE.md` / action log の cleanup 診断入口です。新規 worktree kickoff には使いません。
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
  - CUDA build は `AGENT_CANON_LLAMA_CPP_CUDA=auto|1|0` で制御します。`auto` は `nvcc`、GPU device、linkable `libcuda` が揃う場合だけ `-DGGML_CUDA=ON` にし、それ以外は CPU build に戻します。
  - `AGENT_CANON_LLAMA_CPP_CUDA_DRIVER_LIB_DIR` は WSL / devcontainer の `libcuda.so` 探索先を明示します。`AGENT_CANON_LLAMA_CPP_CMAKE_ARGS` は追加 CMake flags、`AGENT_CANON_LLAMA_CPP_BUILD_JOBS` は build 並列数です。
  - CUDA / CMake flag の組み合わせは build cache key として記録されます。source が新しくなくても設定が変わった場合は `already_current` にせず再ビルドします。
  - 既定 model selector は `ggml-org/SmolLM3-3B-GGUF:Q4_K_M` です。model weights は lazy fetch で、repo にコミットしません。
- `tools/agent_tools/route.py`
  - 長い候補 tool / skill 名を短い route area へ解決します。
  - 例: `profile_surface_resolver.py` は `route.py --area surface`、`$runtime-capability-routing` は `route.py --area runtime` として扱います。
  - 新しい public tool / skill を足す前に `python3 tools/agent_tools/route.py --name <candidate>` で既存 route に畳めるか確認します。
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
  - user-home cache に `prose_graph.sqlite`、`diagnostics.sqlite`、`document_inventory.json`、`exports/` を作り、source file から中間表現 DB と warning DB を再生成します。`--out-dir` を指定した場合だけその artifact root に出力します。
- `agent-canon structured-analysis document-inventory --root .`
  - Markdown / text 文書を棚卸しし、runtime mirror、generated evidence、closed issue record、missing dependency manifest、重複見出しなどの非正本候補を正本候補と一緒に出します。旧 `tools/agent_tools/noncanonical_document_inventory.py` は caller warning 付きの legacy migration shim です。
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
  - goal / maintainer / audit profile の tool であり、通常の small change では required gate にしません。
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
  - hook JSONL、eval report、Codex runtime summary、`reports/agents/` の agent run report は `git@github.com:iwashita-nozomu/agent-canon-log.git` を `.agent-canon/log-archive/` に mount して蓄積します。branch / push 手順は `documents/runtime-log-archive.md` を正本にし、通常操作は `tools/agent_tools/runtime_log_archive_git.py sync` を使います。個別修復時だけ `ensure|status|import-legacy|import-eval-results|archive-agent-report|archive-agent-reports|push` を使います。
  - `generate_agent_improvement_guide.py` は `memory/`、mounted `.agent-canon/log-archive/eval-results/skill-workflow-prompt/`、mounted hook archive、`issues/open|closed/` を読んで PR / branch push 用の改善指南書を生成します。生成は read-only で、skill usage、hook event、tool name、checker target、protocol feedback token の不足をまとめ、実修正は local Codex に渡します。
  - `generate_agent_runtime_dashboard.py` は同じ evidence tree を人間が見るための dashboard にします。正本ログの場所、hook namespace、entry 数、skill usage、prompt route 候補、human feedback、eval report family、issue 数を Markdown に出し、GitHub Actions では AgentCanon repo の Step Summary と artifact にだけ出します。agent がログ分析するときは `--compact-out` で token-light summary、generated drilldown、prompt/token rolling trend を生成し、通常分析では raw JSONL を開かずそれを読みます。token 利用は lifetime total だけではなく recent moving average と coverage status で判断します。足りない詳細は raw log 検索ではなく dashboard tool の追加 summary として生成し、raw JSONL は tool 実装、schema debugging、corruption audit の explicit rationale がある場合だけ使います。
  - `run_accumulated_agent_evals.py` は同じ evidence tree の required eval family を機械的に追記する入口です。role、skill/workflow prompt、local LLM、workflow-selection、report-quality の各 eval を `--accumulate` で実行し、標準出力は log file に捕捉します。
  - `eval_accumulation_check.py` は同じ evidence tree の構造 gate です。hook JSONL、skill eval report、local LLM eval report、unique id、ignore rule を検査し、改善指南書が読めない evidence を早期に止めます。agent-facing run では `--compact-out <path>.json` を使い、finding 全件は JSON summary 側へ逃がします。
  - `evaluate_workflow_selection.py` は `evidence/agent-evals/workflow_selection_eval.toml` の固定 prompt case で workflow routing を検査します。`--accumulate` を付けた run は `.agent-canon/log-archive/eval-results/workflow-selection/` に詳細結果を蓄積します。
  - `evaluate_codex_agent_roles.py` は subagent role TOML ごとに `explorer` read-only、reviewer findings-first、`spark_worker` narrow implementation、禁止事項、model cost bucket、task routing、token / latency / retry / parent intervention / format violation / output-used metrics の受け口を検査します。agent-facing run では `--compact-out <path>.json` を使い、model matrix と finding detail は artifact で読む運用にします。
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
  - GitHub PR flow、AgentCanon PR check、dependency review、skill/workflow prompt eval、runtime alignment、skill mirror parity、convention compliance、tool catalog の dependency-header trace を検査します。
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
- `tools/bin/agent-canon python-algorithm-contract-check`
  - Python AST を JSON として抽出し、Rust 側で `algorithm_module_protocol` module の standard public surface、callable `Algorithm`、nested ownership、concrete `Info` schema を検査します。親 algorithm 側の nested field は特定 module 名に固定せず、import された amp module alias と `*.Algorithm` / `*.SolveConfig` / `*.Info` / `*.initialize` の AST usage から自動推定します。
- `tools/experiments/update_latest_result.py`
  - experiment result root の `LATEST.json` と `LATEST.md` を更新し、最新 run、summary、manifest、visual report の入口を固定します。
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

- `setup_worktree.sh` / `tools/docs/create_worktree.sh` は deprecated wrapper です。呼ばれた場合は caller chain と移行先を stderr に出し、新規 worktree を作らず停止します。
- 既定運用は current checkout の run bundle と `team_manifest.yaml` write scope です。

## 参照先

- Template-derived repositories may add a root-local `scripts/README.md` for
  repo bootstrap scripts that are not AgentCanon-owned tools.
- [SHARED_RUNTIME_SURFACES.md](../SHARED_RUNTIME_SURFACES.md)
