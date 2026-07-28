<!--
@dependency-start
contract template
responsibility Provides the canonical planning and provenance README for an experiment topic.
upstream design ../../experiments/README.md experiment directory and registry route.
upstream design ../../design/experiment_runner.md managed experiment execution contract.
downstream implementation ../../../experiments/_template/run.py provides the runnable topic scaffold.
downstream implementation ./experiment-provenance.template.toml records machine-readable plan and provenance.
downstream implementation ../../../tools/experiments/create_experiment_topic.py creates a topic and places this README/provenance pair.
@dependency-end
-->

# <Experiment topic>

この template は、experiment の計画、資源選定、実行・結果 provenance、失敗結果、
再現性を一つの reader path にまとめる正本雛形です。実験コードの runnable scaffold は
`experiments/_template/` を再利用し、この文書はその topic の判断と証跡を所有します。

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
- `config.yaml`: checked-in topic設定の正本。
- `visualize.ipynb`: run artifactを読む可視化 notebook。
- `result/`: `result/<run_name>/` ごとの run artifact とログ。

## Scaffold structure

```text
experiments/<topic>/
├── README.md
├── provenance.toml
├── run.py
├── cases.py
├── config.yaml
├── visualize.ipynb
└── result/
    └── <run_name>/
        ├── summary.json
        ├── cases.jsonl
        ├── config_snapshot.json
        └── logs/
```

`create_experiment_topic.py` は runnable scaffold を `experiments/_template/` からコピーし、
この canonical template の README と provenance TOML を同じ topicへ配置します。したがって、
作成された topic の `README.md` だけで、Files、構造、managed実行、artifact、実装位置を
再構築できます。

## Create Topic

最初に実験名 `<topic>` を固定し、次の tool を実行します。registry entry と
`README.md` / `provenance.toml` を同じ生成routeで作成します。

```bash
python3 tools/experiments/create_experiment_topic.py <topic>
```

topic作成後の編集順は `run.py`、`cases.py`、`config.yaml`、`visualize.ipynb`、
`README.md`、`provenance.toml` です。実験コードの runnable owner は
`experiments/_template/` とその生成先topicであり、この文書はそのreader-facing contractを所有します。

## Plan

- topic:
- question / hypothesis:
- baseline and candidate:
- case matrix:
- metrics and oracle:
- stopping rule:
- expected result and decision rule:
- non-goals:

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

各 run は `result/<run-id>/` に immutable な snapshot と manifest を保存し、README の
provenance tableから追跡できるようにします。

## Run Contract

topic `run.py` を直接起動せず、必ず managed runner を入口にします。runnerの実コードが
受け取る `--topic` と `--` 後の remainder command、および exact topic entrypoint / Python
判定に合わせた正式な手動commandは次のとおりです。

```bash
python3 tools/experiments/run_managed_experiment.py \
  --topic <topic> \
  --variant formal \
  -- \
  python3 experiments/<topic>/run.py
```

- runnerは `--` 以降を inner command として選択し、`python3 experiments/<topic>/run.py` が
  canonical entrypointであることを確認する。
- runnerが `EXPERIMENT_RUN_DIR`、`EXPERIMENT_RUN_MANIFEST`、config snapshot、command/environment/source
  manifest、stdout/stderr/startup logをmanaged childへ渡し、topic `main()` は引数なしで実行する。
- topic `run.py` は `result/<run_name>/` を作成し、少なくとも `summary.json`、`cases.jsonl`、
  topic-specific artifact、必要な `logs/` を書き出す。notebookはmanaged childのrun flowから
  artifactを読み、formal runの別のentrypointにはしない。
- `config.yaml` はchecked-in設定の正本であり、run時の割当・snapshot・command identityは
  runnerのprovenanceへ記録する。

## Implementation Markers

- `run.py` のtop-level importは `from __future__ import annotations` と軽量な定数・標準libraryに限定する。
- `run.py` の `main()` は引数なしで固定し、`argparse` などのtopic CLIを追加しない。
- JAX、CUDA、NumPy、EQX、Optax、project moduleなどの実験依存importは、`run_experiment()` または
  `run_case_worker()` の内部へ置く。
- 実験の実装箇所は `run.py`、`cases.py`、`config.yaml`、`visualize.ipynb` の `IMPLEMENT HERE`
  markerで明示する。
- GPU visibility、JAX platform、allocator、preallocation、serial worker数はtopic code / checked-in
  configへ埋め込まない。GPU/resource admissionと実行環境はmanaged runnerおよびcaller/schedulerの
  owner boundaryで決め、provenanceへ記録する。

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

## Acceptance and retention

- acceptance oracle:
- required validation:
- accepted failure condition:
- success condition: exit status、validation oracle、acceptance がすべて pass
- failure condition: failure evidence、preserved artifacts、accepted reason、close condition がそろう
- result retention path and cleanup owner:
- reviewer decision: pass / revise / reject:
- close condition:
