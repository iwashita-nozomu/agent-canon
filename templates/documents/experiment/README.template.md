<!--
@dependency-start
contract template
responsibility Provides the canonical planning and provenance README for an experiment topic.
upstream design ../../../documents/experiments/README.md experiment directory and registry route.
upstream design ../../../documents/design/experiment_runner.md managed experiment execution contract.
downstream implementation ../../../templates/experiments/_template/run.py provides the runnable topic scaffold.
downstream implementation ./experiment-provenance.template.toml records machine-readable plan and provenance.
downstream implementation ../../../tools/experiments/create_experiment_topic.py creates a topic and places this README/provenance pair.
@dependency-end
-->

# <Experiment topic>

この template は、experiment の計画、資源選定、実行・結果 provenance、失敗結果、
再現性を一つの reader path にまとめる正本雛形です。実験コードの runnable scaffold は
`templates/experiments/_template/` を再利用し、この文書はその topic の判断と証跡を所有します。

## Reader Map

この README は、experiment の question → algorithm/variant → case/oracle → resource/env →
managed run → result/failure → interpretation → retention/cleanup の順で読みます。

- purpose: 実験の判断と再現可能な証拠を一つの topic contract に固定する。
- intended reader and decision: 実験設計者、実行担当者、reviewer、保守者。
- what this document contains: plan、複数案、algorithm contract、必要十分 oracle、resource/env/result provenance、failure semantics。
- canonical source / generated surface: この README と `provenance.toml` が topic source、`result/<variant>/<run-id>/` は run-local result。
- owner boundary: orchestration、case model/execution、metrics、visualization、artifact schema/I/O の OOP/type 境界を分ける。
- implementation map: `run.py` は入口、`case_model.py` は CaseSpec/CaseResult、`case_execution.py` は worker/failure、`artifact_schema.py` は schema、`artifact_io.py` は atomic publication/manifest、`visualization.py` は notebook consumer を所有する。
- required readback: managed command、config snapshot、resource admission、result manifest、docs formatter/readback。
- lifecycle: result retention、cleanup owner、再構築可能性を closeout 前に確認する。

## 責務

- 仮説・比較対象・受入条件を実行前に固定する。
- machine-readable TOML と run/result artifact の provenance を対応付ける。
- GPU/resource の選定理由、失敗結果の受理、再現手順を残す。
- 成功結果だけでなく、契約に照らして受理した失敗結果を明示する。

## 読者 map

- **実験設計者**: 仮説、case、resource、停止条件を確認する。
- **実行担当者**: caller/scheduler が選んだ resource と command を再現する。
- **reviewer**: provenance、failure semantics、受入 oracle、比較の妥当性を判断する。
- **保守者**: topic scaffold、registry、result retention の境界を更新する。

## 含む内容

計画、仮説、case、評価指標、resource/GPU 選定、実行 command、config snapshot、
run/result provenance、失敗結果の受理条件、再現性、artifact retention、受入条件を
含めます。GPUの固定番号、serial throttle、成功だけを要求する後付け条件は含めません。

## Files

- `README.md`: この canonical template から作成される topic の reader-facing contract。
- `provenance.toml`: README と同じ計画、選択、resource、run、result identity を記録する machine-readable provenance。
- `run.py`: managed runner の child から呼ばれる topic entrypoint。`main()` が run artifact を生成する。
- `cases.py`: topic の case 定義。
- `case_model.py`: CaseSpec、CaseResult、terminal state と success/failure cross-field invariant。
- `case_execution.py`: replaceable case worker、duration、failure-cause classification。
- `artifact_schema.py`: RunSummary、ArtifactManifest、completion provenance の型境界。
- `artifact_io.py`: config/provenance snapshot、atomic JSON/JSONL、nested artifact digest readback。
- `visualization.py`: optional notebook consumer と visualization status artifact。
- `config.yaml`: checked-in topic設定の正本。
- `visualize.ipynb`: run artifactを読む可視化 notebook。
- `result/`: `result/<variant>/<run_name>/` ごとの run artifact とログ。

## Scaffold structure

```text
experiments/<topic>/
├── README.md
├── provenance.toml
├── run.py
├── cases.py
├── case_model.py
├── case_execution.py
├── artifact_schema.py
├── artifact_io.py
├── visualization.py
├── config.yaml
├── visualize.ipynb
└── result/
    └── <run_name>/
        ├── summary.json
        ├── cases.jsonl
        ├── config_snapshot.json
        ├── provenance_snapshot.toml
        ├── environment.json
        ├── artifact-manifest.json
        ├── visualization-status.json
        ├── failure-evidence.json (failed/blocked 時)
        └── logs/
```

`create_experiment_topic.py` は runnable scaffold と責務別の5 moduleを
`templates/experiments/_template/` からコピーし、
この canonical template の README と provenance TOML を同じ topicへ配置します。したがって、
作成された topic の `README.md` だけで、Files、構造、managed実行、artifact、実装位置を
再構築できます。

## Create Topic

最初に実験名 `<topic>` を固定し、次の tool を実行します。registry entry と
`README.md` / `provenance.toml` を同じ生成routeで作成します。

```bash
python3 -m tools.experiments.create_experiment_topic <topic>
```

topic作成後の編集順は `run.py`、`cases.py`、`config.yaml`、`visualize.ipynb`、
`README.md`、`provenance.toml` です。実験コードの runnable owner は
`templates/experiments/_template/` とその生成先topicであり、この文書はそのreader-facing contractを所有します。

## Plan

- topic:
- question / hypothesis:
- baseline and candidate:
- case matrix:
- metrics and oracle:
- stopping rule:
- expected result and decision rule:
- non-goals:

## Algorithm contract before tests

実験の期待値や test を先に作らず、対象 algorithm の public entrypoint、入力、state transition/
recurrence、invariants、stopping/acceptance rule、typed failure を先に固定します。

- algorithm / variant contract:
- state transition or recurrence:
- invariants and preconditions:
- stopping / acceptance rule:
- implementation mechanism and selected responsibility unit:
- necessary-and-sufficient oracle:
- test activation condition and static-only boundary:

## OOP and C++ boundary

実験の orchestration、domain logic、metrics、visualization、artifact I/O は独立した責務として
記録し、variant の差分は factory/function boundary に閉じます。C++ の experiment/test は
topic 内の一つの single-project boundary として扱い、必要な `CMakeLists.txt` はその topic
直下だけに置きます。template root に top-level CMake を要求せず、他の topic・親repoの build
system・共有 header を勝手に取り込みません。

## Options and selection

候補を一つだけ書いて後付けで正当化しません。少なくとも実行可能な複数案を比較し、
selected option、rejected rationale、selection evidence を同じ判断記録に残します。

| option | mechanism / cost | expected evidence | status |
| --- | --- | --- | --- |
| A: `<option-a>` | `<mechanism-and-cost>` | `<evidence-needed>` | selected / rejected |
| B: `<option-b>` | `<mechanism-and-cost>` | `<evidence-needed>` | selected / rejected |
| C: `<option-c>` | `<mechanism-and-cost>` | `<evidence-needed>` | selected / rejected |

- selected option:
- rejected rationale:
- selection evidence:
- unresolved choice and decision owner:
- independent reviewer:
- independent review evidence and source snapshot:

## Machine-readable contract

対応する TOML は [`experiment-provenance.template.toml`](experiment-provenance.template.toml)
を使い、README の記述と同じ topic / commit / config / resource / run / result identity
を持たせます。

- plan digest:
- config path and snapshot:
- source commit / dirty state:
- runner command:
- result directory:
- selected option / selection evidence:
- rejected rationale:

## Conflict intent and failure-cause classification

- conflict intent / preserved user or design intent:
- unresolved conflict owner and escalation route:

| cause class | observed evidence | result state | accepted reason / close condition |
| --- | --- | --- | --- |
| expected contract failure | `<evidence>` | failed / accepted | `<reason>` |
| infrastructure / environment | `<evidence>` | blocked / failed | `<owner-and-close-condition>` |
| implementation / algorithm | `<evidence>` | failed | `<repair-and-regression>` |
| oracle / specification | `<evidence>` | blocked | `<design-adjudication>` |
| unknown | `<evidence>` | blocked | `<investigation>` |

## Resource and GPU selection

- resource request:
- scheduler / caller:
- capability evidence:
- GPU selection reason:
- visibility and parallelism policy:
- environment limit or serial-debug reason, if any:

topic code と checked-in config は GPU番号、`CUDA_VISIBLE_DEVICES`、単一GPU制限、
serial worker 数を固定しません。実行時の割当は caller または scheduler の provenance
として記録します。

## Run and result provenance

| record | required identity |
| --- | --- |
| plan | topic, plan digest, owner, created-at |
| source | repository, branch, commit, dirty-state |
| environment | runner, host/container, Python/runtime, resource allocation |
| input | config path, config snapshot, cases, seed policy |
| run | command, start/end, run id, exit status |
| result | result path, summary, artifact manifest, validation status |

result state は `incomplete` / `success` / `failed` / `blocked` の構造化値として記録します。
`failure_evidence`、`accepted_failure_reason`、`preserved_artifacts`、`close_condition`、
`validation_oracle` は、成功・失敗・blocked のいずれでも省略しません。

各 run は `result/<variant>/<run-id>/` に immutable な snapshot と manifest を保存し、README の
provenance tableから追跡できるようにします。

## Run Contract

topic `run.py` を直接起動せず、必ず managed runner を入口にします。runnerの実コードが
受け取る `--topic` と `--` 後の remainder command、および exact topic entrypoint / Python
判定に合わせた正式な手動commandは次のとおりです。

```bash
python3 -m tools.experiments.run_managed_experiment \
  --topic <topic> \
  --variant formal \
  -- \
  python3 experiments/<topic>/run.py
```

- runnerは `--` 以降を inner command として選択し、`python3 experiments/<topic>/run.py` が
  canonical entrypointであることを確認する。
- runnerが `EXPERIMENT_RUN_DIR`、`EXPERIMENT_RUN_MANIFEST`、config snapshot、command/environment/source
  manifest、stdout/stderr/startup logをmanaged childへ渡し、topic `main()` は引数なしで実行する。
- topic `run.py` は `result/<variant>/<run_name>/` を作成し、少なくとも `summary.json`、`cases.jsonl`、
  `config_snapshot.json`、`environment.json`、`artifact-manifest.json`、
  `visualization-status.json`、topic-specific artifact、必要な `logs/` を atomic に書き出す。
  失敗または空 case では `failure-evidence.json` も保存する。notebookはmanaged childのrun
  flowから artifactを読み、formal runの別のentrypointにはしない。
- `config.yaml` はchecked-in設定の正本であり、run時の割当・snapshot・command identityは
  runnerのprovenanceへ記録する。

最小 scaffold には `cases.py` の `example` case が一つありますが、`config.yaml` と
`provenance.toml` は `template_complete=false` / `completion_status="incomplete"` です。
required fields と completion provenance が満たされるまでは run は `incomplete`、case は実行せず、
成功結果を名乗りません。materialization smoke はこの incomplete fixture/state を先に検証し、
completion fixture を埋めた代表 run だけが success になります。case record は `case_id`、
`state`、`result`、`failure_class`、時刻、duration を必ず持ちます。case が空なら run は
`blocked`、case failure なら `failed` とし、成功 record だけを残して failure を隠しません。
`EXPERIMENT_RUN_VISUALIZATION=1` を指定しない場合、visualization は
`visualization-status.json` に `not_requested` と記録され、Jupyter を必須にしません。
completion field と placeholder/未解決 marker の registry は `artifact_schema.py` が一つだけ
所有し、gate は `config.yaml` を YAML として parse した後、config/provenance の mapping、list、
scalar を再帰走査します。malformed YAML、TOML、nested reviewer の `<...>`、`IMPLEMENT HERE`
などが残れば reject し、fixture も全 token の一括置換ではなく semantic field を個別に materialize
して検証します。さらに `plan.options` は2案以上と各選択理由/evidence、`plan.selection` は
選択結果と却下理由/evidence、`review` は reviewer、source snapshot、selection evidence、
decision を必須とします。

## Implementation Markers

- `run.py` のtop-level importは `from __future__ import annotations`、標準 library、軽量な local
  module (`artifact_io.py`、`artifact_schema.py`、`case_execution.py`、`case_model.py`、
  `visualization.py`) に限定する。`cases.py` は completion gate 通過後の `load_cases()` 内で
  lazy import し、重い project dependency を top-level に置かない。
- `run.py` の `main()` は引数なしで固定し、`argparse` などのtopic CLIを追加しない。
- `template_complete=false`、placeholder、または completion provenance 不足を成功へ変える
  production bypass flag は設けない。
- JAX、CUDA、NumPy、EQX、Optax、project moduleなどの重い実験依存importは、利用者が追加する
  `run_case_worker()` の内部または notebook の実行 cell に置き、`run.py` の top-level importへ
  引き上げない。
- `IMPLEMENT HERE` marker は現在 `config.yaml` の completion/config field と
  `visualize.ipynb` の artifact reader/figure cell にだけあります。`run.py` と `cases.py` に
  markerを追加せず、case registry は `cases.py` の `CASES`、domain algorithm は
  `case_execution.py` の `run_case_worker()`、schema/readback は5 moduleの各 ownerへ実装します。
- `run.py` は execution entrypoint/orchestration に限定し、上記5 moduleの責務を重複実装しない。
- artifact manifest は run directory 内の nested regular file 全件を normalized relative path と
  SHA-256 で readback する。CaseResult の terminal state invariant を publication 前に通す。
- `ArtifactManifest` と `RunSummary` は `RunState` enum、`exit_status`、`template_complete`、
  `completion_provenance`、required readback artifact の cross-field invariant を publication
  前に検証する。JSON へ出すときだけ enum の `.value` を使う。
- GPU visibility、JAX platform、allocator、preallocation、serial worker数はtopic code / checked-in
  configへ埋め込まない。GPU/resource admissionと実行環境はmanaged runnerおよびcaller/schedulerの
  owner boundaryで決め、provenanceへ記録する。

### Local responsibility imports and extension points

各 module の local responsibility import と、利用者が追加する重い project dependency を
分けます。軽量な local import は責務境界を接続しますが、JAX、CUDA、NumPy、EQX、Optax、
project-specific package などの重い dependency は `run_case_worker()` または notebook の
実行経路へ遅延させます。次の5 moduleが extension point と implementation trace の正本です。

| module | local responsibility import | heavy project dependency boundary | extension point / implementation trace |
| --- | --- | --- | --- |
| `case_model.py` | 標準 library の dataclass、JSON、数値検証 | なし。domain object は受け取らない | `CaseSpec` と `CaseResult` が input、terminal state、cross-field invariant を所有する |
| `case_execution.py` | `case_model.py` と `artifact_io.py` | `run_case_worker()` 内だけに domain algorithm と重い dependency を置く | `run_case_worker()` が一 case の algorithm seam、`execute_case()` が failure record trace を所有する |
| `artifact_schema.py` | 標準 library の enum、型、schema helper | なし。serialization は import しない | `RunState`、completion registry、`ArtifactManifest`、`RunSummary` が publication contract を所有する |
| `artifact_io.py` | `artifact_schema.py`、`case_model.py`、YAML/TOML parser | project runtime や device dependency は持たない | YAML/TOML completion gate、atomic writer、nested digest readback を実装する |
| `visualization.py` | `artifact_io.py` と標準 library | Jupyter は `EXPERIMENT_RUN_VISUALIZATION=1` の実行時だけ要求する | visualization status と notebook consumer の readback を実装し、run の success gateとは分離する |

`run.py` はこの5 moduleを呼ぶ execution entrypoint/orchestrator に留めます。利用者が
domain algorithm、追加 artifact、重い runtime を実装するときは、対応する extension point の
contract、provenance、failure semantics、readback evidence を更新し、同じ責務を `run.py` に
複製しません。

## Result state and failure results are evidence

`template_complete = false` または必須 placeholder が残る間は `incomplete` であり、
成功結果として閉じません。成功と失敗は相互排他的です。成功は exit status、
`validation_oracle`、受入条件が pass したときだけ許可し、失敗は観測可能な
`failure_evidence` と `preserved_artifacts` を保持したときだけ `failed` として受理します。
再現・原因調査待ちは `blocked` とし、`accepted_failure_reason` と `close_condition` が
未確定なら完了扱いにしません。

- failed run id:
- observed failure and exit status:
- failure class: expected / infrastructure / implementation / oracle / unknown:
- result state: incomplete / success / failed / blocked:
- failure_evidence:
- accepted_failure_reason: 成功ではない結果を受理する根拠、または `none`:
- preserved logs and partial artifacts:
- preserved_artifacts:
- why the failure is accepted as a result:
- what it rules out or changes:
- follow-up owner and close condition:
- validation_oracle:

失敗を隠して再実行を成功結果だけに置き換えません。受理できない failure は
`status=blocked` として保持し、再現または原因調査が完了するまで結論を出しません。

## Reproduction

再現時は `Run Contract` の managed commandを使い、clean checkout、exact config snapshot、
caller/schedulerのresource admission、run name、artifact readbackをprovenance TOMLへ
記録します。managed runner以外の起動経路を再現手順として記載しません。

- clean checkout / submodule state:
- exact config snapshot:
- resource admission record:
- command and expected exit status:
- artifact readback command:
- deterministic seed / nondeterminism note:
- environment snapshot and versions:
- result manifest / digest readback:

## Acceptance and retention

- acceptance oracle:
- required validation:
- accepted failure condition:
- success condition: exit status、validation oracle、acceptance がすべて pass
- failure condition: failure evidence、preserved artifacts、accepted reason、close condition がそろう
- result retention path and cleanup owner:
- reviewer decision: pass / revise / reject:
- close condition:

## Formatter and lifecycle closeout

- Markdown/math/Mermaid check: `tools/bin/agent-canon docs check <README.md>`
- TOML parse/readback: `python3 -c 'import pathlib,tomllib; tomllib.loads(pathlib.Path("provenance.toml").read_text())'`
- formatter/fixer used:
- post-format source and rendered readback:
- result cleanup command and owner:
- reconstructibility proof after cleanup:
