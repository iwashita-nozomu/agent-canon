# experiment-lifecycle
<!--
@dependency-start
contract skill
responsibility Documents experiment-lifecycle for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable experiment and report structure contract
upstream design prose-reasoning-graph.md prose graph experiment-plan diagnostics overlay
downstream implementation ../../tools/agent_tools/tool_rejection_preflight.py predicts experiment execution surface guardrails
@dependency-end
-->


## Purpose

実験の準備、初期化、実行、結果整理、review、再実行判断を一続きの運用として扱います。

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
- 新規 topic は最初に実験名を固定し、`python3 tools/experiments/create_experiment_topic.py <topic>` を実行します。create tool が内部の runnable scaffold owner を解決し、project-root `experiments/<topic>/`、canonical な topic `README.md` / `provenance.toml`、および project registry の topic entry を配置します。`templates/experiments/_template/` の直接コピーは行いません。
- topic 作成後は `run.py` の `main::main`、`cases.py`、`config.yaml`、`visualize.ipynb`、`README.md` の順で編集します。
- project registry がある場合は、formal 実行前に `python3 tools/ci/check_experiment_registry.py` で registry schema と registered command placeholder を確認します。
- 実験の利用者向け入口は `python3 tools/experiments/run_managed_experiment.py --topic <topic> --variant formal -- python3 experiments/<topic>/run.py` です。`run.py` は managed runner から呼ばれる inner entrypoint として、run directory 作成、設定 snapshot、artifact 書き出し、notebook 実行を所有します。
- 実験設定の checked-in 正本は `experiments/<topic>/config.yaml` に置き、run 時に `config_snapshot.json` などの topic config snapshot として保存します。
- GPU / JAX の実行環境の所有者は scheduler または caller environment とします。実験 topic の code と checked-in config は、GPU visibility、JAX platform、allocator、preallocation などの run ごとの環境割当を埋め込まない形に保ちます。実行環境 contract 自体を変更する task では、`environment-maintenance` と scheduler の正本へ分岐します。
- topic README は、実験内容、問い、比較対象、標準コマンド、設定正本、可視化 notebook、出力 schema、run_name 規則を固定する入口です。
- 非自明な実験 README には、再利用する `python/` 配下の file、class、function を名前で列挙する implementation source map と、各 step が作る object、更新する object、下流へ渡す object、artifact として書く object を追える object-flow 節を置きます。variant 比較では、共通実行 path と、variant が分岐する factory / function 境界を明示します。
- 可視化は `experiments/<topic>/visualize.ipynb` の Jupyter notebook に置き、formal run の起動や設定正本にはしません。
- notebook の各可視化項目は、直前の Markdown cell に日本語で「入力 artifact」「描く量」「読み方」を 1-2 文で説明します。
- 実験 topic を review する段階では `experiment-review` を使い、managed runner route、GPU/JAX 環境所有、artifact schema、notebook readiness を checklist として確認します。
- 各 run は `result/<run_name>/` を持ちます。追加ログが必要な topic は `result/<run_name>/logs/` に stdout、stderr、startup、tool、diagnostic logs を分けます。
- 標準 run artifact は `summary.json`、`cases.jsonl`、topic config snapshot、case artifacts、`visualize_executed.ipynb` を含みます。これらが無い run は再現性が不足した run として扱い、正式結果には使う前に managed runner route で rerun または明示的な limitation を残します。
- smoke / formal の入口は project `Makefile` に置く場合も、内側では同じ managed runner が topic `run.py` を inner command として呼びます。
- formal run は source checkout、既定では `main` で実行し、run 完了後に
  `save-experiment-results` で source provenance、report presence、manifest、
  append-only collision policy を固定してから
  `python3 tools/experiments/save_experiment_result_annex.py --result-dir experiments/<topic>/result/<run_name> --annex-repo "$EXPERIMENT_RESULT_ANNEX_REPO"`
  で結果と optional report を一つの deterministic git-annex archive に保存します。
- experiment execution surface を変更する task は、patch 前に
  `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>`
  を実行し、`experiment_execution_surface_guard` の handoff を解決します。
  対象 surface は `tools/ci/check_experiment_registry.py`、`documents/experiments/experiment-registry.md`、
  `agents/workflows/experiment-workflow.md`、`experiments/registry.toml`、topic
  `run.py` entrypoint です。
  この場合は `test-design` を併用します。project `experiments/registry.toml`
  がある checkout では `python3 tools/ci/check_experiment_registry.py` を実行します。
  runner / registry checker behavior を変える場合は
  `python3 -m pytest tests/tools/test_run_managed_experiment.py -q` で確認します。
  formal experiment run は明示された run plan の実行段階で扱います。
- result / report 生成では `save-experiment-results` と
  `result-artifact-writeout` を使い、raw run output、summary report、manifest、
  unique run_name、append-only collision policy、source provenance、formal-status を分けます。
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
1. For a new experiment topic, fix the topic name first and run `python3 tools/experiments/create_experiment_topic.py <topic>`; the tool owns scaffold placement and registry registration. Then edit `run.py` `main::main`, `cases.py`, `config.yaml`, `visualize.ipynb`, and `README.md` in that order. Do not copy `templates/experiments/_template/` directly.
1. Treat project-root `experiments/registry.toml` as the project-owned topic registry for entrypoints and registered smoke/formal commands. AgentCanon source owns the registry contract in `documents/experiments/experiment-registry.md`; from a template or derived repo root, read that contract as `vendor/agent-canon/documents/experiments/experiment-registry.md`.
1. When a project registry exists, validate registry schema and registered command placeholders with `python3 tools/ci/check_experiment_registry.py` before formal execution.
1. Treat `python3 tools/experiments/run_managed_experiment.py --topic <topic> --variant formal -- python3 experiments/<topic>/run.py` as the user-facing run route. The topic `run.py` is an inner entrypoint called by the managed runner and owns run directory creation, config snapshotting, artifact writing, and notebook execution.
1. After a canonical run from the source checkout, usually `main`, use
   `$save-experiment-results` before retaining generated result/report artifacts.
   The dedicated save skill owns source provenance, report presence, manifest,
   append-only collision policy, and formal-status before
   `python3 tools/experiments/save_experiment_result_annex.py --result-dir experiments/<topic>/result/<run_name> --annex-repo "$EXPERIMENT_RESULT_ANNEX_REPO"` runs.
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
1. Ensure every run has `result/<run_name>/`; put additional stdout, stderr, startup, tool, or diagnostic logs under `result/<run_name>/logs/` when the topic emits them.
1. Treat `summary.json`, `cases.jsonl`, the topic config snapshot, case artifacts, and `visualize_executed.ipynb` as standard topic run artifacts. If a run lacks them, rerun through the managed runner route or record that the run is not fully reproducible.
1. For planned edits to experiment execution surfaces, run `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and resolve the `experiment_execution_surface_guard` handoff before patching. This surface includes `tools/ci/check_experiment_registry.py`, `documents/experiments/experiment-registry.md`, `agents/workflows/experiment-workflow.md`, `experiments/registry.toml`, and topic `run.py` entrypoints. Pair this skill with `$test-design`; run `python3 tools/ci/check_experiment_registry.py` when project `experiments/registry.toml` exists, use `python3 -m pytest tests/tools/test_run_managed_experiment.py -q` for runner or registry checker behavior changes, and reserve long experiment runs for an explicit run plan.
1. Use `$structure-planning` before experiment planning, rerun planning, result report generation, or HTML view generation when the structure is nontrivial; fix first artifact, source-to-structure map, OOP structure contract, metric contract, invalid interpretations, and validation gate before running or writing.
1. For experiment plans and reports, require the OOP structure contract to list reused modules/classes/functions/protocols, objects created/mutated/passed/written by each step, the factory/function boundary where variants differ, and dependency direction across orchestration, domain logic, metrics, visualization, and artifact I/O before section order is drafted.
1. For experiment plans or reports with nontrivial paragraph order or causal/evidence transitions, ask `$structure-planning` to use `agent-canon semantic-index discourse-relations --profile experiment-report` or `--profile methods-protocol` as advisory edge evidence.
1. If a prose graph handoff is present, use hypothesis, metric, baseline, and expected-result diagnostics as advisory input to the experiment plan or rerun plan.
1. Use `$save-experiment-results` with `$result-artifact-writeout` for
   experiment result/report generation so raw run output, Markdown summary,
   manifest, run name, append-only collision policy, source provenance, and
   formal-status are recorded separately.
1. If code changes must iterate with explicit decision states, also use `experiment-change-loop`.
