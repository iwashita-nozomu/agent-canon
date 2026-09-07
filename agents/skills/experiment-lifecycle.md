# experiment-lifecycle
<!--
@dependency-start
contract skill
responsibility Owns experiment run identity, lifecycle state, reproducibility core, and explicit rerun/publication decisions without owning artifact files or report prose.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable experiment and report structure contract
upstream design prose-reasoning-graph.md prose graph experiment-plan diagnostics overlay
downstream implementation ../../tools/validation/semantic/tools/tool_rejection_preflight.py predicts experiment execution surface guardrails
@dependency-end
-->


## Purpose

実験の準備、初期化、実行、結果整理、review、再実行判断を一続きの運用として扱います。

## Ownership Contract

Own one experiment run from preparation through terminal status. Run identity/state and the reproducibility core belong here; physical files, semantic roles, checksums, and durable readback belong to `result-artifact-writeout`; reader-facing claims belong to `report-writing` only when requested; browser artifacts belong to `html-output` only when requested. Annex retention is an explicit `save_experiment_result_annex.py` operation rather than an effect of saving files.

The reproducibility core records source identity, effective configuration, executed command/protocol, relevant environment/runtime identity, terminal status including failed or partial states, and references to artifacts that actually exist. No universal filename inventory is imposed: summaries, case records, visualization.py renderers, plots, and logs are producer-specific outputs and are required only when the selected producer/protocol declares them.

Topic-specific metrics, observations, thresholds, comparisons, and research-success judgments belong to the topic or research owner. This skill records the declared protocol and operational evidence, but it does not turn execution state, exit status, artifact presence, or readback into a universal research acceptance gate.

## Use When

- experiment directory の初期化
- case 群の実行
- result / report 生成
- critical review と report review を挟んだ実験反復
- rerun、追加検証、report 書き直しの分岐

## Topic Preparation

新規 topic は、topic 名と registry identity を先に固定してから、次の creator route を実行します。

```bash
python3 tools/experiments/lifecycle/create_experiment_topic.py <topic>
```

この tool が `templates/experiments/_template/` を唯一の copy source として
`experiments/<topic>/`、`README.md`、`provenance.toml`、registry entry を同時に作成します。
`report/.gitkeep` と `result/.gitkeep` もこの route で用意されます。template directory の直接コピーや
別の document template fallback は使いません。

## Core References

- `documents/experiments/experiment-registry.md`
- `tools/experiments/lifecycle/create_experiment_topic.py`
- `agents/skills/research-workflow.md`
- `agents/skills/adaptive-improvement-loop.md`

## Role In Research-Driven Change

- この skill は `Research-Driven Change` の inner loop です。
- 外側の仮説更新や次の change 決定は `research-workflow` が扱います。
- この skill は 1 つの protocol と 1 回の run、またはその直後の rewrite / extra validation / rerun 分岐を扱います。

## Protocol Selection

実験は topic の protocol、選択した runtime profile、または明示された依頼で必要な段階だけ
実行します。準備、コード実装、静的チェック、run、report は独立した選択肢であり、全段階を
暗黙に実行しません。実験前に `Question`、`Comparison Target`、`Stop Condition`、
`Fairness Notes`、`Artifact Plan`、`Visualization Plan`、`Naming Plan`、`Registry Plan`、
`Config Snapshot Plan`、`Execution Plan` を必要な範囲で固定します。

新規 topic の標準入口は `create_experiment_topic.py` です。作成後の編集順は
`run.py` の `main::main`、`cases.py`、`config.yaml`、`visualization.py`、`README.md` とし、
template の直接コピーや別の scaffold fallback を使いません。

## Execution Modes

- `debug` / `smoke`: import、worker 起動、shape / env mismatch などの局所確認。正式な
  comparison evidence に昇格させない
- `verified`: protocol が選んだ backend / environment で bounded run を行い、宣言した
  status・failure・artifact を確認する
- `formal`: 比較表や report の根拠となる fresh run。case set、timeout、dtype、backend、
  worker、出力先を開始前に固定し、1 invocation で完走させる

`spot run`、途中停止した partial run、都合のよい subset、途中編集で継ぎ足した run は
formal evidence にしません。失敗・停止は `Stop Reason:` と `Restart Decision:` を記録し、
必要なら新しい `run_name` で最初から実行します。debug / smoke を残す場合は、その種別を
artifact と report に明記します。

## Implementation Boundary

topic code は問いと比較を表現する薄い層に保ちます。`run.py` は orchestration、`cases.py`
は case / difficulty / resource estimate、`task(case, context)` は一 case の研究ロジック、
`context_builder` / `initializer` は case 環境、`resource_estimate` は resource 見積りを
所有します。process lifecycle、timeout、child cleanup、worker completion、GPU / CPU slot、
環境変数の child 反映は managed runner に委譲し、topic 側に mini-runner、scheduler、独自
completion 契約、GPU 割当、signal 回収、partial resume protocol を追加しません。

managed lifecycle を選ぶ場合、scheduler と runner は一度だけ構築し、`runner.run(worker)`
を一度だけ呼びます。terminal `ExecutionResult` は scheduler completion のみを正本とし、
topic、hook、admission context、wrapper が runner return を別の result として読みません。

## Output and Carry-over

run artifact は `result/<run-id>/raw/` と `result/<run-id>/summary/` に分け、実際に producer が
選んだものだけを `result-artifact-writeout` へ渡します。topic の `visualization.py` は run
artifact reader / renderer であり、formal run launcher、test surface、config source には
しません。reader-facing report は `report-writing` を選んだ場合だけ作り、複数 run の知見は
必要な場合にだけ topic note へ持ち上げます。formal result の annex retention は明示的な
`save_experiment_result_annex` 操作です。

## Boundary

- この skill が repo 横断の実験 lifecycle 正本です。topic 固有の詳細は各 topic README と
  `documents/experiments/experiment-registry.md` が所有します。
- 実験結果を見ながら code change、調査、チューニングまで含めた loop を回す場合は `adaptive-improvement-loop` を追加します。
- topic の entrypoint と formal command は project-root `experiments/registry.toml` を project-owned 正本にします。AgentCanon source は registry 契約を `documents/experiments/experiment-registry.md` で定義します。parent root からは qualified ignored source clone または task が選択した published source revision として読みます。
- 新規 topic は Topic Preparation の creator route を実行します。create tool が内部の runnable scaffold owner を解決し、project-root `experiments/<topic>/`、canonical な topic `README.md` / `provenance.toml`、および project registry の topic entry を配置します。
- topic 作成後は `run.py` の `main::main`、`cases.py`、`config.yaml`、`visualization.py`、`README.md` の順で編集します。
- project registry がある場合は、実行前に `python3 -m tools.validation.ci.checks.check_experiment_registry` で registry schema と registered command placeholder を確認します。
- 実験の利用者向け入口は `python3 -m tools.experiments.execution.run_managed_experiment --topic <topic> --variant <variant> -- python3 experiments/<topic>/run.py` です。`run.py` は managed runner から呼ばれる inner entrypoint として、`result/<run-id>/raw/` と `result/<run-id>/summary/` の作成、設定 snapshot、atomic artifact 書き出しを所有します。
- 実験設定の checked-in 正本は `experiments/<topic>/config.yaml` に置き、run 時に `config_snapshot.json` などの topic config snapshot として保存します。
- GPU / JAX の実行環境の所有者は scheduler または caller environment とします。実験 topic の code と checked-in config は、GPU visibility、JAX platform、allocator、preallocation などの run ごとの環境割当を埋め込まない形に保ちます。実行環境 contract 自体を変更する task では、`environment-maintenance` と scheduler の正本へ分岐します。
- topic README は、実験内容、問い、比較対象、標準コマンド、設定正本、可視化 visualization.py renderer、出力 schema、run_name 規則を固定する入口です。
- 非自明な実験 README には、再利用する `python/` 配下の file、class、function を名前で列挙する implementation source map と、各 step が作る object、更新する object、下流へ渡す object、artifact として書く object を追える object-flow 節を置きます。variant 比較では、共通実行 path と、variant が分岐する factory / function 境界を明示します。
- 可視化は `experiments/<topic>/visualization.py` の topic 固有 renderer に置き、formal run の起動や設定正本にはしません。既定 scaffold は visualization.py renderer を生成しません。
- 実験 topic を review する段階では `experiment-review` を使い、managed runner route、GPU/JAX 環境所有、artifact schema、visualization.py renderer readiness を checklist として確認します。
- 各 topic run は `result/<run-id>/` を持ちます。生結果は `raw/`、要約・証跡は `summary/` に分け、追加ログも所有者を明示してこの二つの境界を跨がないようにします。
- run artifact は、選択した producer / protocol が実際に生成すると宣言したものだけを要求します。存在する artifact は `result-artifact-writeout` に渡して role / checksum / readback を記録し、生成対象でない optional artifact の placeholder や limitation は作りません。
- smoke / formal の入口は project `Makefile` に置く場合も、内側では同じ managed runner が topic `run.py` を inner command として呼びます。
- run は source checkout、既定では `main` で実行します。run identity / terminal status はこの skill、実在する file / role / checksum / readback は `result-artifact-writeout` が所有します。durable retention が必要な場合だけ `python3 -m tools.experiments.artifacts.save_experiment_result_annex --result-dir experiments/<topic>/result/<run_name> --annex-repo "$EXPERIMENT_RESULT_ANNEX_REPO"` を明示的に実行します。archive は annex worktree の `experiments/<topic>/result/<run_name>.tar.gz` に一度だけ作成し、remote push はこの操作に含めません。
- experiment execution surface を変更する task は、patch 前に
  `python3 tools/validation/semantic/tools/tool_rejection_preflight.py --root . <planned-edit-paths>`
  を実行し、`experiment_execution_surface_guard` の handoff を解決します。
  対象 surface は `tools/validation/ci/checks/check_experiment_registry.py`、`documents/experiments/experiment-registry.md`、
  `experiments/registry.toml`、topic `run.py` entrypoint です。
  この場合は `test-design` を併用します。project `experiments/registry.toml`
  がある checkout では `python3 -m tools.validation.ci.checks.check_experiment_registry` を実行します。
  runner / registry checker behavior を変える場合は
  `python3 -m pytest tests/tools/test_run_managed_experiment.py -q` で確認します。
  formal experiment run は明示された run plan の実行段階で扱います。
- result artifact の保存は `result-artifact-writeout` に委譲します。reader-facing report は要求された場合だけ `report-writing`、HTML artifact は要求された場合だけ `html-output` を追加し、run state、artifact state、report state、publication state を一つの wrapper に再統合しません。
- experiment plan、rerun plan、result report、HTML view の構造が非自明な場合は、run や report 生成の前に `structure-planning` を使い、first artifact、source-to-structure map、metric contract、invalid interpretation、validation gate を固定します。
- experiment plan / report の structure contract には OOP 観点を入れます。
  再利用する module / class / function / protocol、各 step が作る object、
  変更する object、下流へ渡す object、artifact として書く object、variant が
  差し替わる factory / function 境界、orchestration / domain logic / metric /
  visualization / artifact I/O の依存方向を固定してから section order を書きます。
- experiment plan / report の paragraph order、causal transition、evidence-to-claim transition が非自明な場合は、`structure-planning` 側で `agent-canon semantic-index discourse-relations --profile experiment-report` または `--profile methods-protocol` を使い、discourse edge を構造 evidence として保存します。
- prose graph handoff がある場合は、hypothesis / metric / baseline / expected-result diagnostics を experiment plan または rerun plan の入力にします。

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read `agents/skills/experiment-lifecycle.md`.
1. Keep execution steps, result paths, and report locations consistent with this skill and the topic README.
1. Select only the preparation, implementation, static-check, execution, or report phase required by the topic protocol; do not turn optional phases into universal gates.
1. Classify a run as `debug`/`smoke`, `verified`, or `formal`. Do not promote spot, subset, or partial runs to formal comparison evidence; stopped runs require `Stop Reason:` and `Restart Decision:` plus a fresh run identity when rerun.
1. For a new experiment topic, fix the topic name first and run `python3 tools/experiments/lifecycle/create_experiment_topic.py <topic>`; the tool owns scaffold placement and registry registration. Then edit `run.py` `main::main`, `cases.py`, `config.yaml`, `visualization.py`, and `README.md` in that order. Do not copy `templates/experiments/_template/` directly.
1. Treat project-root `experiments/registry.toml` as the project-owned topic registry for entrypoints and registered smoke/formal commands. AgentCanon source owns the registry contract in `documents/experiments/experiment-registry.md`; from a parent root, read it from the qualified ignored source clone or published source revision selected by the task.
1. When a project registry exists, validate registry schema and registered command placeholders with `python3 -m tools.validation.ci.checks.check_experiment_registry` before execution.
1. Treat `python3 -m tools.experiments.execution.run_managed_experiment --topic <topic> --variant <variant> -- python3 experiments/<topic>/run.py` as the user-facing run route. The topic `run.py` is an inner entrypoint called by the managed runner and owns `result/<run-id>/raw/`, `result/<run-id>/summary/`, config snapshotting, and atomic artifact writing.
1. Keep topic code limited to experiment orchestration, case logic, context construction, and declared resource estimates; delegate process lifecycle, timeout, child cleanup, completion, slot allocation, and caller environment propagation to the managed runner.
1. When the managed lifecycle is selected, construct one scheduler and one runner and call `runner.run(worker)` once; read terminal `ExecutionResult` from scheduler completions rather than creating a second result path.
1. After a canonical run from the source checkout, usually `main`, keep run identity and terminal status in this lifecycle record, delegate each concrete generated file to `$result-artifact-writeout`, and invoke `python3 -m tools.experiments.artifacts.save_experiment_result_annex --result-dir experiments/<topic>/result/<run_name> --annex-repo "$EXPERIMENT_RESULT_ANNEX_REPO"` only as an explicit retention operation. The archive manifest records source provenance and the append-only result identity.
1. Keep GPU/JAX execution-environment ownership in the scheduler or caller environment. Experiment topic code and checked-in configs stay free of hard-coded per-run environment assignment such as GPU visibility, JAX platform, allocator, or preallocation overrides unless the task is explicitly an environment-contract change.
1. Preserve available GPU parallelism by default. Do not force a topic to single-GPU or serial execution by adding `max_workers: 1`, GPU visibility filters, single-device JAX platform settings, or equivalent throttles unless the user explicitly requests serial debugging or the run plan records a concrete environment limit. `gpu_max_slots: 1` means one worker slot per GPU; it must not be used as a substitute for reducing the visible GPU set.
1. When a Python process remains after an interrupted or failed experiment, identify the parent `run.py`, child worker, process group, and elapsed time before calling it residual. Treat active parent/worker processes as a still-running experiment and stop them only when the user asks for abort or cleanup.
1. If the user restricts validation, distinguish non-persistent static checks from checks that leave artifacts. Static checks that do not create durable outputs are allowed. Experiment runs, visualization.py renderer execution, smoke checks, report generators, or any validation that writes result/log/report artifacts must not be run unless the user asks for them; when such a command is run and creates transient artifacts, delete those artifacts immediately after the run and report the cleanup.
1. Keep checked-in experiment settings in `experiments/<topic>/config.yaml`; run artifacts must include a topic config snapshot, commonly `config_snapshot.json`, written by `run.py`.
1. Keep topic-specific metrics, observations, thresholds, comparisons, and research-success judgments with the topic or research owner. Treat run state, exit status, artifact presence, and readback as operational evidence; do not promote them to a universal research acceptance gate.
1. Require `experiments/<topic>/README.md` to describe the experiment content, question, comparison target, standard commands, config source, visualization visualization.py renderer, output schema, and run_name convention before formal execution.
1. Require each nontrivial experiment README to include an implementation source map that lists the reused `python/` files, classes, and functions by name, plus a separate object-flow section that shows which objects each step creates, mutates, passes downstream, and writes as artifacts. If an experiment compares variants, identify the single shared execution path and the exact factory/function boundary where variants differ.
1. Put topic visualization in `experiments/<topic>/visualization.py`; a topic may emit HTML or image artifacts from its renderer, but visualization must not be the formal run launcher, fine-grained test surface, or config source of truth.
1. When reviewing an experiment topic, add `$experiment-review` and check the managed runner route, GPU/JAX environment ownership, artifact schema, and visualization.py renderer readiness.
1. Ensure every topic run has `result/<run-id>/raw/` and `result/<run-id>/summary/`; compact outputs use `summary/summary.json` and `summary/cases.jsonl`, with no root-level fallback.
1. Require only producer-declared artifacts. Record references to files that actually exist through `$result-artifact-writeout`; do not impose a universal summary/case/visualization.py renderer/log inventory or create synthetic missing-artifact limitations for outputs the producer did not select.
1. For planned edits to experiment execution surfaces, run `python3 tools/validation/semantic/tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and resolve the `experiment_execution_surface_guard` handoff before patching. This surface includes `tools/validation/ci/checks/check_experiment_registry.py`, `documents/experiments/experiment-registry.md`, `experiments/registry.toml`, and topic `run.py` entrypoints. Pair this skill with `$test-design`; run `python3 -m tools.validation.ci.checks.check_experiment_registry` when project `experiments/registry.toml` exists, use `python3 -m pytest tests/tools/test_run_managed_experiment.py -q` for runner or registry checker behavior changes, and reserve long experiment runs for an explicit run plan.
1. Use `$structure-planning` before experiment planning, rerun planning, result report generation, or HTML view generation when the structure is nontrivial; fix first artifact, source-to-structure map, OOP structure contract, metric contract, invalid interpretations, and validation gate before running or writing.
1. For experiment plans and reports, require the OOP structure contract to list reused modules/classes/functions/protocols, objects created/mutated/passed/written by each step, the factory/function boundary where variants differ, and dependency direction across orchestration, domain logic, metrics, visualization, and artifact I/O before section order is drafted.
1. For experiment plans or reports with nontrivial paragraph order or causal/evidence transitions, ask `$structure-planning` to use `agent-canon semantic-index discourse-relations --profile experiment-report` or `--profile methods-protocol` as advisory edge evidence.
1. If a prose graph handoff is present, use hypothesis, metric, baseline, and expected-result diagnostics as advisory input to the experiment plan or rerun plan.
1. Use `$result-artifact-writeout` for concrete experiment files, add `$report-writing` only for requested reader-facing interpretation, and add `$html-output` only for requested HTML. Keep publication as an explicit lifecycle decision rather than a side effect of artifact writeout.
1. If code changes must iterate with explicit decision states and a backlog, also use `$adaptive-improvement-loop`.
