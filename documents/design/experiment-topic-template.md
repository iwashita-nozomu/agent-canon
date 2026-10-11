<!--
@dependency-start
contract design
responsibility Defines the single-source experiment topic template, materialization route, compact module boundary, and raw/summary run layout.
upstream design ../experiments/experiment-registry.md owns topic identity and registered execution
upstream design ../experiments/result-log-retention-and-visualization.md owns result retention classes
upstream design ./experiment_runner.md owns runner and experiment-side execution responsibilities
downstream implementation ../../tools/experiments/lifecycle/create_experiment_topic.py materializes one topic and registry entry
downstream implementation ../../tools/catalog.yaml exposes the one public creator through typed target-write dispatch
downstream implementation ../../templates/experiments/_template/run.py owns run aggregation and summary publication
downstream implementation ../../templates/experiments/_template/cases.py owns case models and execution
downstream implementation ../../templates/experiments/_template/visualization.py owns visualization status
downstream implementation ../../templates/experiments/_cpp_template/topic.cpp owns the native target extension point
downstream implementation ../../templates/experiments/_cpp_template/run.py owns bounded native launch and raw readback
downstream implementation ../../templates/experiments/_cpp_template/optional/cases.py owns the selected native CaseSpec field model
downstream implementation ../../templates/experiments/_cpp_template/visualization.py owns native raw-output rendering
downstream implementation ../../documents/contracts/template-bundle-manifest.toml exports both package sources
downstream implementation ../../agents/skills/experiment-lifecycle.md exposes topic preparation
downstream implementation ../../tests/tools/test_experiment_template_contracts.py validates materialized behavior
@dependency-end
-->

# Experiment topic template design

## 目的

本設計は、`create_experiment_topic.py` が選択されたcopy sourceからexperiment topicとregistry entryを
materializeする契約を定める。Python profileは既存managed lifecycleへ接続するrunnable scaffoldを生成し、
C++ profileはnative starter packageをdraft状態で生成する。topic固有のalgorithm、metric、visualization内容は
汎用Python scaffoldへ実装しない。

## Target structure

```text
templates/experiments/_template/
├── README.md
├── provenance.toml
├── run.py
├── cases.py
├── visualization.py
├── config.yaml
├── report/
│   └── .gitkeep
└── result/
    └── .gitkeep

templates/experiments/_cpp_template/
├── README.md
├── provenance.toml
├── config.yaml
├── topic.cpp
├── run.py
├── visualization.py
├── cmake/
│   ├── consumer-local.CMakeLists.txt
│   └── root-aggregate.registration.cmake
├── report/
│   └── .gitkeep
└── result/
    └── .gitkeep
```

C++ source packageは`optional/cases.py`も保持する。creatorは`--multi-case`選択時だけこれをtopic rootへ
materializeし、それ以外ではtopicにcase moduleを作らない。

materialized topicは選択profileのCMake entrypointと、選択時だけのcase moduleを含む。
README/provenanceの第二copy source、compatibility copy、symlink、fallback templateは持たない。

既存Python scaffoldは従来通り`cases.py`を含み、managed case lifecycleを所有する。C++ profileは
`topic.cpp`をnative targetにし、`run.py`を実行境界、`visualization.py`をraw output readerに限定する。
固定一件caseでは`cases.py`を作らない。明示的にmulti-caseを選んだ時だけ、既存`CaseSpec` field contract
のinput adapterをmaterializeし、`run.py`がnon-empty case configを列挙して同じC++ targetへ渡す。
Python case workerやempty/example registryは生成しない。starter targetはdraftを維持し、native experimentが
実装されるまで実行失敗を返す。生成だけでscientific resultを宣言しない。

## Clauses

ETC clauses below describe the existing Python scaffold profile. The C++ package
uses the same creator and registry transaction while keeping native execution
inside its selected CMake consumer graph.

| clause | operation | resulting state | completion evidence |
| --- | --- | --- | --- |
| ETC-001 | README/provenanceをrunnable template rootへ統合する | copy sourceが一つになる | old document template absence、dry-run/template inventory |
| ETC-002 | case model、registry、execution/failureを`cases.py`へ統合する | case ownerが一moduleになる | import graph、case success/failure tests |
| ETC-003 | visualization ownerを`visualization.py`一つにする | notebook/module二重入口が消える | old notebook absence、status tests |
| ETC-004 | artifact schema/I/Oを`run.py`、`cases.py`、`visualization.py`へ割り当てる | topic-local artifact framework fileが消える | atomic publication、schema/failure tests |
| ETC-005 | `report/.gitkeep`と`result/.gitkeep`をmaterializeする | report/result rootsがfresh topicに存在する | create topic file inventory |
| ETC-006 | topic-produced artifactを`result/<run-id>/raw`と`summary`へ分離する | 生結果とcompact evidenceが別ownerになる | result tree、manifest/required artifact readback |
| ETC-007 | experiment-lifecycle skillからcreator commandへ直接routeする | skill readerが準備toolへ到達する | public/canonical skill、catalog/tool command check |
| ETC-008 | creator/runner/docs/testsの旧pathを同じ変更で除去する | fallbackやstale consumerが残らない | forbidden-presence scan、focused suite |

## Module responsibility

### `cases.py`

- `CaseSpec`、`CaseResult`とcross-field invariant
- `CASES` registry
- one-case worker extension point
- case execution durationとfailure classification
- JSON-compatible case record projection

case codeはrun-level summary、atomic file publication、visualizationを所有しない。

### `run.py`

- managed runner admission
- run、raw、summary directory resolution
- config/provenance completion readback
- run-level state/summary/manifest type
- atomic text/JSON/JSONL publication
- case orchestrationとrun-level operational state
- summary artifact digest readback

独立`artifact_schema.py`と`artifact_io.py`は作らない。統合後もatomic replacement、typed terminal state、
failure evidence、digest/readbackを維持する。

### `visualization.py`

- visualization requested/not-requested/blocked/success status
- visualization statusのatomic publication
- topic固有rendererのextension point

既定templateはnotebookを生成しない。topicが可視化を必要とする場合はmaterialized
`visualization.py`をtopic内で実装する。

## Run layout

```text
experiments/<topic>/result/<run-id>/
├── raw/
│   └── <topic-produced raw result>
└── summary/
    ├── summary.json
    ├── cases.jsonl
    ├── artifact-manifest.json
    ├── config_snapshot.json
    ├── provenance_snapshot.toml
    ├── environment.json
    ├── visualization-status.json
    └── failure-evidence.json
```

`EXPERIMENT_RUN_DIR`はrun root、`EXPERIMENT_RAW_DIR`は`raw/`、`EXPERIMENT_SUMMARY_DIR`は
`summary/`を指す。topic workerにはraw directoryを渡し、compact aggregateはsummary directoryへ
publishする。managed runnerが所有するroot-level manifest/logはownerのまま維持できるが、topic-produced
artifactをrun rootへ追加しない。

registry/runnerのrequired eval artifactは`summary/summary.json`と`summary/cases.jsonl`を参照する。
旧root-level `summary.json` / `cases.jsonl`はfallbackにしない。

plan の completion は question、observables、evidence targets、protocol、resource、入力・環境条件、
operational stop condition など実行に必要な宣言だけを対象にする。研究上の結果解釈、
案の採否、レビュー判断は topic / research owner の post-run artifact であり、runner の
開始・完了条件ではない。

## Materialization

canonical commandは次である。

```bash
python3 tools/experiments/lifecycle/create_experiment_topic.py <topic>
```

tool-container経由ではcatalog entry `create-experiment-topic`を使い、登録済みparent targetへ
explicit-target-writeします。`template-bundle`の`experiment-scaffold` profileは両方のsource packageを
source-free exportし、topic materializationは既存creatorが所有します。

C++ packageは同じcreatorの選択引数で生成する。CMake profileはconsumer ownerが選び、creatorは
path shapeや既定値から推測しない。

```bash
python3 tools/experiments/lifecycle/create_experiment_topic.py <topic> \
  --template-profile cpp --cmake-profile <root-aggregate|consumer-local>
```

multi-case input adapterが必要な場合だけ`--multi-case`を追加する。生成後の`config.yaml`へ実際のcase
inputsを入れるまでlauncherはfail closedし、空registryやsynthetic caseは生成しない。

Python profileは従来通りregistry `defaults.topic_template_dir`またはcanonical defaultを解決し、single
`copytree`でtopicを作成してREADME/provenance tokenを置換する。別directoryからREADME/provenanceをcopyしない。
C++ profileでは
`templates/experiments/_cpp_template`から共有filesをcopyし、選択されたCMake fragmentだけを
`CMakeLists.txt`または`cmake-registration.cmake`としてmaterializeする。source packageは
`template-bundle-manifest.toml`の`experiment-scaffold` exportにも含める。

creatorはtopic packageと既存registry serializerが作るregistryをprivate staging pathへ準備し、
topicをrenameした後に同じdirectoryでregistryをatomic replaceする。publish failure時は新topicを取り除き、
明示`--force`で退避した既存topicを戻す。既存`--force` authorityとPython default behaviorを保つ。
`--dry-run`は選択profileに応じたtarget file inventoryを表示する。

`root-aggregate`の`cmake-registration.cmake`はroot manifestからincludeできるrequest fileであり、creatorは
project root CMakeLists.txtを変更しない。consumer ownerによるincludeとnative configure/build/runの確認は
このAgentCanon source changeでは主張しない。

## Skill route

```text
.codex/personal/skills/experiment-lifecycle/SKILL.md
  -> agents/skills/experiment-lifecycle.md#Topic Preparation
  -> bootstrap.sh tool run create-experiment-topic -- <topic> [profile selection]
  -> tools/experiments/lifecycle/create_experiment_topic.py
  -> templates/experiments/_template/ or _cpp_template/
  -> experiments/registry.toml
```

catalog/tool command packetはtopic preparation commandをrequired commandとして公開し、skill textだけに
埋め込まれたundiscoverable commandにしない。

## Failure semantics

| failure | result |
| --- | --- |
| selected template file missing | creatorがwrite前にfail |
| topic path exists without `--force`, or registry identity collides | existing target stateを保持してfail |
| topic or `experiments` path is a symlink | creatorがwrite前にfail |
| staged registry publication fails | new topicを取り除き、既存topicとregistryを維持 |
| explicit `--force` publication fails | new topicを取り除き、退避した既存topicとregistryを復元 |
| incomplete config/provenance | summary state=`incomplete`、raw executionなし |
| Python case registry/worker failure | typed failed case、summary failure evidenceを保持 |
| C++ multi-case config is missing, empty, or invalid | case adapterがnative process起動前にfail |
| visualization unavailable/requested | status=`blocked`、run successへ昇格しない |
| summary atomic write/readback failure | old artifactを保持してnon-zero |
| raw/summary path escape | artifact publish前にreject |

## Validation

```text
necessary_presence:
  Python: README.md, provenance.toml, run.py, cases.py, visualization.py,
          config.yaml, report/.gitkeep, result/.gitkeep
  C++ single-case: README.md, provenance.toml, config.yaml, <topic>.cpp,
                   run.py, visualization.py, selected CMake surface, report/.gitkeep,
                   result/.gitkeep; cases.py absent
  C++ multi-case: C++ single-case plus cases.py

forbidden_presence:
  templates/documents/experiment,
  case_model.py, case_execution.py, artifact_schema.py, artifact_io.py,
  visualize.ipynb, root-level topic summary.json/cases.jsonl fallback

sufficient_behavior:
  dry-run profile-specific exact inventory and force replacement readback,
  C++ single-case lacks cases.py and emits one selected CMake surface,
  C++ multi-case requires configured cases and launches the same native target,
  source-free export contains both template packages,
  creator publishes topic and registry together,
  materialized incomplete/success/failure run,
  result/<run-id>/raw and summary readback,
  atomic artifact/checksum tests,
  skill routing command readback
```

Targeted commands:

```bash
python3 -m pytest -q tests/tools/test_experiment_template_contracts.py
python3 -m pytest -q tests/tools/test_run_managed_experiment.py
python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py
```

## Design-to-Implementation Trace

| clause | implementation | reverse evidence |
| --- | --- | --- |
| ETC-001/005/008 | template tree、creator、checker | file inventoryとold path absence |
| ETC-002 | `cases.py` | case model/execution tests |
| ETC-003 | `visualization.py` | status and old notebook absence |
| ETC-004/006 | `run.py` | atomic summary/raw tree tests |
| ETC-007 | public/canonical skill、catalog/tool commands | routing alignment check |
| C++ profile | `_cpp_template/`、creator、template export manifest | selected CMake output、single/multi-case inventory、native launcher boundary |

## DIC status

ETC-001〜ETC-008はowner、target path、state、failure semantics、validationが固定され、implementation-ready
である。C++ profileはconsumer-selected CMake surfaceとsource-free package boundaryを持つ。旧fileを
compatibility import、copy、symlinkとして残す変更、sibling raw path、第二visualization entry、document
template fallbackはdesign driftとしてrejectする。
