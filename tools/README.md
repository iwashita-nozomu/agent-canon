# tools
<!--
@dependency-start
responsibility Documents tools for this repository.
upstream design ../AGENTS.md shared canon runtime contract
downstream design catalog.yaml structured AgentCanon tool catalog
downstream design ../documents/tools/tool-docs.toml same-named tool documentation map
downstream implementation agent_tools/tool_catalog.py validates catalog/docs consistency
downstream implementation agent_tools/tool_drift.py validates tool/convention trace contracts
downstream implementation agent_tools/responsibility_scope.py validates responsibility scopes and protecting tools
downstream implementation agent_tools/issue_sync.py validates local issue sync state
downstream implementation agent_tools/eval_accumulation_check.py validates eval result accumulation
downstream implementation agent_tools/file_responsibility_llm.py runs single-file local LLM responsibility review
@dependency-end
-->


Root `tools/` is a symlink view into `vendor/agent-canon/tools/`. The root path
is the stable command surface for template and derived repositories; the
vendored AgentCanon path is the canonical implementation source. These two
paths must not become separate ownership surfaces.

Shared agent helper, CI/check, container runner, experiment helper, Markdown
maintenance, and validation tools live in `vendor/agent-canon/tools/` and are
called through `tools/...` from parent repositories. Project-local automation
that is not reusable AgentCanon capability belongs in project-owned paths such
as `scripts/`, package-local modules, or repo-specific CI files. Do not add
project-specific files under root `tools/`; it is an AgentCanon-owned runtime
view.

When a change is generic, edit `vendor/agent-canon/tools/...`, open or merge an
AgentCanon change, update the parent repo submodule pin, and repair the root
view with `bash tools/sync_agent_canon.sh link-root`. When a command or test log
mentions `tools/...`, read it as the root execution path for AgentCanon-owned
tooling unless the path is explicitly project-owned elsewhere.

## Tool Catalog

`tools/catalog.yaml` is the structured AgentCanon tool catalog. It separates
canonical shared tools and compatibility wrappers without turning README prose
into a second registry. Use it to check whether a tool is callable by default,
wired into CI / PR validation, covered by tests, or documented by the
same-named tool-doc map.

`documents/tools/tool-docs.toml` maps selected tool entrypoints to one
reader-facing Markdown file each. The tool and document basenames must match
so the catalog can be enumerated mechanically.

Validation entrypoints:

```bash
python3 tools/agent_tools/tool_catalog.py
python3 tools/agent_tools/tool_drift.py
python3 tools/agent_tools/responsibility_scope.py
python3 tools/agent_tools/issue_sync.py
python3 tools/agent_tools/eval_accumulation_check.py
python3 tools/agent_tools/local_llm_eval.py
```

`tool_catalog.py` validates catalog shape, path existence, per-entry summaries,
docs/tests, default wiring, retired legacy paths, and tool-doc one-to-one
mapping. Use
`--format markdown` when you need the catalog crosswalk as a reader-facing
tool table.
`tool_drift.py` uses dependency manifests plus the catalog to
detect stale tool/convention links, missing required PR-flow checks, and
retired legacy tool reintroduction.
`responsibility_scope.py` validates top-level `responsibility-scope.toml`
so each durable surface has an owner class, path coverage, protecting tools,
and linked operational issues.
`issue_sync.py` validates `issues/open|closed/` offline and prints a deterministic
GitHub Issue creation plan for local issues that do not yet have a
`github_issue:` mirror field.
`eval_accumulation_check.py` validates that hook JSONL, skill prompt eval, and local LLM eval
reports are accumulating under `agents/evals/results/` as readable,
non-ignored, append-only AgentCanon evidence.
`local_llm_eval.py` validates the configured single-file local LLM
responsibility prompt boundary and can optionally accumulate prompt-only or
model-backed reports under `agents/evals/results/local-llm-responsibility/`.

## 含めるもの
- `bin/`
  - `agent-canon` は AgentCanon Rust CLI の stable wrapper です。template /
    derived repo では root `tools/` symlink から呼び、実体 source は
    `vendor/agent-canon/rust/agent-canon/` を使います。devcontainer では
    post-create が release binary を
    `${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}/agent-canon/bin/agent-canon` へ
    install し、`/usr/local/bin/agent-canon` から実行できるようにします。
    wrapper は installed binary が checked-out Rust source より古い場合、
    stale binary ではなく source から `cargo run` します。
    `rust-migration-audit` は DevContainer / Dockerfile 境界を確認し、
    `rust-migration-plan` は固定 policy と hook / skill feedback logs から
    次に Rust 化する tool 候補を出します。派生 repo では
    `agent-canon rust-migration-plan --root vendor/agent-canon` を使います。
- `agent_tools/`
  - task/doc start、waterfall gate、close gate、work log、runtime smoke
  - `task_start.py` と `bootstrap_agent_run.py` は task 入口で `make agent-canon-ensure-latest` preflight を自動実行します。submodule repo では親 repo の無関係な dirty state だけを理由に skip せず、AgentCanon update surface が repairable なら最新化を進めます。unsafe な update surface は machine-readable に route を出します。
  - `agent_canon_update_todos.py` は AgentCanon pin 更新後に親 repo の agent が先に消化する TODO を `documents/agent-canon-update-tasks.toml` から読み、親 repo ローカルの `.agent-canon/update-state.toml` で適用済み boundary を管理します。pending は停止理由ではなく、task-start の `AGENT_CANON_UPDATE_TODO_NEXT=apply_agent_canon_update_todos` として最初の作業に route します。
  - `vector_search.py` は tools、skills、workflow、documents、MCP surface を標準ライブラリ TF-IDF vector で横断検索します。正確な symbol / path は `rg` を優先し、広い概念や再利用候補探索で併用します。
  - `route.py` は長い候補 tool / skill 名を短い routing area へ解決し、`ROUTE`、`AREA`、`NEXT_ACTION`、`COMMANDS`、`EVIDENCE` を出します。候補名をそのまま新規 tool 化せず、まず `python3 tools/agent_tools/route.py --name <candidate>` で既存 route に畳みます。
  - `tool_catalog.py` は `tools/catalog.yaml` と `documents/tools/tool-docs.toml` を検査し、canonical tool、compatibility wrapper、retired legacy path、tool-doc 対応のずれを止めます。
  - `tool_drift.py` は dependency manifest を trace map として使い、tool / workflow / PR checklist / convention docs の抜け漏れを検出します。
  - `responsibility_scope.py` は top-level `responsibility-scope.toml` を検査し、runtime、issues、eval、tooling、GitHub surface、vendor skill の owner class と protecting tool を固定します。
  - `issue_sync.py` は `issues/open|closed/` の required field、status、filename、closed issue の `resolved_by`、任意の `github_issue:` mirror field を検査し、GitHub Issue 作成 plan を出します。
  - `eval_accumulation_check.py` は `agents/evals/results/` の hook JSONL、skill eval report、local LLM eval report を検査し、duplicate run id、malformed JSONL、ignored evidence path、missing required field を止めます。
  - `file_responsibility_llm.py` は llama.cpp と小型 GGUF model を使う advisory checker です。現状の scope は単一 file の責務分析だけで、repo-wide ownership や CI 合否には使いません。
  - `local_llm_eval.py` は `agents/evals/local_llm_responsibility_eval.toml` を読み、Local LLM の単一 file 責務分析プロンプトと任意の model-backed output を評価します。既定は prompt-only で、`--accumulate` のときだけ append-only result を書きます。
  - `file_surface_inventory.py` は root view、submodule pin、AgentCanon source を JSON / Markdown で分類します。
  - `noncanonical_document_inventory.py` は Markdown / text 文書を棚卸しし、runtime mirror、generated evidence、closed issue record、missing dependency manifest、重複見出しなどの非正本候補と正本候補を出します。
  - `helper_function_inventory.py` は Python helper 関数 / クラスを AST/call graph/side effect facts と domain 別の機能ベース rule から列挙し、`auto_helper` と `needs_user_judgment` を分けて JSON / Markdown / text で出します。
  - `log_surface_inventory.py` は `.codex/hooks/`、`.agents/skills/`、`.claude/skills/`、`agents/skills/`、`tools/` から hook / skill / tool が出力する machine-readable field を静的に棚卸しし、`documents/log-surface-inventory.json` との差分を検査します。
  - `tool_rejection_preflight.py` は planned edit path から OOP readability、helper inventory、dependency review、GitHub workflow、hook runtime alignment、skill mirror sync、tool catalog、agent protocol convention、log-surface inventory などの予測 reject gate を出し、parent 直編集または write-capable subagent handoff に渡す `TOOL_REJECTION_PREDICTED_GATE` 行を生成します。
  - `review_backlog_scan.sh` は file inventory、stale wording search、dependency review、code dependency scan、OOP/readability、`Any`、hardcoded-number、log-helper、convention scans を run bundle へ集約します。
  - `vendor_skill_adapters.py` は `vendor/skills/manifest.toml` を検査し、enabled third-party skill を `.agents/skills/` の runtime adapter symlink として露出します。
- `ci/`
  - repo check、container runner、server readiness、fresh clone acceptance
  - `python_env_policy.py` は host/container を判定し、container でだけ canonical `.venv` を許可します。
  - `check_github_workflows.py` は GitHub Actions checkout / permissions / concurrency、PR template evidence、Copilot discovery surface を検査します。
  - `container_config.py` は standalone AgentCanon では repo-local Docker absence を許容し、template / derived repo では repo-local `docker/Dockerfile` / `docker/packs/*.toml` と AgentCanon-owned `.devcontainer/` の静的整合を検査します。
- `docs/`
  - Markdown lint、math check、link audit、format、mirror sync、design document consolidation helpers
- `data/`
  - JSONL-to-Markdown conversion and compact result-data transforms
- `hlo/`
  - HLO JSONL summary helpers
- `audit/`
  - portable audit-log schema and JSONL writer
- `experiments/`
  - topic scaffold、registry sync、managed run
- `oop/`
  - `python/` と `cpp/` に分けた OOP readability / inventory entrypoint。共有実装は `oop/shared/` に置き、言語別の default path を機械的に列挙できるようにします。
- `shared/`
  - shared helper
- `validation/`
  - generic validation helper
  - `notebook_quality.py` は notebook を細かい test ではなく、説明付きで部分実行しやすい実用 demo として保つための checker です。
- `static_analysis/`
  - language-organized index for Python, C/C++, and common static-analysis entrypoints. OOP readability implementations are exposed through `oop/python/` and `oop/cpp/`.
- top-level helper
  - `sync_agent_canon.sh`
    - `plan` は derived repo から見た update route を read-only で出します。
    - `ensure-latest` は task 開始時に upstream `agent-canon` と local `vendor/agent-canon` を揃えます。
    - `agent-canon` remote が未設定なら GitHub canonical remote `https://github.com/iwashita-nozomu/agent-canon.git` を自動追加します。local bare mirror を使う repo だけ `AGENT_CANON_REMOTE_URL=/mnt/git/agent-canon.git` を明示します。
    - submodule repo では gitlink commit を確認し、必要なら submodule pointer を fast-forward 更新します。
  - legacy subtree repo では subtree metadata / snapshot import fallback を使います。
  - `update_agent_canon.sh`
    - `plan` は derived repo から `agent-canon` だけ更新するときの route を出します。
    - `latest` は通常の最新化を tool-first に実行し、safe な場合は `ensure-latest`、root view check、AgentCanon update TODO acknowledge まで進めます。local shared-canon branch、dirty submodule、diverged history、merge conflict は消さず、`AGENT_CANON_LATEST_WORKFLOW` と `NEXT_ACTION=run_agentcanon_conflict_workflow` を出して agent workflow に渡します。
    - `apply` は `ensure-latest` を呼び、GitHub `main` の submodule pin を parent repo に持ち帰ります。
    - `merge-main-into-current` は `vendor/agent-canon/` の current branch に GitHub `main` を merge し、AgentCanon PR branch を push できる状態へ近づけます。
    - compatibility commands for local remotes, source refresh, and direct main alignment are intentionally not user-facing.

## AgentCanon Update Path

通常の派生 repo では `update_agent_canon.sh latest` を入口にします。

1. `make agent-canon-update-plan` で route を read-only 確認します。
1. `make agent-canon-latest` で通常の AgentCanon `main` 更新、root view check、親 repo update TODO acknowledge を tool に任せます。
1. submodule 内に local branch commit、dirty shared-canon 差分、diverged history、merge conflict がある場合、`latest` は停止ではなく `AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md` と `AGENT_CANON_LATEST_CONFLICT_COMMAND=bash tools/update_agent_canon.sh merge-main-into-current` を出します。その場合は agent が conflict workflow に入り、必要なら `make agent-canon-merge-main` で GitHub `main` を current branch に取り込み、AgentCanon branch と PR に出します。
1. AgentCanon PR が merge された後に `make agent-canon-ensure-latest` で template / derived repo へ持ち帰ります。
1. `python3 tools/agent_tools/agent_canon_update_todos.py plan --write` で、その pin 更新に伴う親 repo TODO を生成します。pending があれば親 repo の agent が先に適用し、完了なら `complete`、明示的な repo 判断が必要なら `defer --reason ... --owner ...` を記録します。
1. すべての pending TODO が `completed` または `deferred` になったら `python3 tools/agent_tools/agent_canon_update_todos.py acknowledge` で `.agent-canon/update-state.toml` の `tasks_applied_through` を現在 pin へ進めます。
1. `make agent-canon-update` で GitHub `main` の submodule pin を適用します。
1. root view が drift した場合だけ `make agent-canon-links` を使います。
1. 派生 repo 側の shared canon 差分を upstream に戻す場合は、`vendor/agent-canon/` branch を GitHub に push して AgentCanon PR を使います。

`sync_agent_canon.sh` は低レベル実装です。
日常の update 導線では `pull` や `push` を直接選ばず、Make target または `update_agent_canon.sh plan/apply` から入ります。
submodule 化済み repo では `plan` が `already_current_submodule` / `submodule_update` を返します。
  - `run_comprehensive_review.sh`
  - `run_pytest_with_logs.sh`
  - `docker_dependency_validator.sh`
  - `ci/container_config.py`
  - `check_doc_test_triplet.py`
  - `agent_tools/waterfall_gate_check.py`
  - `agent_tools/evaluate_agent_run.py`
  - `agent_tools/compare_agent_run_paths.py`
  - `agent_tools/goal_loop.py`
  - `agent_tools/evaluate_skill_workflow_prompts.py`
  - `agent_tools/check_convention_compliance.py`
  - `agent_tools/check_static_any.py`
  - `agent_tools/check_log_helper_names.py`
  - `agent_tools/file_surface_inventory.py`
  - `agent_tools/review_backlog_scan.sh`
  - `agent_tools/check_algorithm_module_nested_contract.py`
  - `agent_tools/agent_update_branch.sh`
  - `agent_tools/vector_search.py`
  - `oop/python/readability.py`
  - `oop/python/rule_inventory.py`
  - `oop/cpp/readability.py`
  - `oop/cpp/rule_inventory.py`

## Repo-Local Tool Import Policy

Repo-local tools discovered in derived repositories are not copied over newer
AgentCanon implementations blindly. Use this order:

1. Compare the repo-local file with the current AgentCanon path.
1. Keep the current AgentCanon implementation when it is newer or broader.
1. Promote unique, repo-neutral capability into the nearest canonical family:
   `agent_tools/`, `ci/`, `docs/`, `data/`, `hlo/`, `audit/`,
   `experiments/`, `oop/`, or `validation/`.
1. Keep project-specific or stale tools in the source repository, or delete
   them after review. Do not add new `tools/legacy/` paths to AgentCanon.
1. Record the disposition in `documents/repo-local-tool-imports.md`.
1. Add or update the corresponding `tools/catalog.yaml` entry.

Current promoted helpers:

- `tools/data/jsonl_to_md.py`
- `tools/hlo/summarize_hlo_jsonl.py`
- `tools/experiments/update_latest_result.py`
- `tools/audit/audit_log_schema.py`
- `tools/audit/audit_logger.py`
- `tools/docs/create_design_template.py`
- `tools/docs/find_redundant_designs.py`
- `tools/docs/find_similar_designs.py`
- `tools/docs/organize_designs.py`
- `tools/docs/tfidf_similar_docs.py`

Legacy tool imports are retired in AgentCanon. Historical disposition remains
in `documents/repo-local-tool-imports.md`; live tooling must be represented as
canonical or compatibility entries in `tools/catalog.yaml`, with reader-facing
docs registered in `documents/tools/tool-docs.toml` when the tool needs a
one-to-one explanation page.

## Result Log And Visualization Tools

Result-log retention is governed by
`documents/result-log-retention-and-visualization.md`.

Canonical helper commands:

```bash
python3 tools/data/jsonl_to_md.py <input.jsonl> <output.md>
python3 tools/hlo/summarize_hlo_jsonl.py <hlo.jsonl> > summary.json
dot -V
```

Closeout evidence should point to a raw path, a summary/report path, and a
retention decision. Do not leave only raw logs when the user-facing claim relies
on the result.

## Agent Evaluation Tools

`evaluate_agent_run.py` grades one `reports/agents/<run-id>/` bundle before closeout.
It turns workflow monitoring, review, validation, schedule, dependency, and retrospective evidence into `agent_evaluation.md` with a score and fix-now feedback actions.
This is the repo-local counterpart to trace / eval feedback loops: use it to identify missing tooling, guardrails, documentation, prompt policy, skill/config/workflow updates, or run evidence before the user-facing completion report.

```bash
python3 tools/agent_tools/evaluate_agent_run.py \
  --report-dir reports/agents/<run-id> \
  --write
```

`task_close.py` requires `agent_evaluation.md` to report `evaluation_status: pass`, `feedback_actions_resolved: yes`, and `learning_capture_complete: yes`.
`workflow_monitoring.md` is the in-workflow monitoring artifact consumed by the evaluation. Keep it current during the run, not only at closeout.
`workflow_monitor.py` appends signals, interventions, and improvement decisions to `workflow_monitoring.md`.
After evidence is verified, `workflow_monitor.py --closeout-token-preset` records the standard behavior tokens consumed by `evaluate_agent_run.py`; it is a recording shortcut, not a substitute for validation evidence.
`bootstrap_agent_run.py` and `task_start.py` seed routing and preflight signals automatically, and tools such as `check_mcp_inventory.py` and `run_repo_dependency_review.sh` can append evidence when given `--report-dir` or `AGENT_RUN_REPORT_DIR`.
`compare_agent_run_paths.py` compares two run bundles when agent behavior can take different execution paths. It emits `RUN_PATH_COMPARISON`, `RUN_PATHS_DIFFER`, `SELECTED_INEFFICIENT_ROUTE`, and `STATIC_ANALYSIS_FEEDBACK` tokens for `workflow_monitoring.md` and fails when the selected candidate route is known inefficient.
`compare_codex_token_footprints.py` compares two Codex session JSONL files, emits `TOKEN_FOOTPRINT_*` machine status lines, and can append token-efficiency evidence to `workflow_monitoring.md`.
When a run uses skills, prompt eval evidence is required. Run
`evaluate_skill_workflow_prompts.py --accumulate` and record the emitted
`EVAL_RUN_ID`, `EVAL_STATUS`, and `EVAL_ACCUMULATED_REPORT` as behavior events.
Hook outcomes accumulate in AgentCanon under
`agents/evals/results/hook-runs/` by default. Temporary local hook output belongs
in `reports/hooks/` only when a task explicitly overrides the destination with
`AGENT_CANON_HOOK_RESULTS_DIR`, `AGENT_CANON_OOP_HOOK_LOG_PATH`, or
`AGENT_CANON_SKILL_LOG_PATH`.
`generate_agent_improvement_guide.py` reads memory notes, skill eval reports,
durable hook results, and `issues/open|closed/` to produce the PR /
branch-push improvement guide artifact; it does not mutate skills, workflows,
tools, or memory.
`eval_accumulation_check.py` is the structural gate for that accumulation
surface. It confirms hook JSONL, prompt eval reports, and local LLM eval
reports are readable, uniquely identified, and not hidden by ignore rules
before the improvement guide tries to mine them.

```bash
python3 tools/agent_tools/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --signal "skills=$agent-orchestration,$codex-task-workflow" \
  --intervention "spawned fresh reviewer" \
  --decision workflow_improvement_decision=applied

python3 tools/agent_tools/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --closeout-token-preset

python3 tools/agent_tools/compare_agent_run_paths.py \
  --baseline-run reports/agents/<run-a> \
  --candidate-run reports/agents/<run-b> \
  --report-out reports/agents/<run-b>/path_comparison.md

python3 tools/agent_tools/compare_codex_token_footprints.py \
  --baseline-session ~/.codex/sessions/<baseline>.jsonl \
  --candidate-session ~/.codex/sessions/<candidate>.jsonl \
  --report-out reports/agents/<run-id>/token_footprint.md
```

## Vector Search Tool

Use `rg` first for exact symbol, path, and error-message lookup. Use
`vector_search.py` when the question is semantic: "どの tool が dependency graph
を見ているか", "GitHub remote migration に近い文書はどれか", "safe.directory
周りの helper はどこか" のような再利用候補探索です。

The default index is dependency-free and transient. It scans shared text
surfaces with TF-IDF vectors and does not write embedding artifacts or require
network access.

```bash
python3 tools/agent_tools/vector_search.py --query "dependency header graph"
python3 tools/agent_tools/vector_search.py --surface tools --query "github cli validation"
python3 tools/agent_tools/vector_search.py --query "mcp goal loop" --format json
python3 tools/agent_tools/vector_search.py --surface . --query "solver logging" --context
python3 tools/agent_tools/vector_search.py --surface python --query "initialize info" --context --symbol initialize
```

With `--context`, the tool keeps the TF-IDF search result and also emits
context candidates. `CONTEXT_PATH` rows expand search-hit files through
dependency manifest upstream / downstream edges, while `PYTHON_SYMBOL` and
`PYTHON_EDGE` rows use Python AST definitions and direct calls to show local
function fan-out and reverse caller fan-in. Use `--dependency-depth` to walk
more than one hop and `--context-top` to cap the emitted context pack.

If a repo later adds embedding-backed search, keep it optional: put generated
indices under `reports/` or another ignored artifact path, never commit
embedding vectors, and do not add API keys or model choices to Dockerfile
defaults.

## Log Helper Naming Tool

`check_log_helper_names.py` fails Python functions that look like logging helpers but do not start with `_log`.
Use it when changing logging, report-writing, run-bundle, or JSONL helper code.

```bash
python3 tools/agent_tools/check_log_helper_names.py --changed --exclude vendor --exclude reports
```

## Review Backlog Scan

`review_backlog_scan.sh` is the standard repo-cross inspection entrypoint for
large goal iterations in the standalone AgentCanon repo, this template, and
derived repos that pin AgentCanon as `vendor/agent-canon`. It inspects the
parent/root surface and AgentCanon source as separate scopes, then writes a
machine-readable inventory, a Markdown inventory, tool logs, and a
command-status summary under the run bundle.

```bash
make review-backlog-scan ARGS="--report-dir reports/agents/<run-id>/cross_repo_inspection --submodule-aware"
bash tools/agent_tools/review_backlog_scan.sh \
  --report-dir reports/agents/<run-id>/cross_repo_inspection \
  --submodule-aware
```

Scope flags:

- `--submodule-aware`: scan the template/root surface and `vendor/agent-canon`
  as separate scopes.
- `--root-only`: scan the parent repo surface and exclude submodule internals.
- `--agentcanon-only`: scan AgentCanon source, using `vendor/agent-canon` in a
  derived repo and `.` in the source repo.

Use the `--submodule-aware` form before marking template / derived-repo PRs
ready for review when the change touches shared runtime surfaces, PR templates,
workflow docs, issue storage, tool definitions, dependency manifests, or synced
root views. The run is not a replacement for `make ci`; it is the inspection
bundle that tells reviewers which repo-level surfaces still need edit or
verification.

Minimum evidence to keep with the run bundle:

- `file_surface_inventory.json` and `file_surface_inventory.md` for root,
  submodule pin, symlink/copy views, and AgentCanon source classification.
- `dependency_review_root.txt` and `dependency_review_agentcanon.txt` for
  manifest coverage, format, and dependency graph checks.
- `code_dependencies_root.txt` and `code_dependencies_agentcanon.txt` for
  import/include/source reachability.
- `oop_*_readability_*.md`, `static_any_*.txt`,
  `hardcoded_numbers_*.txt`, and `log_helper_names_*.txt` for mechanical
  implementation review signals.
- `convention_compliance.txt` and `review_backlog_scan_status.tsv` for
  convention and command-status evidence.

After the run, convert the inventory and dependency graph evidence into an
explicit edit / verification list. A grep hit alone is not enough: each listed
surface should say whether it is AgentCanon-owned source, template/root local
state, a synced copy, a symlink view, a GitHub path-constraint copy, or a
project-owned artifact.

## Goal Loop Tool

`goal_loop.py` manages a top-level `goal.md` contract and repeats a command until explicit exit criteria are checked and `goal_status: achieved` is set.
The default `goal.md` and `goal_loop.py init` include mandatory criteria for dependency review, code dependency extraction, OOP/readability analysis, repo-wide static analysis or CI, and objective-specific evidence.
The default Backlog is a minimum first-iteration packet, not a single tiny TODO.
It requires a prompt-to-artifact checklist, reuse / consolidation / deletion survey,
one cohesive implementation slice, task-relevant validation, and immediate continuation
when `NEXT_ACTION=run_next_iteration` remains.
`goal_loop.py init` also writes an `Optional Goal Item Catalog`.
Those catalog entries are non-default: they are visible for humans and agents,
but they do not block closeout or become `GW*` work units until copied into
`Exit Criteria` or `Backlog` for the current objective.
Goal setup also records `pr_mutation_authority`. The default is
`inspect_and_prepare_only`; use `github_copilot_merge_when_green` when the user
wants GitHub-hosted Copilot / PR automation to merge after checks pass. This
mode does not authorize local Codex to bypass checks, dismiss reviews, or hide
merge evidence.

```bash
python3 tools/agent_tools/goal_loop.py status --goal-file goal.md
python3 tools/agent_tools/goal_loop.py plan --goal-file goal.md \
  --report-out reports/agents/<run-id>/goal_work_breakdown.md
python3 tools/agent_tools/goal_loop.py run --goal-file goal.md -- <iteration-command>
python3 tools/agent_tools/goal_loop.py init --goal-file goal.md \
  --objective "<objective>" \
  --pr-mutation-authority github_copilot_merge_when_green
python3 tools/agent_tools/goal_loop.py mark --goal-file goal.md --criterion G5 --done
```

Use the loop for long-running improvement work where closeout must be blocked until the goal contract is mechanically complete.
Before implementation, run `goal_loop.py plan` and copy every open `GW*` row into the run bundle `schedule.md`; this prevents starting from a bare objective with no explicit work units.
Do not shrink the first iteration to one micro-fix when the objective names multiple surfaces.
Select a coherent slice that can move the checklist, survey, implementation, and validation backlog items together.
For efficiency, follow `agents/workflows/goal-plan-implementation-loop.md`: plan only the next implementation-ready slice, implement it, record evidence, refresh `NEXT_ACTION`, and continue immediately when the loop still has open work.
Do not mark criteria done from intent alone; each checked item needs a report, command output, or run bundle artifact.
When the next open item is blocked by an external event, such as an unmerged
upstream PR, set `goal_status: blocked` and record the blocker in the Loop Log.
`goal_loop.py status` then reports `NEXT_ACTION=wait_for_unblock` instead of
asking the agent to rerun the same iteration. Use `goal_status: stopped` only
when the goal is intentionally abandoned without achievement; it reports
`NEXT_ACTION=stop_goal_loop`.

## Skill And Workflow Prompt Evals

`evaluate_skill_workflow_prompts.py` runs frozen checklist evals for skill and workflow prompt surfaces.
Use it whenever a skill is used, and before and after prompt repair when changing
agent-facing skills or workflows.

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest agents/evals/skill_workflow_prompt_eval.toml \
  --accumulate \
  --run-id <run-id> \
  --skill-used agent-orchestration
```

The runner also audits the manifest itself. Do not close prompt-improvement work unless
`EVAL_STATUS=pass`, `EVAL_AUDIT_STATUS=pass`, and `EVAL_GROWTH_CANDIDATES=0` all appear in the
machine-readable output.
Detailed reports accumulate under
`agents/evals/results/skill-workflow-prompt/` with this naming convention:

```text
<eval_run_id>-<status>-<skill-slug>.md
```

`eval_run_id` is assigned as
`skill-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-sha256-prefix>`. The runner does
not overwrite existing reports; if an explicit `--report-out` path already
exists, it writes a sibling file with the unique `eval_run_id` appended.

## Agent Improvement Guide

`generate_agent_improvement_guide.py` reads AgentCanon-owned evidence and
generates a deterministic guide for PR and branch-push review:

```bash
python3 tools/agent_tools/generate_agent_improvement_guide.py \
  --root . \
  --out reports/agent-improvement-guide/agent-improvement-guide.md
```

The guide summarizes `memory/`, `agents/evals/results/skill-workflow-prompt/`,
`agents/evals/results/hook-runs/`, `issues/open/`, and `issues/closed/`.
It is read-only evidence. Local Agent or Copilot PR work applies the actual
skill, workflow, and tool changes.
Keep duplicate eval IDs, duplicate explicit targets, and duplicate checklist IDs at zero.
When one prompt surface needs more coverage, consolidate the checks into that surface's existing
eval entry instead of adding a parallel duplicate-target eval.

## Dependency Manifest Tools

Dependency manifest checks live under `tools/agent_tools/` and are Bash-first.

- `scan_code_dependencies.sh` extracts code dependency edges from imports, local includes, and shell `source` statements. This is not a dependency header tool.
- `scan_dependency_headers.sh` reports missing `@dependency-start` / `@dependency-end` markers.
- `check_dependency_header_format.sh` validates manifest syntax, relative paths, kinds, and target existence.
- `check_dependency_graph.sh` builds upstream and downstream graphs and fails isolated manifests, self references, and cycles by default.
- `check_dependency_graph.sh --check-bidirectional` additionally checks reverse-edge presence and kind consistency during bidirectional migration.
- `check_dependency_graph.sh --list-related --focus <path>` lists every manifest edge declared by, or pointing at, a changed code/doc path so reviewers can see all dependent surfaces before implementation review.
- `run_repo_dependency_review.sh` runs scan, format, and graph checks against all tracked checkable repo files. Use this during checkpoint and final review, not only closeout.
- `run_repo_dependency_review.sh --list-changed-dependencies` adds the same related-surface listing for current changed files.
- GitHub path-constraint root copies such as
  `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` keep AgentCanon-source
  dependency headers. The format and graph checkers resolve those dependency
  paths against the AgentCanon source file when `vendor/agent-canon` is
  present, so root-copy review does not require duplicate root-only headers.
- `tool_catalog.py` validates the structured AgentCanon tool catalog, per-entry summaries, default wiring, docs/tests, retired legacy paths, and one-to-one tool docs.
- `tool_drift.py` validates dependency-manifest trace links between tools, PR flow docs/templates, workflow checks, and convention gates.
- `responsibility_scope.py` validates top-level `responsibility-scope.toml`, required top-level coverage, protecting tool catalog entries, and linked issue files.
- `issue_sync.py` validates durable local issues and plans GitHub Issue mirrors without requiring network access in CI.
- `eval_accumulation_check.py` validates append-only hook, skill eval, and local LLM eval results before guide generation consumes them.

Do not use Dockerfile or environment files as universal dependency anchors.
Use `environment` edges only for real Docker / CI / requirements / runtime coupling.
Generic canon files should connect to the nearest canon-owned anchor such as `AGENTS.md`, `README.md`, a directory README, a canonical workflow document, or this tool index.

For analysis-first work, run code dependency extraction and header dependency graph validation separately.
Use code dependency evidence to understand import/include/source reachability, and header dependency evidence to decide which design, docs, tests, workflow, and environment context must be read before editing.

## Static Design Analysis Tools

- `check_convention_compliance.py` aggregates convention compliance evidence. It verifies that every convention source exists, every normative convention document exposes a verification route, prohibition-bearing documents carry a prohibition section, every manifestable convention gate has a tool or prompt-eval check, every workflow calls the convention gate, workflow prohibitions remain wired, and skill-routing prompts delegate tool-covered rules to the checker.
- `tool_catalog.py` keeps the AgentCanon tool catalog machine-readable and blocks stale paths, uncataloged default-wired tools, missing docs/tests, retired legacy entries, and broken tool-doc mappings.
- `tool_drift.py` checks dependency-header trace contracts for GitHub PR flow, AgentCanon PR validation, convention compliance, repo dependency review, and the tool catalog.
- `responsibility_scope.py` keeps checker/tool ownership tied to a scope so new gates do not become orphaned entrypoints.
- `issue_sync.py` keeps folder issues structurally valid and gives GitHub Issue sync a repeatable command plan.
- `eval_accumulation_check.py` keeps hook and skill eval evidence usable by improvement-guide and feedback-loop tools.
- `local_llm_eval.py` keeps Local LLM single-file responsibility analysis covered by configurable eval cases without making model output a repo-wide gate.
- `check_hardcoded_numbers.py` checks Python and C++ sources for unexplained numeric literals. It allows only small universal literals by default, accepts uppercase Python module constants and C++ `constexpr` constants, and supports line-local `hardcoded-number-ok` allowances for formula or standard-derived values.
- `analyze_refactor_surface.py` scores Python refactor surfaces for long functions, long classes, long files, and wide public method surfaces.
- `helper_function_inventory.py` inventories Python helper functions/classes and infers roles from AST body facts, calls, side effects, path domain, internal call graph evidence, single-caller or file-local specialization, and functional candidate rules. It reports high-confidence `auto_helper` verdicts separately from `needs_user_judgment` symbols, with `--only-auto-helpers` and `--only-user-judgment` filters for review loops.
- `tools/oop/python/readability.py` scores Python OOP readability risks. It checks vague class/helper names, oversized classes/functions, wide public surfaces, excessive instance state/parameters, static-method namespace classes, `None` runtime routing, mixed transform/effect boundaries, cognitive-complexity signals, redundant wrappers, stateless callable classes, pass-through functions, identity functions, and trivial formatting functions.
- `tools/oop/cpp/readability.py` scores C/C++ OOP readability risks. It checks vague type names, oversized classes/functions, wide public fields/methods, excessive parameters/base classes, `nullptr` runtime routing, mixed transform/effect boundaries, pass-through wrappers, identity functions, and trivial formatting functions. It also preserves intentional C++ boundaries for schema/value-object aggregates, annotated primitive ABI functions, `__nad_` exported ABI functions, expression-DSL identity terminals, and compact numeric scalar wrappers.
- `tools/oop/*/readability.py --format markdown --include-snippets` writes a deterministic mechanical report that explains each finding by OOP dimension and line number.
- `tools/oop/*/readability.py --exclude vendor --exclude reports ...` keeps vendored snapshots and generated artifacts out of external-repo scans. Record the exact path set and excludes beside the report.
- `tools/oop/*/readability.py --review-prompt-out <path>` writes a prompt for `oop_readability_reviewer`. The reviewer documents the mechanical report, but does not change the score, thresholds, counts, paths, line numbers, or pass/fail verdict.

These tools are review aids.
Use them to set baseline / target / actual scores in refactor or design artifacts.
For hardcoded numeric literals, treat `HARDCODED_NUMBERS=fail` as a fix-surface issue: either name the value, move it to typed configuration / API input, or justify the literal with a local allowance.
For OOP readability, keep the mechanical report as the source of truth and use `oop_readability_reviewer` only to write the reader-facing interpretation and false-positive notes.

## Container Configuration Tools

- `tools/ci/container_config.py` statically validates repo-local Dockerfile,
  runtime pack, and AgentCanon-owned devcontainer configuration without
  requiring Docker or Podman to run. It returns `CONTAINER_CONFIG=skip` only
  when a checkout has neither `docker/` nor `.devcontainer/`.
- `tools/docker_dependency_validator.sh` remains the shell-level dependency
  contract for canonical Docker image contents.
- `tools/ci/run_container_pack.py --print-only` previews the build and smoke
  commands resolved from `docker/packs/*.toml`.

## 含めないもの

- clone 直後の repo-local 初期化
- template 固有の name / slug / bare remote 置換

それらは root `scripts/` に残します。

## Bash 実装の扱い

- shared automation として配る Bash は `tools/` に置きます。
- repo ごとに変わる bootstrap Bash は root `scripts/` に残します。
- agent helper、CI、review、validation、container runner、experiment helper の Bash を root `scripts/` に置くことを禁止します。

## 入口

- template 利用者:
  - root `tools/` から使います
- shared canon 保守者:
  - `vendor/agent-canon/tools/` を source of truth として編集します

## 関連文書

- `documents/SHARED_RUNTIME_SURFACES.md`
- `agents/workflows/agent-canon-pr-workflow.md`
- `documents/agent-canon-subtree-migration.md`
