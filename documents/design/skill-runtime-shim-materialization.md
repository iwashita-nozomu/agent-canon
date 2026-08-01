<!--
@dependency-start
contract design
responsibility Defines the single schema and materializer for the catalog-defined public Codex runtime skill shims.
upstream design ../rule/README.md document naming and Japanese-content rule
upstream design ./README.md design-canon reader route
upstream design ../../agents/skills/catalog.yaml public skill identity, discovery metadata, and command owner
upstream design ../../agents/skills/skill-dependencies.yaml typed prerequisite, successor, order, routing-candidate, and parallel relations
upstream design ../../agents/canonical/skills.md public skill reader/index boundary
upstream design ./skill-tool-invocation-graph.md skill/tool identity, graph projection, and readback contract
upstream design ../../documents/codex/prompt-skill-evaluation-checklist.md fresh evaluator and report contract
downstream implementation ../../tools/agent_tools/skill_tool_commands.py read-only command packet producer
downstream implementation ../../tools/agent_tools/route.py deterministic catalog-backed route consumer
downstream implementation ../../tools/agent_tools/skill_dependency_map.py graph materializer and semantic golden producer
downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py host-discovery and catalog/shim parity checker
downstream implementation ../../tools/agent_tools/check_skill_frontmatter.py frontmatter readback checker
downstream implementation ../../tools/agent_tools/check_skill_tool_invocation_graph.py graph projection readback checker
downstream implementation ../../tools/agent_tools/evaluate_skill_workflow_prompts.py prompt checklist evaluator
@dependency-end
-->

# Skill Runtime Shim Materialization

## Reader Map

この設計は、AgentCanon の catalog-defined public skill について、Codex host が発見する
.agents/skills/*/SKILL.md を一つの schema と一つの materializer から生成する
target state を定めます。実装者は先に「正本と adapter の境界」「生成 record の
field order」「移行/readback」を読み、その後に graph/route golden と
gpt-5.4-mini 評価を確認します。skill の本文は個別の
agents/skills/<skill>.md が所有し、この文書は本文の複製ではありません。

## Decision Summary

現在の public skill identity は agents/skills/catalog.yaml の全 `skill_families` 行、依存関係は
agents/skills/skill-dependencies.yaml、読者向け索引は
agents/canonical/skills.md、host discovery は .codex/config.toml の
[[skills.config]] と .agents/skills/<skill>/SKILL.md が所有します。

Wave 4 の target state は次です。

- agents/skills/<skill>.md は唯一の canonical prose owner とする。
- agents/skills/catalog.yaml は id、host discovery metadata、command、route
  identity の唯一の machine source とする。既存の purpose、routing、
  tool_commands、visualization fields は削除・再解釈しない。
- agents/skills/skill-dependencies.yaml の relation は唯一の dependency source
  とする。shim に relation の配列や routing policy を写さない。
- .agents/skills/<skill>/SKILL.md は frontmatter、owner link、source identity、
  ToolCall command packet の薄い adapter_only projection とする。
- catalog の全 public skill を同じ schema、同じ template、同じ materializer で生成する。
  skill_tool_commands.py は read-only の command-packet producer として残すが、
  sync サブコマンド、sync facade、旧 writer の互換概念は target state に存在しない。
  SKILL.md の唯一の writer は materializer である。
- shim 側には routing 実装を置かない。prompt の keyword、description の単語、
  近接 filename、shim の prose は capability、workflow、ToolCall を選ぶ authority
  ではない。全体 route.py は既存の catalog/dependency の route owner として、
  catalog の既存の route identity を入力に決定論的な route output を作る。この
  Wave は triggers を追加・複製・再解釈しない。したがって「keyword routing を
  廃止する」は shim prose からの keyword matcher/classifier を廃止する、という
  所有境界であり、route.py の既存 owner data を別の shim route に置き換えること
  ではない。

この設計では実装、shim の書き換え、catalog の更新、graph artifact の再生成、
commit を行わない。

## Scope and Non-Goals

### Scope

対象は catalog.yaml の全 public skill と、対応する全 generated target です。

~~~text
.agents/skills/<skill>/SKILL.md
~~~

host の path は現在どおり ../.agents/skills/<skill>/SKILL.md とします。
`.codex/config.toml` は host-wiring の source/input であり、materializer の生成 target
ではありません。materializer は `.agents/skills/<skill>/SKILL.md` だけを生成し、config
entry の catalog-derived set、source order、path、enabled を readback します。

### Non-Goals

- canonical skill の policy、numbered rules、例、proof、workflow prose を shim に
  再掲すること。
- routing.triggers を新しい keyword matcher、classifier、shim-side policy に
  変えること。
- skill-dependencies.yaml、route.py、graph の identity を shim から再構築する
  こと。
- third-party vendor/skills adapter の symlink 契約を public skill shim に
  流用すること。
- この Wave で model、host config、public skill id、ToolID、argument schema を
  変更すること。

## Responsibility Boundaries

| 判断 | 正本 | shim が持つもの | shim が持たないもの |
| --- | --- | --- | --- |
| skill identity / purpose | agents/skills/catalog.yaml | skill_id への参照 | 別の skill 一覧 |
| host discovery | frontmatter と .codex/config.toml | name、description | host config の再定義 |
| canonical prose | agents/skills/<skill>.md | 相対 link と digest | canonical rules のコピー |
| trigger / route identity | catalog.yaml#skill:<id>.routing と route.py | route locator と route digest | trigger 配列、keyword matcher、route decision |
| dependencies | skill-dependencies.yaml | invocation locator と digest | prerequisite/successor の再掲 |
| command-packet identity | catalog の `tool_commands` と `skill_tool_commands.py` | packet locator、packet digest、read-only show command | command prose の再発見、独自 writer、sync facade |
| ToolID / ToolCall / argument schema | `agent_team.materialize_skill_tool_call_token(skill, phase=...)` | skill/phase 固有 ToolCall/argument-schema identity の locator と digest だけ | ToolCall payload、argument schema、ToolID の再定義 |
| graph identity / edge | skill_dependency_map.py の source universe | 参照用 graph locator | graph edge の再 materialize |

agents/canonical/skills.md は index/read parity の projection であり、catalog-derived な
identity source ではありません。documents/design/skill-tool-invocation-graph.md
の graph owner はこの設計の owner/identity locator を参照できますが、shim の
Markdown template は所有しません。

## Canonical Input Record

materializer は catalog/dependency/route/command/typed-tool reader の戻り値を、次の
順序の `agent_canon.skill_runtime_shim.v1` record に canonicalize します。JSON の
object field order、array order、scalar normalization、digest preimage を固定し、
未定義 field、`null`、任意の policy prose、absolute path は拒否します。optional
な関係は `[]` で表し、optional key を省略しません。

~~~text
SkillRuntimeShimRecord = {
  schema, skill_id, discovery, owner, identity, render, provenance
}

schema = { id, version }
discovery = {
  name, description, shim_path,
  host_config_path, host_config_index, host_config_order, host_enabled,
  host_config_entry_digest
}
owner = {
  canonical_doc, canonical_ref, catalog_ref, dependency_ref,
  route_ref, command_ref, tool_surface_ref, graph_ref
}
identity = {
  catalog_identity_digest, dependency_identity_digest,
  route_identity_digest, command_packet_identity_digest,
  tool_surface_identity_digest, tool_call_refs
}
render = { mode, template_id, command_packet_template_id }
provenance = {
  catalog_source_digest, dependency_source_digest, canonical_doc_digest,
  materializer_id, record_digest
}
~~~

field の値は次のように固定します。

| field | 生成値と検査 |
| --- | --- |
| schema.id / schema.version | `agent_canon.skill_runtime_shim` / `1`。未知の version は fail-closed |
| skill_id | catalog の `skill_families[].id` と完全一致。lower hyphen-case |
| discovery.name | 現在の shim frontmatter の name を migration で catalog の discovery metadata に移す。skill_id と一致 |
| discovery.description | 現在の shim frontmatter の description を UTF-8/NFC の scalar として byte-preserving に catalog の discovery metadata へ移す。`purpose` の要約で置換しない |
| discovery.shim_path | .agents/skills/<skill_id>/SKILL.md |
| discovery.host_config_* | `.codex/config.toml` の 0-based entry index、source order、`path`、`enabled` をそのまま readback。entry digest の preimage は `path`, `enabled` のみで、index/order は config wiring identity として別途比較 |
| owner.* | repository-relative POSIX locator。`canonical_ref` は `catalog.yaml#skill:<id>.canonical_doc`、`route_ref` は `catalog.yaml#skill:<id>.routing`、`command_ref` は `catalog.yaml#skill:<id>.tool_commands`、`tool_surface_ref` は `agent_team.materialize_skill_tool_call_token` の skill/phase typed identity record |
| identity.* | 各 owner の typed projection digest。required/discovered/conditional/maintenance の非空 phase ごとに `agent_team` が materialize した ToolCall/argument-schema identity を読み、trigger、dependency、ToolID、ToolCall、argument schema の payload を shim にコピーせず、各 owner の readback が同じ digest を再計算 |
| render.mode | 常に adapter_only。canonical prose は materialize 対象外 |
| render.template_id | skill-runtime-shim-md-v1 |
| render.command_packet_template_id | `skill-tool-command-packet-v2`。packet の全 phase/resolution は locator/digest 経由で保持し、shim に絶対実行 path を入れない |
| provenance.* | repository-relative source digest、materializer identity、record digest。absolute execution path は入れない |

### Canonical serialization and digest

全 scalar は UTF-8、通常文字列は NFC、identifier は NFKC 後に lower hyphen-case
検査、改行は LF、JSON は compact、末尾改行なしとします。record の object key order は
上記の `schema,skill_id,discovery,owner,identity,render,provenance`、各 nested object は
schema block に記載した order とします。arrays は semantic order を持つものだけ source
order を維持し、その他は normalized id の昇順です。`null`、unknown key、absolute path、
YAML mapping の偶然の挿入順は digest に入りません。

record digest は、digest field を除いた canonical JSON bytes `P` に対して
`sha256("agent-canon.skill-runtime-shim.record.v1\0" || P)` とします。owner identity
digest は owner kind ごとに `sha256("agent-canon.skill-runtime-shim.owner.<kind>.v1\0" || P)`、
host config entry digest は `sha256("agent-canon.host-config-entry.v1\0" ||
canonical_json({"path":path,"enabled":enabled}))` とします。command packet digest は
`SkillCommandPacket` の全 fields（required/discovered/conditional/maintenance と全
resolved command tuples、related skills、canonical doc、runtime skill）を
`skill_tool_commands.v2` の field order で serialize した bytes から計算します。
これは単なる `show` 行の digest ではありません。ToolID、ToolCall、argument-schema
digest は `agent_team.materialize_skill_tool_call_token(skill, phase=...)` の canonical
serializer と digest domain を使い、
shim record はそれらを `Ref={id,digest}` として参照します。

rendered shim は source、canonical、route、dependency、command、host config、
ToolCall、materializer を個別 comment として複製しません。materializer は
`SkillRuntimeShimRecord` 全体を owner source から再構成し、次の単一 comment だけを
render/readback します。

~~~text
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"<hex64>"} -->
~~~

`record_digest` の preimage は canonical doc SHA、route/dependency/command packet
digests、host path/index/order/enabled、全非空 phase の skill/phase 固有
ToolID/ToolCall/argument-schema identity、materializer/template identity を含みます。
comment 自体は owner payload を再掲せず、readback は comment の exact
schema/version/digest と owner sources から再構成した record digest を照合します。

### Determinism and idempotent fixed point

この二つを同じ性質として扱いません。

- `determinism` は同じ source snapshot、config readback、command/tool packet、materializer
  version、record input に対して、同じ canonical record bytes/digest、同じ generated
  content bytes、同じ catalog-sized projection digest map を返す純粋な render property です。
- `idempotent fixed point` は実体 target に対する二回の materialize/readback protocol
  の property です。初回は legacy body から content delta が発生し得ます。初回完了後、
  source が不変なら二回目は同じ record digest、catalog-sized projection digest map、readback
  digest/status を返し、`content_delta_count=0`、`content_delta_paths=[]` になります。
  canonical doc を含む record source が一件でも変わった場合は、acceptance fixture を
  更新する前に catalog-derived な全 target を materialize/readback して target tree を収束させます。その
  収束済み tree から fixture producer を二回実行し、first/second とも
  `content_delta_count=0`、`content_delta_paths=[]` を固定します。

実装時の fixture は
`tests/fixtures/skill-runtime-shim/fixed-point/expected.json`、acceptance test は
`tests/agent_tools/test_skill_shim_materializer.py::test_materialize_fixed_point` と
します。fixture/acceptance output は次の exact schema です。

~~~text
FixedPointAcceptance = {
  schema: "agent_canon.skill_runtime_shim.fixed_point",
  version: 1,
  source_snapshot_digest: hex64,
  first_run: {
    record_digests: {skill_id: hex64},
    projection_digests: {skill_id: hex64},
    readback_digest: hex64,
    content_delta_count: integer,
    content_delta_paths: string[]
  },
  second_run: {
    record_digests: {skill_id: hex64},
    projection_digests: {skill_id: hex64},
    readback_digest: hex64,
    content_delta_count: 0,
    content_delta_paths: []
  },
  equal_record_digests: true,
  equal_projection_digests: true,
  equal_readback_digest: true,
  status: "pass"
}
~~~

acceptance は record/projection/readback の各 map が catalog の skill id 集合と一致すること、first/second
の digest map が byte-for-byte equal であること、second run の content delta がゼロ
であることを同時に検査します。per-file replace の途中停止後も、同じ materializer を
再実行した second run がこの fixed-point fixture に一致するまで accepted にしません。

discovery は host metadata の source であり、routing policy の複製ではありません。
catalog に追加する場合も既存 field の意味・順序・trigger 値を変更せず、
discovery の値は現行 frontmatter の readback から一度だけ移します。

## Exact Generated Shim

各 SKILL.md は次の順序・節だけを持ちます。実装時の template は placeholder を
出力しません。例えば `agent-orchestration` の canonical link は
`[agent-orchestration](../../agents/skills/agent-orchestration.md)` と具体化されます。
各 skill では `posixpath.relpath(owner.canonical_doc, ".agents/skills/<id>")` で
同じ相対 link を計算します。

~~~markdown
---
name: <discovery.name>
description: <discovery.description>
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"<provenance.record_digest>"} -->

<!--
@dependency-start
contract skill
responsibility Exposes <skill-id> for runtime discovery.
upstream design ../../../agents/skills/<skill-id>.md owner
@dependency-end
-->

# <skill_id>

## Canonical Skill

Canonical workflow and policy: [agent-orchestration](../../agents/skills/agent-orchestration.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill agent-orchestration --format text`; schema `skill_tool_commands.v2`, digest: `<command_packet_identity_digest>`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
~~~

dependency headerの具体的な field は source record の owner links から生成し、
canonical document の dependency header をコピーしません。固定の responsibility は
「Exposes <skill-id> for runtime discovery.」とし、upstream は catalog、dependency
map、canonical doc、downstream は materializer、command packet、route、alignment checker
とします。これで owner link は残りますが、個別 skill の policy は二重管理になりません。

Tool Commands の executable surface は catalog と `SkillCommandPacket` の単一 source
から materializer が生成します。`skill_tool_commands.py show` は全 fields を返す
read-only packet producer であり、`sync`、`write`、`replace`、facade は提供しません。
materializer 以外の writer が SKILL.md を変更したら writer-inventory failure とします。
command の logical argv、phase、related skill、全 resolved fields は packet JSON と
packet digest で保存し、`source_root`、`execution_cwd`、`execution_argv` の絶対 path は
実行時出力に限り、durable shim metadata には入りません。

## Adapter-Only / Canonical-Prose Handling

ここでの二つの状態を混同しません。

| 状態 | canonical owner | runtime file | 処理 |
| --- | --- | --- | --- |
| canonical_prose | agents/skills/<id>.md | adapter_only shim | 正常な v1。canonical link と単一 materialization-record comment だけを生成 |
| legacy_adapter_only | 旧 generated schema の完全な bytes | adapter 節 | 全必須 metadata field、owner link、dependency manifest、canonical/command section の exact match を readback して再生成 |
| legacy_canonical_prose | canonical doc と重複する既存 shim prose | 生成停止 | canonical prose を adapter 節へ推測で縮退しない |
| legacy_mixed_or_unknown | 未確定 | 生成停止 | shim-only の意味を自動で canonical policy に昇格せず、blocking finding として修正 |

移行は current shim body を正規表現で keyword routing するものではありません。
旧 generated schema は、その schema が要求した frontmatter、8 metadata comments、
canonical owner link、dependency manifest、command invocation、全 section が
materializer の旧 exact template と byte-for-byte 一致する場合だけ受理します。
`Tool Commands` だけ、expected section の subset、owner link 欠落、field 欠落、
field digest mismatch はすべて fail closed です。canonical doc の first heading、
semantic similarity、keyword、近接 path、section membership へ fallback しません。
受理できない block は全件 locator/digest 付き receipt に出し、一件でも存在すれば
per-file replace の前に generation を停止します。canonical prose については semantic
similarity を oracle にせず、次の `LegacyResolutionRecord` を全 block に対して作ります。

~~~text
LegacyResolutionRecord = {
  skill_id, classification, resolution, accepted_sections,
  unmatched_blocks: [{locator, digest}], reviewer_ref
}
~~

`unmatched_blocks` は adapter template に割り当てられない block の完全な locator/digest
list、`resolution` は `migrated` または `blocked` のみです。一致範囲がない、frontmatter
の owner が不明、または policy が shim-only だった場合は `blocked` とし、canonical policy
に推測で昇格させません。この receipt が旧 body と新 adapter の対応 oracle であり、単なる
`show` 行、canonical 文書の先頭 heading、LLM の類似判定は equivalence oracle ではありません。

generic prompt checklist が numbered executable instruction を要求するため、生成
adapter は上記の 1 行の numbered owner-read instruction を必ず保持します。この行は
policy の複製ではなく canonical owner を読むための実行指示です。旧 shim にある
numbered policy rule は移行 receipt を経ずに保持しません。

## Materializer Contract

予定する唯一の writer surface は次です。

~~~bash
python3 tools/agent_tools/skill_shim_materializer.py check --root . --all
python3 tools/agent_tools/skill_shim_materializer.py materialize --root . --all
python3 tools/agent_tools/skill_shim_materializer.py readback --root . --all
~~~

`skill_tool_commands.py` は `show` と `check` の read-only command packet surface だけを
持ち、SKILL.md の変更 route は持ちません。予定する materializer の段階は
`preflight -> classify -> bind -> render -> stage -> per-file replace -> readback`
です。directory swap と journal は採用せず、per-file replace と全件 readback だけを
runtime recovery contract とします。

1. catalog の全 public entry、canonical doc、dependency row、config entry、command
   packet を load する。catalog の skill id 集合との不一致、重複、欠落、unknown id は停止する。
2. SkillRuntimeShimRecord を固定 serializer で作り、catalog の既存 route identity、
   dependency identity、graph locator、command packet、typed ToolID/ToolCall refs を
   確定する。prose、keyword、近接 path から route を決めない。
3. legacy shim の全 catalog id を分類し、LegacyResolutionRecord を作る。unresolved block が
   あれば write phase に入らない。
4. 全 record をメモリ上で render し、各 target の bytes、row digest、staged readback
   を検査する。
5. 検査済みの各 target を deterministic path order で temp file に書き、同じ filesystem
   上で `os.replace` する。これは per-file atomic replace であり、全件 transaction
   ではない。
6. 実体の全 catalog target を再読込し、byte digest、frontmatter、config index/order/
   enabled、owner refs、packet/ToolCall refs を検査する。途中停止や一部 replace failure
   は `partial_stop` として記録し、別の recovery writer を作らず、同じ
   materializer を再実行して canonical source から全 target を収束させる。materialize
   は同じ input record に対して同じ bytes を出す idempotent operation とする。

### Failure Semantics

| failure | state | 次の判断 |
| --- | --- | --- |
| catalog_count_mismatch / missing_canonical_doc | blocked | owner/source を修復して record を再生成 |
| frontmatter_drift / host_config_path_mismatch | drifted | host metadata/config を先に readback |
| unresolved_legacy_block | blocked | canonical owner を明示するまで materialize しない |
| trigger_identity_mismatch / dependency_identity_mismatch | drifted | route/dependency owner から再解決。shim prose を補修しない |
| canonical_prose_in_adapter / duplicate_policy | failed | canonical doc に戻し、shim を template から再生成 |
| tool_command_identity_mismatch | drifted | catalog/command packet owner を検査し、command を手書きしない |
| absolute_locator / unknown_schema | failed | logical locator/schema に戻して readback |
| partial_stop / per_file_replace_failure | partial_stop | 同じ materializer を再実行し、catalog-derived な全 target の readback が pass するまで accepted にしない |

## Migration and Catalog-Derived Readback

移行は一度に catalog-derived な全件を inventory し、対象を番号、サイズ、skill family、変更差分で
分割しません。preflight が全 row、全 source、全 target を解決するまで replace は
開始しません。materializer runtime の write set は生成された runtime target だけです。
materializer の source、tests、eval producer は通常の実装 diff であり、この runtime
write set や per-file recovery に含めません。

~~~text
runtime targets:     .agents/skills/<skill_id>/SKILL.md for all catalog ids
source diff:         agents/skills/catalog.yaml (discovery.name/description only)
host config:         read-only .codex/config.toml; never rewritten by materializer
canonical/deps:      read-only agents/skills/<id>.md and skill-dependencies.yaml
runtime source:      tools/agent_tools/skill_shim_materializer.py (normal implementation diff)
command source:      tools/agent_tools/skill_tool_commands.py (normal implementation diff;
                       show/check remain read-only)
tests:               tests/agent_tools/test_skill_shim_materializer.py and
                      tests/agent_tools/test_skill_shim_evaluation.py plus
                      tests/fixtures/skill-runtime-shim/fixed-point/expected.json
                      (normal implementation diff)
eval producer:       tools/agent_tools/skill_shim_evaluation.py (normal implementation diff)
~~

`.codex/config.toml`、`agents/skills/<id>.md`、`skill-dependencies.yaml`、route/graph
golden source、ToolID/ToolCall/argument schema source は runtime materializer write set
ではない。config は index/order/enabled を read-only に固定し、canonical prose と
relation owner は変更しない。設計作業中の今回の write set はこの設計文書と design
README だけであり、上記の source/tests/eval producer diff は次の implementation phase
の通常の変更契約です。

正確な migration 順序は以下です。

1. `git diff` を変更せずに読み、catalog、canonical docs、config entries、current shims、
   command packets、typed ToolID/ToolCall refs の各集合を catalog と照合する。
2. 各 config entry の 0-based `index`、source `order`、logical `path`、`enabled` と
   `host_config_entry_digest` を baseline receipt に固定する。順序を alphabetical に
   並べ替えたり enabled を再解釈したりしない。
3. current frontmatter/body を分類し、全 LegacyResolutionRecord を作る。unmatched block、
   unknown command、owner link 欠落が一つでもあれば全 locator/digest receipt を出して停止する。
4. catalog の discovery metadata と全 records を canonicalize し、catalog-sized staged shim
   bytes、全 target digest、full command packet JSON/digest、ToolCall refs を run-local
   staging area に生成する。staging area は repository write set ではない。
5. staged bytes を parser で readback し、全件の expected frontmatter/link/packet/
   numbered owner-read instruction と target manifest を比較する。
6. 4 と 5 が pass したときだけ、catalog-derived な全 runtime target を deterministic path order で
   per-file temp + `os.replace` する。source/tests/eval producer の通常実装 diff は
   この replace sequence に含めない。
7. 全 runtime target を実体から再読込し、row receipt、config readback、route/graph
   golden、writer inventory を更新する。途中停止なら `partial_stop` を記録し、同じ
   materializer の再実行で canonical source から未完了/全 target を再収束させる。
8. 全 catalog target の readback が pass して初めて migration を accepted とする。directory
   swap、journal replay、別 recovery writer は作らない。続けて同じ materializer を
   二回目に実行し、fixed-point acceptance fixture の record/projection/readback equality
   と `content_delta_count=0` を確認する。

| phase | 入力 | 生成する evidence | 完了条件 |
| --- | --- | --- | --- |
| baseline | catalog、dependencies、config、generated shim、canonical docs、full command/tool packets | `MigrationBaseline` rows (name, description, path, index, order, enabled, every source/packet digest) | catalog id 集合と config/row 集合が一致する |
| classify | current shim の固定節 parser | `LegacyResolutionRecord` の catalog-sized rows、unmatched locator | unresolved=0 |
| source bind | catalog、dependency map、route.py、typed tool owner、canonical docs | `SkillRuntimeShimRecord` の catalog-sized rowsと record digest | 全 owner/ref/schema が解決 |
| stage | record 集合、runtime target set | staged bytes、target manifest、staged readback | 全 staged rows pass、未承認 path=0 |
| replace | staged runtime targets | per-file replace receipt、target digest | 各 target を deterministic order で temp + `os.replace` |
| readback | runtime targets、config、catalog、owners、packets | per-row readback、partial-stop receipt if needed | missing/extra/duplicate/stale/absolute=0 |
| fixed point | same materializer, unchanged source | `FixedPointAcceptance` fixture/output | record/projection/readback equality、second content delta=0 |
| golden | route/graph/command/tool baseline | semantic golden diff と raw digest delta | typed identity/edge/order/route/command が一致 |

catalog-derived row readback は各 row で次を検査します。

1. name、description、shim path、config path、config index、source order、enabled が
   baseline と完全一致する。
2. canonical doc link が存在し、その digest が record と一致する。
3. dependency、route、command の locator/digest が owner 再計算と一致する。
4. Tool Commands section が `skill_tool_commands.py show --skill <id> --format text`
   を一度だけ持ち、packet の全 fields、全 phase、全 resolved command tuple の
   canonical JSON/digest と一致する。
5. `tool_surface_ref` の ToolID、ToolCall、argument-schema Ref と digest が graph/tool
   owner の readback と一致し、shim に payload が展開されていない。
6. canonical numbered rule、trigger array、dependency array、絶対 path、未承認の
   ToolID、二つ目の policy source が shim にない。keyword-only route decision は
   reject-only finding として fail する。
7. render.mode=adapter_only、schema/version/materializer marker、1行の numbered
   owner-read instruction が一致する。

## Graph and Route Golden Preservation

現 snapshot の skill/command/tool/edge 件数と graph/JSON/Mermaid digest は、この設計へ
埋め込みません。`documents/runtime/skill-dependency-graph.json` の catalog-derived
projection と `tools/agent_tools/check_skill_tool_invocation_graph.py` の readback が
current value の owner です。

shim の body は graph source ではないため、shim materialization だけでは graph の
skill/command/edge/order membership を変更しません。implementation で catalog に
discovery metadata を追加する場合、raw source digest と生成 artifact digest は更新
され得ます。その場合の golden は raw byte digest の同一性ではなく、次の typed
projection equality とします。raw digest の変化は別の `source_digest_delta` として
記録し、semantic golden の pass/fail に混ぜません。

- skill id/order、responsibility group、phase id/order、command id/order、ToolID、
  ToolCall、argument schema、edge kind/source/target/order/attributes、coverage counts
  は現 snapshot と一致する。graph JSON/Mermaid の normalization mode、schema、
  source snapshot ref、projection digest、counts も readback する。
- route.py の frozen output は prompt、route schema、route status、selected/active/
  deferred/matched skill IDs、invocation order、reason/evidence refs、responsibility
  groups、ToolCall refs を exact canonical JSON として比較する。表示用 absolute path、
  run ID、timestamp は projection から除外する。
- `skill_tool_commands.py show --skill <id> --format json` の logical command、
  command phase、related skill、required/discovered/conditional/maintenance の全配列、
  全 resolved argv token と source locator digest は catalog の全 skill id で一致する。
- graph JSON/Mermaid は skill_dependency_map.py graph --root . だけで再生成し、
  check_skill_tool_invocation_graph.py の source/materialized/readback equality を
  通す。generated graph を手編集しない。

route golden は実在する `evidence/agent-evals/workflow_selection_eval.toml` の
`expected_case_count=525`、`expected_generated_case_count=525` を読み、manifest loader
が展開した 525 cases の固定 prompt を、実在する `route.py` の CLI または
`load_skill_route_rules` + `decide_skills` + `RouteRenderer("json")` の実在関数へ直接
渡す golden producer に接続します。`evaluate_workflow_selection.py` や
`.codex/hooks/skill_usage_logger.py` を route golden の判定器として呼びません。

golden producer の各 case output は次の exact schema です。success/failure の全 field
を常に出し、`null` や free-form failure text を使いません。

~~~text
RouteGoldenCase = {
  schema: "agent_canon.route_golden_case.v1",
  case_id: string,
  prompt_sha256: hex64,
  invocation: {
    cli: "tools/agent_tools/route.py",
    mode: "repo-changing" | "routing-only",
    format: "json"
  },
  status: "pass" | "fail",
  normalized_route_json_digest: hex64,
  route: {
    schema: "agent_canon.route.skill_route.v1",
    route: string, mode: string, skills: string[], active_skills: string[],
    deferred_skills: string[], matched_skills: string[],
    related_skill_candidates: string[], related_skills: object,
    reasons: string[], visualization_owner_skill: string | null,
    visualization_tool_call: object | null,
    visualization_adapter_tool_call: object | null,
    visualization_rejection: string | null, evidence: string
  },
  failure: {
    code: "none" | "SKILL_ROUTER_ERROR" | "ROUTE_SOURCE_ROOT_FAILURE" | "ARGUMENT_ERROR",
    class: "none" | "runtime" | "source_root" | "argument" | "catalog",
    exit_code: integer, stderr_sha256: hex64
  }
}
~~~

`route` is the exact JSON projection emitted by `RouteRenderer("json")`, with object keys
sorted by the existing renderer and compact UTF-8 canonical serialization for the digest.
`failure.code` is the exact stable prefix emitted by the CLI, and `failure.class` is mapped
by the fixed table above; unrecognized prefixes fail the producer rather than being folded
into a generic pass. The producer stores `prompt_sha256`, the normalized route JSON digest,
and the failure code/class for every case in one report. No expected answer is placed in the
fresh evaluator packet; the parent-only oracle stores the expected case projection separately.

`route.py` 自体の argparse behavior は変更しません。golden producer は subprocess の
`returncode`, `stdout`, `stderr` を受け、次の mapping だけを適用します。

| observed CLI result | normalized `failure` |
| --- | --- |
| returncode=0、JSON schema が `agent_canon.route.skill_route.v1` | `code="none", class="none", exit_code=0, stderr_sha256=sha256(UTF-8 empty)` |
| returncode=2、stderr の最初の non-empty line が `usage:` で、同じ stderr に argparse の `error:` line がある | `code="ARGUMENT_ERROR", class="argument", exit_code=2, stderr_sha256=sha256(raw stderr)` |
| returncode=2 だが上記 usage/error pair でない | producer failure `UNMAPPED_ROUTE_FAILURE`; golden artifact は生成しない |
| returncode が上記以外、または process 起動不能 | producer failure `UNMAPPED_ROUTE_FAILURE`; golden artifact は生成しない |

`ARGUMENT_ERROR` は producer artifact だけの stable code で、`route.py` の exit code、
usage text、error text は変更・置換しません。`stderr_sha256` は raw UTF-8 stderr の
digest とし、表示用 stderr 本文を golden identity にしません。

producer の exact path は `tools/agent_tools/skill_shim_evaluation.py` の
`route-golden` subcommand、focused test path は
`tests/agent_tools/test_skill_shim_evaluation.py::test_route_golden_normalizes_argparse_error`、
validation command は次です。

~~~bash
python3 tools/agent_tools/skill_shim_evaluation.py route-golden \
  --root . --manifest evidence/agent-evals/workflow_selection_eval.toml \
  --route-cli tools/agent_tools/route.py \
  --output <run-dir>/route-golden.json
~~~

この producer、test、validation report は通常の implementation/evidence diff であり、
route.py と catalog-derived shim の materializer runtime write set には含めません。

~~~text
public skill selection with a canonical skill name
dependency prerequisite and successor selection
ToolCall command packet selection
unrelated task that must not activate a skill
host-provided system skill delegation
~~~

この probe は新しい routing keyword を追加するためではなく、既存 catalog route が
shim body の短縮に影響されないことを確認するためだけに使います。

525-case workflow-selection evidence remains a separate deterministic evaluator owned by
`tools/agent_tools/evaluate_workflow_selection.py`, whose current implementation loads
`.codex/hooks/skill_usage_logger.py` and records workflow-selection evidence. That evaluator
and its logger are not the route golden producer and are not the shim routing owner.

決定論評価の実在 CLI は次です。

~~~bash
python3 tools/agent_tools/evaluate_workflow_selection.py \
  --root . --manifest evidence/agent-evals/workflow_selection_eval.toml \
  --report-out <run-dir>/workflow-selection.md
~~~

この CLI の stdout/report が fixed prompt/expected readback の一次結果です。存在しない
`--format` option や手書き route runner は設計に含めません。

shim route golden の planned producer は、次の実在 `route.py` CLI を case ごとに直接
呼び出します（route golden producer 自体は implementation phase の通常 diff です）。

~~~bash
python3 tools/agent_tools/route.py --root . --prompt-file <case-prompt-file> --format json
~~~

in-process 版を選ぶ場合も、同じ `route.py` の
`load_skill_route_rules(...)`、`decide_skills(...)`、`RouteRenderer("json")` を直接
呼び、別の route classifier を作りません。planned producer の出力は上記
`RouteGoldenCase` exact schema とし、`evaluate_workflow_selection.py` の logger-based
result を route JSON に変換しません。

## Prompt Token Reduction and Fresh gpt-5.4-mini Evaluation

### Token Contract

tokenizer registry や独自 tokenizer は新設しません。measurement producer は実装時に
`tools/agent_tools/skill_shim_evaluation.py` として追加し、fresh `gpt-5.4-mini` host
evaluation が返す観測可能な `input_tokens` usage をそのまま artifact に保存します。
この usage は model-host observation であり、決定論尺度と同一視しません。

~~~formula
U_i = observed host input_tokens(current or generated, fresh gpt-5.4-mini)
B_i = deterministic_measure(host_envelope + current .agents/skills/<id>/SKILL.md)
G_i = deterministic_measure(host_envelope + generated adapter-only SKILL.md)
reduction_i = (B_i - G_i) / B_i
aggregate_reduction = sum(B_i - G_i) / sum(B_i)
~~~

`deterministic_measure` は既存標準ライブラリだけで完全定義します。入力を UTF-8 に
decode した後、CRLF/CR を LF、Unicode を NFC、末尾改行を一つに正規化し、
`utf8_bytes = len(normalized.encode("utf-8"))`、`unicode_scalars = len(normalized)` を
記録します。両方を deterministic comparison の正本とし、既存 source bytes と
normalized bytes を混同しません。

measurement artifact の exact top-level schema は次です。

~~~text
MeasurementArtifact = {
  schema: "agent_canon.skill_runtime_shim.measurement",
  version: 1,
  run_id: string,
  source_snapshot_digest: hex64,
  model_id: "gpt-5.4-mini",
  host_profile: "medium",
  normalization: "utf8-nfc-lf-final-newline",
  host_envelopes: HostEnvelope[],
  candidate_rows: CandidateMeasurementRow[],
  scenario_rows: ScenarioMeasurementRow[],
  summary: MeasurementSummary
}

HostEnvelope = {
  row_type: "host_envelope",
  host_envelope_id: string,
  model_id: "gpt-5.4-mini",
  host_profile: "medium",
  skill_id: string,
  config_entry_index: integer >= 0,
  config_order: integer >= 0,
  config_path: string,
  enabled: boolean,
  prompt_sha256: hex64,
  host_envelope_sha256: hex64,
  host_utf8_bytes: integer >= 0,
  host_unicode_scalars: integer >= 0
}

CandidateMeasurementRow = {
  row_type: "candidate",
  candidate_row_id: string,
  host_envelope_id: string,
  skill_id: string,
  variant: "current" | "generated",
  content_sha256: hex64,
  measured_input: "host_envelope_plus_candidate",
  utf8_bytes: integer >= 0,
  unicode_scalars: integer >= 0,
  denominator_status: "valid" | "not_applicable"
}

ScenarioMeasurementRow = {
  row_type: "scenario",
  scenario_row_id: string,
  scenario_id: string,
  packet_id: string,
  iteration_id: string,
  provenance: "fresh",
  candidate_row_id: string,
  host_envelope_id: string,
  variant: "current" | "generated",
  host_input_tokens: integer >= 0,
  host_usage_source: "fresh_host_evaluation",
  canonical_followup_input_tokens: integer >= 0,
  cache_fields_observed: object,
  observation_status: "pass"
}

MeasurementSummary = {
  host_envelope_count: integer >= 0,
  candidate_row_count: integer >= 0,
  scenario_row_count: integer >= 0,
  valid_denominator_row_count: integer >= 0,
  not_applicable_row_count: integer >= 0,
  current_utf8_bytes_total: integer >= 0,
  generated_utf8_bytes_total: integer >= 0,
  current_unicode_scalars_total: integer >= 0,
  generated_unicode_scalars_total: integer >= 0,
  observed_host_input_tokens_total: integer >= 0,
  paired_reduction_row_count: integer >= 0,
  non_positive_reduction_row_count: integer >= 0,
  deterministic_reduction_status: "pass" | "fail" | "not_applicable"
}
~~~

All listed fields are required, no listed field accepts `null`, and unknown fields are rejected.
Empty optional observations use `{}` or `[]`; absent host usage is a producer failure and never
becomes a zero. `host_input_tokens` and `canonical_followup_input_tokens` are integers in the
closed range `[0, +infinity)`. `host_envelopes` contain only candidate-independent host data;
they never contain `current_*` or `generated_*` bytes/scalars. Those values exist only in their
corresponding `CandidateMeasurementRow`, referenced by `candidate_row_id` from each fresh
scenario observation.

`host_input_tokens` は host が返した数値、`host_usage_source="fresh_host_evaluation"` は
固定値です。cache field が host から返らない場合は空 object とし、推測した discount は
記録しません。current/generated は同じ scenario/packet class の別 fresh iteration として
pairing し、observed token usage と candidate deterministic bytes/scalars を別 row type
で比較します。candidate row の `utf8_bytes`/`unicode_scalars` は
`host_envelope_plus_candidate` の正規化済み入力尺度、`content_sha256` は候補本文だけの
digest です。B_i=0 は 0 とせず `denominator_status="not_applicable"` とし、zero
denominator row は aggregate pass を禁止します。

current/generated candidate は scenario identity または deterministic skill identity ごとに
exact pair として照合します。missing、duplicate、variant/skill/envelope mismatch は
producer failure とし、各 pair で current の UTF-8 bytes と Unicode scalars の両方が
generated より厳密に大きい場合だけ positive reduction row と数えます。
`non_positive_reduction_row_count > 0` は aggregate が 70% 以上でも
`deterministic_reduction_status="fail"` とします。

報告するのは catalog-derived row の deterministic bytes/scalars total、median、p10/p90、最大値、
zero-denominator row 数、fresh host の paired input-token total、canonical-followup
total、fresh evaluator の pass rate です。percentile は fixed nearest-rank p10/p50/p90 と
し、目標は deterministic adapter measure の aggregate reduction >= 70%、全 row の
reduction > 0、critical usability failure=0 とし、
baseline に対する scenario pass rate の低下を 5 percentage points 未満に制限
します。observed input token usage は usability/host evidence として保存し、tokenizer
なしの deterministic尺度を token count と呼びません。canonical read route、ToolCall、
owner boundary を失った場合は失敗です。

### Fresh Scenario Packets

fresh evaluator の model/profile は `gpt-5.4-mini` / `medium`、read-only、fresh
instance に固定します。現行 checklist の二つの answer-free packet class、
canonical-graph `full` と `changed` を維持し、三つの scenario を三つの packet class
にはしません。`full` packet に discovery-selection と boundary-negative、`changed`
packet に toolcall-route を variant として収録します。各 packet は full Prompt Under
Test text とその path、Canonical Target Files、Prompt Dependency Files、frozen
scenario、requirements/checklist、method、fixed report grammar、packet digest を持ち、
expected command、expected artifacts、answer、prior reasoning は持ちません。
各 evaluator は一つの packet/variant だけを読み、nested agent、prior result、期待する
command、期待 answer を受け取りません。parent-only oracle が expected route を別 artifact
で保持します。

実装時の packet manifest path は固定で
`evidence/agent-evals/skill_runtime_shim_eval.toml` とします。manifest は次の schema
だけを持ち、answer-free packet の content と parent-only oracle を混ぜません。

~~~toml
catalog_kind = "agent_canon_skill_runtime_shim_eval"
version = 1
packet_class_order = ["full", "changed"]

[[packet]]
id = "shim-discovery-selection-v1"
packet_class = "full"
prompt_path = "evidence/agent-evals/skill-runtime-shim/packets/full/shim-discovery-selection-v1.md"
canonical_target_files = [".agents/skills/agent-orchestration/SKILL.md", "agents/skills/agent-orchestration.md"]
prompt_dependency_files = ["agents/skills/catalog.yaml", "agents/skills/skill-dependencies.yaml", "documents/codex/prompt-skill-evaluation-checklist.md"]
method = "one fresh read-only gpt-5.4-mini evaluator"
requirements = ["discovery", "canonical-owner", "no-shim-route"]
report_grammar = "documents/codex/prompt-skill-evaluation-checklist.md#Observed-Report-Grammar"
packet_digest = "sha256-of-the-complete-answer-free-packet"

[[packet]]
id = "shim-boundary-and-negative-v1"
packet_class = "full"
prompt_path = "evidence/agent-evals/skill-runtime-shim/packets/full/shim-boundary-and-negative-v1.md"
canonical_target_files = [".agents/skills/task-routing/SKILL.md", "agents/skills/task-routing.md"]
prompt_dependency_files = ["agents/skills/catalog.yaml", "documents/codex/prompt-skill-evaluation-checklist.md"]
method = "one fresh read-only gpt-5.4-mini evaluator"
requirements = ["no-false-activation", "host-delegation", "no-duplicate-policy"]
report_grammar = "documents/codex/prompt-skill-evaluation-checklist.md#Observed-Report-Grammar"
packet_digest = "sha256-of-the-complete-answer-free-packet"

[[packet]]
id = "shim-toolcall-route-v1"
packet_class = "changed"
prompt_path = "evidence/agent-evals/skill-runtime-shim/packets/changed/shim-toolcall-route-v1.md"
canonical_target_files = [".agents/skills/structure-planning/SKILL.md", "agents/skills/structure-planning.md"]
prompt_dependency_files = ["agents/skills/catalog.yaml", "agents/skills/skill-dependencies.yaml", "documents/design/skill-tool-invocation-graph.md"]
method = "one fresh read-only gpt-5.4-mini evaluator"
requirements = ["owner-command-packet", "typed-toolcall", "failure-semantics"]
report_grammar = "documents/codex/prompt-skill-evaluation-checklist.md#Observed-Report-Grammar"
packet_digest = "sha256-of-the-complete-answer-free-packet"
~~~

`packet_digest` は実装時に literal placeholder ではなく、packet file の canonical UTF-8
bytes から計算します。packet file は prompt、target/dependency paths、scenario、
requirements、method、report grammar だけを持ち、`expected_*`, `oracle_*`, expected
command/artifacts、prior result は schema 上禁止します。parent-only oracle の exact path
は `evidence/agent-evals/skill-runtime-shim/oracles/<packet-id>.json`、measurement
artifact の exact path は `evidence/agent-evals/skill-runtime-shim/measurements/<run-id>.json`
とし、evaluator allowlist に oracle path を入れません。oracle JSON は
`schema, packet_id, scenario_id, baseline_projection, generated_projection,
expected_route_projection, expected_failure_projection, oracle_digest` の順で保存し、
fresh packet からは不可視です。

| packet | prompt under test | allowlist | 観測する要件 |
| --- | --- | --- | --- |
| shim-discovery-selection-v1 | 代表的な adapter-only shim とユーザー task | 評価対象 shim、対応 canonical doc、catalog/dependency の owner rows、checklist | host shim を public skill として発見し、canonical owner を指し、shim prose から policy/keyword route を発明しない |
| shim-toolcall-route-v1 | agent-orchestration または structure-planning の command packet を要求する task | 対象 shim、canonical doc、skill_tool_commands.py contract、route/dependency owner | packet を owner から取得し、ToolCall/owner/dependency/failure semantics を区別する。期待する command は packet に埋め込まない |
| shim-boundary-and-negative-v1 | 無関係 task、host-provided system skill、canonical prose を変更する task の三択を含むが、正解は packet に書かない | 対象 shim、catalog、canonical docs、host delegation table、checklist | 不要な activation を避け、official system skill を local catalog に取り込まず、canonical prose を shim に追加しない |

fresh scenario artifact/token measurement producer は実装時に次の一つの CLI surface と
して追加します。これは現時点では未実装であり、設計 validation command として実行した
とは主張しません。

~~~bash
python3 tools/agent_tools/skill_shim_evaluation.py packets \
  --root . --manifest evidence/agent-evals/skill_runtime_shim_eval.toml \
  --model gpt-5.4-mini --profile medium --output-dir <run-dir>/packets
python3 tools/agent_tools/skill_shim_evaluation.py tokens \
  --root . --model gpt-5.4-mini --manifest evidence/agent-evals/skill_runtime_shim_eval.toml \
  --host-evaluation-dir <run-dir>/host-evaluations \
  --output <run-dir>/measurements/<run-id>.json
~~~

`packets` は packet text/path/dependency/target/digest artifact と parent-only expected
readback を分離して出し、`tokens` は manifest の全 scenario ID ごとに current/generated
の一意な exact pair を必須にして、missing、duplicate、packet/category mismatch、incomplete
observation を fail-closed とします。`tokens` は host evaluation の observed `input_tokens` と
deterministic bytes/scalars の paired rows、percentile、zero-denominator fields を出します。
producer は repository の current CLI を subprocess で呼び、answer を prompt artifact に
埋め込みません。各 scenario は current shim と generated shim を
別 iteration で評価し、同じ scenario_id の fresh instance を再利用しません。parent は
discovery_accuracy、
canonical_owner_following、toolcall_exactness、false_activation_rate、
duplicate_policy_rate、malformed_report_rate と token metrics を分離して記録します。
evaluation_status=pass は evaluator の観測結果であり、parent の critical-pass や
convergence を意味しません。

## Validation Route

Wave 4 design の validation evidence は次です。

~~~bash
python3 tools/agent_tools/check_agent_runtime_alignment.py
python3 tools/agent_tools/check_skill_frontmatter.py --root .
python3 tools/agent_tools/skill_tool_commands.py --root . check
python3 tools/agent_tools/skill_dependency_map.py check --root .
python3 tools/agent_tools/check_skill_tool_invocation_graph.py --root .
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --root . --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml \
  --report-out <run-dir>/skill-workflow-prompt.md
python3 tools/agent_tools/evaluate_workflow_selection.py \
  --root . --manifest evidence/agent-evals/workflow_selection_eval.toml \
  --report-out <run-dir>/workflow-selection.md
~~~

implementation phase では上記に materializer の check/readback、catalog-derived migration
receipt、route golden diff、graph regeneration/readback、fresh mini packet/token
producer reports を追加します。固定点 acceptance は次の focused test で検証します。

~~~bash
python3 -m pytest \
  tests/agent_tools/test_skill_shim_materializer.py \
  -k test_materialize_fixed_point
python3 tools/agent_tools/skill_shim_evaluation.py route-golden \
  --root . --manifest evidence/agent-evals/workflow_selection_eval.toml \
  --route-cli tools/agent_tools/route.py \
  --output <run-dir>/route-golden.json
python3 tools/agent_tools/skill_shim_evaluation.py tokens \
  --root . --model gpt-5.4-mini --manifest evidence/agent-evals/skill_runtime_shim_eval.toml \
  --host-evaluation-dir <run-dir>/host-evaluations \
  --output <run-dir>/measurements/<run-id>.json
~~~

上記の producer/test は実装 phase の通常 diff として追加するもので、route.py 自体は
変更しません。直前の current validation block は現時点に存在する CLI のみを示し、
ここで示した producer/test command は実装後の validation contract です。未実装の
`skill_shim_materializer.py` と `skill_shim_evaluation.py` は current validation として
実行したことを主張しません。この design phase では fresh clone の graph DB unavailable
を記録し、graph checker の pass output と source artifact を使いました。

## Evidence And Assumption Ledger

| kind | statement | evidence / owner | status |
| --- | --- | --- | --- |
| fact | public shim、canonical skill doc、host config は catalog の skill id 集合で照合される | current find inventory、check_agent_runtime_alignment.py、graph checker | observed |
| fact | graph projection の skill/command/tool/edge counts は source snapshot から生成される | check_skill_tool_invocation_graph.py --root . | observed |
| fact | shim frontmatter は catalog-derived な全件で readback され、body size は不均一になり得る | check_skill_frontmatter.py、catalog-sized inventory | observed |
| fact | current skill_tool_commands.py は catalog structured branch で command phase を解決し、現在の `sync` は runtime file を直接編集する | tools/agent_tools/skill_tool_commands.py | observed; target state では sync surface を削除 |
| assumption | discovery metadata を catalog に追加しても graph semantic payload は変わらない | graph builder の skill payload は id/doc/shim/command/capability/phase だけを投影 | explicit; implementation readback required |
| assumption | host discovery は frontmatter/config path を保持し、fresh gpt-5.4-mini evaluator は adapter の canonical relative link を辿れる | fresh packet artifact と observation report で検証 | pending implementation eval |
| limitation | fresh clone には dependency graph DB と semantic-index cache がなく、依存 review/semantic relations は今回実行不可 | run_repo_dependency_review.sh、semantic-index output | recorded, non-blocking for design |

## Design-To-Implementation Trace

| clause | implementation owner | planned path / symbol | reverse readback |
| --- | --- | --- | --- |
| SHIM-001 one schema and fixed field order | shim materializer | tools/agent_tools/skill_shim_materializer.py / SkillRuntimeShimRecord | schema/version/field order and canonical JSON digest |
| SHIM-002 catalog-owned discovery metadata | catalog reader | agents/skills/catalog.yaml / skill_families[].discovery | catalog-sized frontmatter pairs equal migration baseline |
| SHIM-003 canonical prose stays out of runtime adapter | human skill canon | agents/skills/<skill>.md and generated template | adapter contains link/digest only; duplicate-policy scan=0 |
| SHIM-004 owner/dependency/route identity | route/dependency readers | skill_route_catalog.py, route.py, skill_dependency_map.py | catalog-derived route/dependency digests and semantic edge golden |
| SHIM-005 command packet preservation | command packet owner | skill_tool_commands.py / SkillCommandPacket (read-only) | complete packet JSON/digest, all phases/resolved fields, catalog-derived command count equals generated graph/readback |
| SHIM-005b typed ToolID/ToolCall preservation | graph/tool-packet owner | agent_team.py, skill-tool-invocation-graph.md | ToolID/ToolCall/argument-schema Ref and digest equal; no payload in shim |
| SHIM-006 host discovery preservation | runtime alignment | .codex/config.toml, check_agent_runtime_alignment.py | catalog-sized config-to-shim paths, frontmatter pass |
| SHIM-007 single writer | shim materializer | skill_shim_materializer.py; skill_tool_commands.py has no sync/write surface | writer inventory identifies exactly one SKILL.md writer; sync symbol absent |
| SHIM-008 all-catalog migration/readback | migration route | skill_shim_materializer.py migrate/readback and tests | catalog-sized row receipt, unresolved=0 |
| SHIM-009 graph/route golden | graph and route checkers | skill_dependency_map.py, check_skill_tool_invocation_graph.py, frozen route cases | typed identity/edge/order/route equality |
| SHIM-010 token reduction | prompt eval owner | existing prompt/workflow CLIs plus planned skill_shim_evaluation.py tokens | observed host usage, UTF-8 bytes/Unicode scalars, envelope/cache observation, percentile/paired rows; aggregate >=70% |
| SHIM-011 fresh mini usability | evaluator route | planned skill_shim_evaluation.py packets; checklist full/changed packet classes | three scenario variants in two packet classes, no prior context, fixed report grammar |
| SHIM-012 no keyword/duplicate policy | route and checker tests | route tests plus shim materializer negative tests | keyword-only route and canonical-prose-in-adapter both fail |
| SHIM-013 determinism vs fixed point | materializer acceptance | `tests/fixtures/skill-runtime-shim/fixed-point/expected.json`, `tests/agent_tools/test_skill_shim_materializer.py::test_materialize_fixed_point` | first/second catalog-sized record/projection maps, readback digest equal; second content delta=0 |
| SHIM-014 route CLI error normalization | golden producer owner | `tools/agent_tools/skill_shim_evaluation.py route-golden`, `tests/agent_tools/test_skill_shim_evaluation.py::test_route_golden_normalizes_argparse_error` | route.py unchanged; argparse exit 2 + usage/error stderr maps exactly to ARGUMENT_ERROR |
| SHIM-015 measurement artifact contract | measurement producer owner | `tools/agent_tools/skill_shim_evaluation.py tokens` and `tests/agent_tools/test_skill_shim_evaluation.py` | top-level schema/version, required non-null rows, host_input_tokens >=0, host/candidate separation |

Implementation handoff must cite SHIM-001..SHIM-015. The normal implementation diff may
contain the materializer source, command-surface source, catalog discovery metadata,
tests, and eval producer; the materializer runtime write set remains only the catalog-generated
shim targets. Required checker/eval projections are readback artifacts, not a second runtime
writer. The handoff must not edit canonical skill prose to make the adapter look useful. Any
need to change public identity, route semantics, ToolID, argument schema, or host config
reopens this design before implementation.

## Structure Contract

- structure_kind: implementation-ready design specification
- audience: materializer, route/graph/checker owners, evaluator, and reviewer
- first_artifact: exact generated shim schema/table
- first_artifact_question: host discovery に必要な最小入力と canonical prose の owner は何か
- visual_plan: text-only; schema table、state table、trace table、既存 generated graph を使うため新規 Mermaid は追加しない
- document_unit: owner=documents/design/skill-runtime-shim-materialization.md; reader=implementation and validation owners; source map=catalog/dependencies/canonical docs/graph/checklist; validation=design claims, headers, alignment, graph readback; cadence=Wave 4 implementation and future shim template changes; canonical parent=documents/design/README.md; consumers=materializer, checkers, route, evaluator
- document_split_decision: split because this is a new owner, schema, materializer, migration route, and validation surface
- invalid_interpretations: this document is not a route keyword dictionary, not a generated graph, not permission to implement/commit, and not evidence that the planned materializer already exists
