<!--
@dependency-start
contract reference
responsibility Indexes AgentCanon-owned template sources and the one-way static consumer export boundary.
upstream design ../documents/contracts/static-seed-export.md static seed allowlist, provenance, and exclusion contract
upstream design ../documents/rule/README.md document filename, placement, and language rules
upstream design ../documents/conventions/DOCSTRING_GUIDE.md semantic Docstring clauses and projection traces
downstream implementation ./agents/README.md reusable agent artifact template source
downstream implementation ./documents/README.md reader-facing document template source
downstream implementation ./code/README.md materializable code and Docstring template source
downstream implementation ./experiments/_template/run.py runnable experiment scaffold source
downstream implementation ../tools/agent_tools/export_static_seed.py produces the exact default-consumer seed
downstream implementation ../tools/agent_tools/code_template_rendering.py renders AgentCanon-internal code templates
downstream implementation ../tools/agent_tools/agent_team.py renders AgentCanon-internal agent templates
downstream implementation ../tools/experiments/create_experiment_topic.py copies AgentCanon-internal experiment templates
@dependency-end
-->

# Centralized Templates

この directory は、AgentCanon source repository 内で保守する template の唯一の owner です。
ただし、default template/derived consumer がこの source tree を runtime に参照することはありません。
consumer へ渡す default surface は
[Static Seed Export Contract](../documents/contracts/static-seed-export.md) の exact allowlist から生成した
regular file と最小 provenance だけです。

## Reader Map

- AgentCanon maintainer: source template をこの directory で編集し、source-owned checker を実行する。
- Default consumer maintainer: committed source commit から static seed を one-way export し、通常 file として review する。
- Default consumer/runtime: 取り込まれた file を直接所有し、AgentCanon source、resolver、updater、同期状態を参照しない。
- Live integration adopter: default とは別に explicit opt-in runtime contract を選ぶ。

## Source-view index

Profile path ownership is defined by
`documents/contracts/template-bundle-manifest.toml`. The exporter writes only
to a fresh external directory and records the source commit and bundle digest.

| Source view | Responsibility | Materialization rule |
| --- | --- | --- |
| `templates/agents/` | task-start、run bundle、review、closeout の artifact template | AgentCanon source 内で agent team が render する |
| `templates/documents/` | README、design、experiment、host、remote execution、GitHub source | standalone AgentCanon target と source を同時に更新する |
| `templates/code/` | parse-valid module/class/function と Docstring の materializable source | source-owned renderer が destination owner へ materialize する |
| `templates/experiments/_template/` | runnable experiment scaffold の frozen source | source-owned experiment command が新規 topic へ copy する |
| `templates/agents/_partials/` | reader map、review contract、finding/decision の再利用部品 | top-level agent artifact の render 時だけ展開する |

## Default Consumer Export Boundary

Default consumer に供給する file set は
`documents/contracts/static-seed-allowlist.toml` の exact path 列だけです。現在の seed は
`.codex/config.toml` と `.codex/agents/<role>.toml` を含み、出力時に
`agent-canon-static-seed.json` を加えます。

次は default consumer へ配布しません。

- AgentCanon の template source directory
- source resolver、dispatcher、updater、latest checker
- runtime projection、transaction state、sync state
- tests、notes、memory、evidence、reports、issues
- source checkout secret、URL、network command
- symlink、gitlink、source mirror、代替 package

export は一つの committed source snapshot から実行する maintainer-owned one-way operation です。
取り込み後の regular file は consumer repository が所有します。consumer CI、bootstrap、product image、
background task は再生成や上流探索を行いません。

## Experiment Copy Boundary

`create_experiment_topic.py` は AgentCanon source 内で
`templates/experiments/_template/` を唯一の copy source として読み、生成先だけを
`experiments/<topic>/` に書き込みます。この source-owned operation は default consumer の
bootstrap/runtime surface ではありません。

managed runner の実行入口は常に生成後の `experiments/<topic>/run.py` です。`run.py` は
orchestration、run schema、atomic publication を担当します。`cases.py` が case model・registry・
worker・failure classification、`visualization.py` が topic renderer extension point を所有します。
topic-produced outputs are divided between `result/<run-id>/raw/` and `result/<run-id>/summary/`.

## Consumer Migration Packet

Default consumer を static seed と composed root instruction へ切り替える変更は、次を同じ
migration packet に記録します。

- producer commit と allowlist から seed を一度 export する。
- provenance と全 output が regular file であることを確認する。
- consumer が必要とする seed file だけを tracked content として取り込む。
- 旧 source checkout、runtime projection、update/sync state、runtime-only workflow を削除する。
- consumer-owned project config、実 topic、product tests、Docker/CI surface を保持する。
- source checkout を不可視化した fixture で bootstrap と canonical project checks を実行する。
- static seed の再生成を consumer setup、CI、runtime へ追加しない。
- `ROOT_AGENTS.md` を共通 base、`documents/agent-canon/consumer-root-instructions.md` を
  consumer-specific source とし、consumer root `AGENTS.md` は明示 composer の regular output とする。
- composition output に source checkout、symlink、vendor、submodule、singular `AGENT.md` を追加しない。

Migration order は AgentCanon static consumer contract、consumer tree ownership、canonical command、
fresh-clone bootstrap の順です。互換 wrapper や dangling link を中間状態として残しません。

## Docstring Projection

Template Docstring の semantic owner は
[Docstring Semantic Contract](../documents/conventions/DOCSTRING_GUIDE.md) です。各 source consumer は
responsibility region と selected semantic delta だけを記録し、固定 section や signature、type、
namespace、field の事実を繰り返しません。

`templates/documents/semantic-responsibility-contract.template.toml` は空の instance shape を提供します。
値を埋めた semantic responsibility contract は run-local artifact として active design packet から参照し、
template source へ戻しません。

## Required Document and Artifact Fields

各 template の利用者は、必要性を判断できる最小の field を埋めます。reader map は文書の冒頭に置き、
設計・実装・review・experiment・PR の選択がある場合は次を相互参照します。

- owner / responsibility と OOP/type boundary
- design-to-implementation trace と dependency / side-effect map
- tests より前の algorithm contract
- necessary-and-sufficient oracle/test boundary
- failure-cause classification、accepted failure、conflict intent
- 複数の viable alternatives と独立 reviewer / selection evidence
- Markdown/math/Mermaid formatter、post-format readback、targeted validation
- artifact retention、再構築、lifecycle cleanup owner

Markdown の整形・数式・Mermaid は source repository の canonical docs checker を使い、formatter/fixer
後は同じ source path を read back します。examples は適応可能な placeholder にし、単一 repository の
path、GPU 番号、serial throttle、固有 API を template の意味として固定しません。
