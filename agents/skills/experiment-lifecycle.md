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
- `documents/experiment-registry.md`
- `tools/experiments/create_experiment_topic.py`
- `agents/workflows/research-workflow.md`

## Role In Research-Driven Change

- この skill は `Research-Driven Change` の inner loop です。
- 外側の仮説更新や次の change 決定は `research-workflow` が扱います。
- この skill は 1 つの protocol と 1 回の run、またはその直後の rewrite / extra validation / rerun 分岐を扱います。

## Boundary

- この repo の実験運用正本は `agents/workflows/experiment-workflow.md` です。
- 実験結果を見ながら code change、調査、チューニングまで含めた loop を回す場合は `adaptive-improvement-loop` を追加します。
- topic の entrypoint と formal command は project-root `experiments/registry.toml` を project-owned 正本にします。AgentCanon source は registry 契約を `documents/experiment-registry.md` で定義します。template / derived repo root からは `vendor/agent-canon/documents/experiment-registry.md` として読みます。
- 新規 topic は最初に実験名を固定し、`python3 tools/experiments/create_experiment_topic.py <topic>` を実行して AgentCanon template path `vendor/agent-canon/experiments/_template/` から project-root `experiments/<topic>/` を作成し、project registry へ topic entry を追加します。
- topic 作成後は `run.py` の `main::main`、`cases.py`、`config.yaml`、`visualize.ipynb`、`README.md` の順で編集します。
- project registry がある場合は、formal 実行前に `python3 tools/ci/check_experiment_registry.py` で registry schema と registered command placeholder を確認します。
- 実験の正本 entrypoint は `/usr/bin/python experiments/<topic>/run.py` のオプションなし直実行です。`run.py` が run directory 作成、設定 snapshot、artifact 書き出し、notebook 実行を所有します。
- 実験設定の checked-in 正本は `experiments/<topic>/config.yaml` に置き、run 時に `config_snapshot.json` などの topic config snapshot として保存します。
- GPU / JAX の実行環境の所有者は scheduler または caller environment とします。実験 topic の code と checked-in config は、GPU visibility、JAX platform、allocator、preallocation などの run ごとの環境割当を埋め込まない形に保ちます。実行環境 contract 自体を変更する task では、`environment-maintenance` と scheduler の正本へ分岐します。
- topic README は、実験内容、問い、比較対象、標準コマンド、設定正本、可視化 notebook、出力 schema、run_name 規則を固定する入口です。
- 非自明な実験 README には、再利用する `python/` 配下の file、class、function を名前で列挙する implementation source map と、各 step が作る object、更新する object、下流へ渡す object、artifact として書く object を追える object-flow 節を置きます。variant 比較では、共通実行 path と、variant が分岐する factory / function 境界を明示します。
- 可視化は `experiments/<topic>/visualize.ipynb` の Jupyter notebook に置き、formal run の起動や設定正本にはしません。
- notebook の各可視化項目は、直前の Markdown cell に日本語で「入力 artifact」「描く量」「読み方」を 1-2 文で説明します。
- 実験 topic を review する段階では `experiment-review` を使い、`run.py` 直実行、GPU/JAX 環境所有、artifact schema、notebook readiness を checklist として確認します。
- 各 run は `result/<run_name>/` を持ちます。追加ログが必要な topic は `result/<run_name>/logs/` に stdout、stderr、startup、tool、diagnostic logs を分けます。
- 標準 run artifact は `summary.json`、`cases.jsonl`、topic config snapshot、case artifacts、`visualize_executed.ipynb` を含みます。これらが無い run は再現性が不足した run として扱い、正式結果には使う前に rerun または明示的な limitation を残します。
- smoke / formal の入口は project `Makefile` に置く場合も、内側では topic `run.py` をオプションなしで呼びます。
- formal run は source checkout、既定では `main` で実行し、run 完了後に
  `save-experiment-results` で retention plan、dirty-source formal-status、
  overwrite policy、branch reason を固定してから
  `python3 tools/experiments/publish_result_branch.py --result-dir experiments/<topic>/result/<run_name> --branch experiment-results/<topic>`
  で結果と report を専用 result branch へ保存します。
- experiment execution surface を変更する task は、patch 前に
  `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>`
  を実行し、`experiment_execution_surface_guard` の handoff を解決します。
  対象 surface は `tools/ci/check_experiment_registry.py`、`documents/experiment-registry.md`、
  `agents/workflows/experiment-workflow.md`、`experiments/registry.toml`、topic
  `run.py` entrypoint です。
  この場合は `test-design` を併用します。project `experiments/registry.toml`
  がある checkout では `python3 tools/ci/check_experiment_registry.py` を実行します。
  runner / registry checker behavior を変える場合は
  `python3 -m pytest tests/tools/test_run_managed_experiment.py -q` で確認します。
  formal experiment run は明示された run plan の実行段階で扱います。
- result / report 生成では `save-experiment-results` と
  `result-artifact-writeout` を使い、raw run output、summary report、manifest、
  unique run_name、overwrite policy、result branch reason、formal-status を分けます。
- experiment plan、rerun plan、result report、HTML view の構造が非自明な場合は、run や report 生成の前に `structure-planning` を使い、first artifact、source-to-structure map、metric contract、invalid interpretation、validation gate を固定します。
- experiment plan / report の structure contract には OOP 観点を入れます。
  再利用する module / class / function / protocol、各 step が作る object、
  変更する object、下流へ渡す object、artifact として書く object、variant が
  差し替わる factory / function 境界、orchestration / domain logic / metric /
  visualization / artifact I/O の依存方向を固定してから section order を書きます。
- experiment plan / report の paragraph order、causal transition、evidence-to-claim transition が非自明な場合は、`structure-planning` 側で `agent-canon semantic-index discourse-relations --profile experiment-report` または `--profile methods-protocol` を使い、discourse edge を構造 evidence として保存します。
- prose graph handoff がある場合は、hypothesis / metric / baseline / expected-result diagnostics を experiment plan または rerun plan の入力にします。
