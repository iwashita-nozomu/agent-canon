<!--
@dependency-start
contract design
responsibility Defines the single-source experiment topic template, materialization route, compact module boundary, and raw/summary run layout.
upstream design ../experiments/experiment-registry.md owns topic identity and registered execution
upstream design ../experiments/result-log-retention-and-visualization.md owns result retention classes
upstream design ./experiment_runner.md owns runner and experiment-side execution responsibilities
downstream implementation ../../tools/experiments/create_experiment_topic.py materializes one topic and registry entry
downstream implementation ../../templates/experiments/_template/run.py owns run aggregation and summary publication
downstream implementation ../../templates/experiments/_template/cases.py owns case models and execution
downstream implementation ../../templates/experiments/_template/visualization.py owns visualization status
downstream implementation ../../agents/skills/experiment-lifecycle.md exposes topic preparation
downstream test ../../tests/tools/test_experiment_template_contracts.py validates materialized behavior
@dependency-end
-->

# Experiment topic template design

## 目的

本設計は、`create_experiment_topic.py` が一つのcopy sourceからrunnable experiment topicを
materializeし、過分割されていないmoduleとraw/summary分離済みresult layoutを提供する契約を定める。
topic固有のalgorithm、metric、visualization内容はtemplateに実装しない。

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
```

materialized topicも同じrelative structureを持つ。README/provenanceの第二copy source、compatibility
copy、symlink、fallback templateは持たない。

## Clauses

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
- case orchestrationとrun acceptance
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

## Materialization

canonical commandは次である。

```bash
python3 tools/experiments/create_experiment_topic.py <topic>
```

creatorはregistry `defaults.topic_template_dir`またはcanonical defaultを解決し、single `copytree`でtopicを
作成した後、template root内のREADME/provenance tokenだけを置換してregistry entryを追加する。
別directoryからREADME/provenanceをcopyしない。

`--dry-run`はtarget structureのexact file inventoryを表示する。`--force`は既存topic削除を伴うため、
既存destructive authority contractを維持する。

## Skill route

```text
.agents/skills/experiment-lifecycle/SKILL.md
  -> agents/skills/experiment-lifecycle.md#Topic Preparation
  -> python3 tools/experiments/create_experiment_topic.py <topic>
  -> tools/experiments/create_experiment_topic.py
  -> templates/experiments/_template/
  -> experiments/registry.toml
```

catalog/tool command packetはtopic preparation commandをrequired commandとして公開し、skill textだけに
埋め込まれたundiscoverable commandにしない。

## Failure semantics

| failure | result |
| --- | --- |
| template root/README/provenance missing | creatorがwrite前にfail |
| topic/registry identity collision |既存topicとregistryを保持してfail |
| incomplete config/provenance | summary state=`incomplete`、raw executionなし |
| case registry/worker failure | typed failed case、summary failure evidenceを保持 |
| visualization unavailable/requested | status=`blocked`、run successへ昇格しない |
| summary atomic write/readback failure | old artifactを保持してnon-zero |
| raw/summary path escape | artifact publish前にreject |

## Validation

```text
necessary_presence:
  README.md, provenance.toml, run.py, cases.py, visualization.py,
  config.yaml, report/.gitkeep, result/.gitkeep

forbidden_presence:
  templates/documents/experiment,
  case_model.py, case_execution.py, artifact_schema.py, artifact_io.py,
  visualize.ipynb, root-level topic summary.json/cases.jsonl fallback

sufficient_behavior:
  dry-run exact inventory,
  materialized incomplete/success/failure run,
  result/<run-id>/raw and summary readback,
  atomic artifact/checksum tests,
  skill routing command readback
```

Targeted commands:

```bash
python3 -m pytest -q tests/tools/test_experiment_template_contracts.py
python3 -m pytest -q tests/tools/test_run_managed_experiment.py
python3 -m pytest -q tests/tools/test_check_experiment_template.py
python3 tools/agent_tools/check_agent_runtime_alignment.py
python3 tools/agent_tools/check_dependency_headers.py --changed
```

## Design-to-Implementation Trace

| clause | implementation | reverse evidence |
| --- | --- | --- |
| ETC-001/005/008 | template tree、creator、checker | file inventoryとold path absence |
| ETC-002 | `cases.py` | case model/execution tests |
| ETC-003 | `visualization.py` | status and old notebook absence |
| ETC-004/006 | `run.py` | atomic summary/raw tree tests |
| ETC-007 | public/canonical skill、catalog/tool commands | routing alignment check |

## DIC status

ETC-001〜ETC-008はowner、target path、state、failure semantics、validationが固定され、implementation-ready
である。旧fileをcompatibility import、copy、symlinkとして残す変更、sibling raw path、第二visualization
entry、document template fallbackはdesign driftとしてrejectする。
