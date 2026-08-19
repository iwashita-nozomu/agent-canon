# experiment-lifecycle
<!--
@dependency-start
contract skill
responsibility Owns experiment run identity, lifecycle state, reproducibility core, and explicit rerun/publication decisions without owning artifact files or report prose.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable experiment and report structure contract
upstream design prose-reasoning-graph.md prose graph experiment-plan diagnostics overlay
downstream implementation ../../tools/agent_tools/tool_rejection_preflight.py predicts experiment execution surface guardrails
@dependency-end
-->


## Purpose

実験の準備、初期化、実行、結果整理、review、再実行判断を一続きの運用として扱います。

## Ownership Contract

Own one experiment run from preparation through terminal status. Run identity/state and the reproducibility core belong here. The same `ExperimentIdentity(topic, variant, run_name)` derives two disjoint source-side homes: `result/<variant>/<run_name>/` for compact review evidence that remains eligible for normal Git tracking, and `raw/<variant>/<run_name>/` for bulky source data, long logs, dumps, and regenerable intermediates ignored by the source repository. Physical files, semantic roles, checksums, and durable readback belong to `result-artifact-writeout`; reader-facing claims belong to `report-writing` only when requested; browser artifacts belong to `html-output` only when requested. Annex retention is an explicit raw-only `save_experiment_result_annex.py` operation rather than an effect of saving files.

The reproducibility core records source identity, effective configuration, executed command/protocol, relevant environment/runtime identity, terminal status including failed or partial states, and references to artifacts that actually exist. No universal filename inventory is imposed: summaries, case records, notebooks, plots, and logs are producer-specific outputs and are required only when the selected producer/protocol declares them.

## Use When

- experiment directory の初期化
- case 群の実行
- result / report 生成
- critical review と report review を挟んだ実験反復
- rerun、追加検証、report 書き直しの分岐

## Core References

- `agents/workflows/experiment-workflow.md`
- `documents/experiments/experiment-registry.md`
- `tools/experiments/create_experiment_topic.py`
- `agents/workflows/research-workflow.md`

## Role In Research-Driven Change

- この skill は `Research-Driven Change` の inner loop です。
- 外側の仮説更新や次の change 決定は `research-workflow` が扱います。
- この skill は 1 つの protocol と 1 回の run、またはその直後の rewrite / extra validation / rerun 分岐を扱います。

## Boundary

- この repo の実験運用正本は `agents/workflows/experiment-workflow.md` です。
- 実験結果を見ながら code change、調査、チューニングまで含めた loop を回す場合は `adaptive-improvement-loop` を追加します。
- topic の entrypoint と formal command は project-root `experiments/registry.toml` を project-owned 正本にします。AgentCanon source は registry 契約を `documents/experiments/experiment-registry.md` で定義します。template / derived repo root からは `vendor/agent-canon/documents/experiments/experiment-registry.md` として読みます。
- 新規 topic は最初に実験名を固定し、`python3 -m tools.experiments.create_experiment_topic <topic>` を実行します。create tool が内部の runnable scaffold owner を解決し、project-root `experiments/<topic>/`、canonical な topic `README.md` / `provenance.toml`、および project registry の topic entry を配置します。`templates/experiments/_template/` の直接コピーは行いません。
- topic 作成後は `run.py` の `main::main`、`cases.py`、`config.yaml`、`visualize.ipynb`、`README.md` の順で編集します。
- project registry がある場合は、実行前に `python3 -m tools.ci.check_experiment_registry` で registry schema と registered command placeholder を確認します。
- 実験の利用者向け入口は `python3 -m tools.experiments.run_managed_experiment --topic <topic> --variant <variant> -- python3 experiments/<topic>/run.py` です。`run.py` は managed runner から呼ばれる inner entrypoint として、run directory 作成、設定 snapshot、artifact 書き出し、notebook 実行を所有します。
- 実験設定の checked-in 正本は `experiments/<topic>/config.yaml` に置き、run 時に `config_snapshot.json` などの topic config snapshot として保存します。
- GPU / JAX の実行環境の所有者は scheduler または caller environment とします。実験 topic の code と checked-in config は、GPU visibility、JAX platform、allocator、preallocation などの run ごとの環境割当を埋め込まない形に保ちます。実行環境 contract 自体を変更する task では、`environment-maintenance` と scheduler の正本へ分岐します。
- topic README は、実験内容、問い、比較対象、標準コマンド、設定正本、可視化 notebook、出力 schema、run_name 規則を固定する入口です。
- 非自明な実験 README には、再利用する `python/` 配下の file、class、function を名前で列挙する implementation source map と、各 step が作る object、更新する object、下流へ渡す object、artifact として書く object を追える object-flow 節を置きます。variant 比較では、共通実行 path と、variant が分岐する factory / function 境界を明示します。
- 可視化は `experiments/<topic>/visualize.ipynb` の Jupyter notebook に置き、formal run の起動や設定正本にはしません。
- notebook の各可視化項目は、直前の Markdown cell に日本語で「入力 artifact」「描く量」「読み方」を 1-2 文で説明します。
- 実験 topic を review する段階では `experiment-review` を使い、managed runner route、GPU/JAX 環境所有、artifact schema、notebook readiness を checklist として確認します。
- 各 run は同一 identity から `result/<variant>/<run_name>/` と `raw/<variant>/<run_name>/` を持ちます。managed runner は child に `EXPERIMENT_RUN_DIR` と `EXPERIMENT_RAW_DIR` を明示し、topic 側で variant や run name を再解析しません。`result/` は summary、case record、config/source/environment snapshot、manifest、failure evidence など compact review evidence に限定します。原データ、長大 stdout/stderr、dump、再生成可能な中間生成物は `raw/` のみに書き、`raw/.gitignore` 自身を除いて通常 Git へ追加しません。
- run artifact は、選択した producer / protocol が実際に生成すると宣言したものだけを要求します。存在する artifact は `result-artifact-writeout` に渡して role / checksum / readback を記録し、生成対象でない optional artifact の placeholder や limitation は作りません。
- smoke / formal の入口は project `Makefile` に置く場合も、内側では同じ managed runner が topic `run.py` を inner command として呼びます。
- run は source checkout、既定では `main` で実行します。run identity / terminal status はこの skill、実在する compact result と raw file の role / checksum / readback は `result-artifact-writeout` が所有します。durable retention が必要な場合だけ `python3 -m tools.experiments.save_experiment_result_annex --raw-dir experiments/<topic>/raw/<variant>/<run_name> --annex-repo "$EXPERIMENT_RAW_ANNEX_REPO"` を明示的に実行します。archive は annex worktree の `experiments/<topic>/raw/<variant>/<run_name>.tar.gz` に一度だけ作成し、tracked `result/.../summary.json` と `run_manifest.json` の path/digest を retention manifest から read back します。Summary、result manifest、reader report、remote push は raw archive に含めません。
- experiment execution surface を変更する task は、patch 前に
  `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>`
  を実行し、`experiment_execution_surface_guard` の handoff を解決します。
  対象 surface は `tools/ci/check_experiment_registry.py`、`documents/experiments/experiment-registry.md`、
  `agents/workflows/experiment-workflow.md`、`experiments/registry.toml`、topic
  `run.py` entrypoint です。
  この場合は `test-design` を併用します。project `experiments/registry.toml`
  がある checkout では `python3 -m tools.ci.check_experiment_registry` を実行します。
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
1. Keep execution steps, result paths, and report locations consistent with the canonical experiment workflow.
1. For a new experiment topic, fix the topic name first and run `python3 -m tools.experiments.create_experiment_topic <topic>`; the tool owns scaffold placement and registry registration. Then edit `run.py` `main::main`, `cases.py`, `config.yaml`, `visualize.ipynb`, and `README.md` in that order. Do not copy `templates/experiments/_template/` directly.
1. Treat project-root `experiments/registry.toml` as the project-owned topic registry for entrypoints and registered smoke/formal commands. AgentCanon source owns the registry contract in `documents/experiments/experiment-registry.md`; from a template or derived repo root, read that contract as `vendor/agent-canon/documents/experiments/experiment-registry.md`.
1. When a project registry exists, validate registry schema and registered command placeholders with `python3 -m tools.ci.check_experiment_registry` before execution.
1. Treat `python3 -m tools.experiments.run_managed_experiment --topic <topic> --variant <variant> -- python3 experiments/<topic>/run.py` as the user-facing run route. The managed runner derives both canonical result and raw directories from one `ExperimentIdentity`, exports them as `EXPERIMENT_RUN_DIR` and `EXPERIMENT_RAW_DIR`, and calls topic `run.py` as the inner entrypoint. Topic code writes compact review evidence to result and bulky/regenerable output to raw without reparsing identity segments.
1. After a canonical run from the source checkout, usually `main`, keep run identity and terminal status in this lifecycle record and delegate each concrete result/raw file to `$result-artifact-writeout`. Invoke `python3 -m tools.experiments.save_experiment_result_annex --raw-dir experiments/<topic>/raw/<variant>/<run_name> --annex-repo "$EXPERIMENT_RAW_ANNEX_REPO"` only as an explicit retention operation. The raw-only archive manifest records source provenance, append-only identity, raw file digests, and the path/digest binding to tracked result evidence; it does not copy Summary or report content.
1. Keep GPU/JAX execution-environment ownership in the scheduler or caller environment. Experiment topic code and checked-in configs stay free of hard-coded per-run environment assignment such as GPU visibility, JAX platform, allocator, or preallocation overrides unless the task is explicitly an environment-contract change.
1. Preserve available GPU parallelism by default. Do not force a topic to single-GPU or serial execution by adding `max_workers: 1`, GPU visibility filters, single-device JAX platform settings, or equivalent throttles unless the user explicitly requests serial debugging or the run plan records a concrete environment limit. `gpu_max_slots: 1` means one worker slot per GPU; it must not be used as a substitute for reducing the visible GPU set.
1. When a Python process remains after an interrupted or failed experiment, identify the parent `run.py`, child worker, process group, and elapsed time before calling it residual. Treat active parent/worker processes as a still-running experiment and stop them only when the user asks for abort or cleanup.
1. If the user restricts validation, distinguish non-persistent static checks from checks that leave artifacts. Static checks that do not create durable outputs are allowed. Experiment runs, notebook execution, smoke checks, report generators, or any validation that writes result/log/report artifacts must not be run unless the user asks for them; when such a command is run and creates transient artifacts, delete those artifacts immediately after the run and report the cleanup.
1. Keep checked-in experiment settings in `experiments/<topic>/config.yaml`; run artifacts must include a topic config snapshot, commonly `config_snapshot.json`, written by `run.py`.
1. Require `experiments/<topic>/README.md` to describe the experiment content, question, comparison target, standard commands, config source, visualization notebook, output schema, and run_name convention before formal execution.
1. Require each nontrivial experiment README to include an implementation source map that lists the reused `python/` files, classes, and functions by name, plus a separate object-flow section that shows which objects each step creates, mutates, passes downstream, and writes as artifacts. If an experiment compares variants, identify the single shared execution path and the exact factory/function boundary where variants differ.
1. Put the visualization notebook at `experiments/<topic>/visualize.ipynb`; notebooks read run artifacts and render figures/tables, but they must not be the formal run launcher, fine-grained test surface, or config source of truth.
1. For each notebook visualization item, add a Markdown cell immediately above the code cell in Japanese explaining the input artifact, the plotted quantity, and how to read the figure in one or two sentences.
1. When reviewing an experiment topic, add `$experiment-review` and check the managed runner route, GPU/JAX environment ownership, artifact schema, and notebook readiness.
1. Ensure every run has both `result/<variant>/<run_name>/` and `raw/<variant>/<run_name>/` from the same identity. Keep compact review evidence in result. Put original datasets, long stdout/stderr, dumps, and regenerable intermediates under raw; do not duplicate them into result merely to make retention convenient.
1. Require only producer-declared artifacts. Record references to files that actually exist through `$result-artifact-writeout`; do not impose a universal summary/case/notebook/log inventory or create synthetic missing-artifact limitations for outputs the producer did not select.
1. For planned edits to experiment execution surfaces, run `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and resolve the `experiment_execution_surface_guard` handoff before patching. This surface includes `tools/ci/check_experiment_registry.py`, `documents/experiments/experiment-registry.md`, `agents/workflows/experiment-workflow.md`, `experiments/registry.toml`, and topic `run.py` entrypoints. Pair this skill with `$test-design`; run `python3 -m tools.ci.check_experiment_registry` when project `experiments/registry.toml` exists, use `python3 -m pytest tests/tools/test_run_managed_experiment.py -q` for runner or registry checker behavior changes, and reserve long experiment runs for an explicit run plan.
1. Use `$structure-planning` before experiment planning, rerun planning, result report generation, or HTML view generation when the structure is nontrivial; fix first artifact, source-to-structure map, OOP structure contract, metric contract, invalid interpretations, and validation gate before running or writing.
1. For experiment plans and reports, require the OOP structure contract to list reused modules/classes/functions/protocols, objects created/mutated/passed/written by each step, the factory/function boundary where variants differ, and dependency direction across orchestration, domain logic, metrics, visualization, and artifact I/O before section order is drafted.
1. For experiment plans or reports with nontrivial paragraph order or causal/evidence transitions, ask `$structure-planning` to use `agent-canon semantic-index discourse-relations --profile experiment-report` or `--profile methods-protocol` as advisory edge evidence.
1. If a prose graph handoff is present, use hypothesis, metric, baseline, and expected-result diagnostics as advisory input to the experiment plan or rerun plan.
1. Use `$result-artifact-writeout` for concrete experiment files, add `$report-writing` only for requested reader-facing interpretation, and add `$html-output` only for requested HTML. Keep publication as an explicit lifecycle decision rather than a side effect of artifact writeout.
1. If code changes must iterate with explicit decision states, also use `experiment-change-loop`.
