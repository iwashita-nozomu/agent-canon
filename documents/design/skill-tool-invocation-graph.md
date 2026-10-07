<!--
@dependency-start
contract design
responsibility Defines the canonical source universe, serialization, generated projections, and readback contract for skill/tool invocation.
upstream design ../rule/README.md document naming and Japanese-content rule
upstream design ../../agents/skills/agent-orchestration.md route and Decision Sufficiency owner
upstream design ../../agents/skills/skill-dependencies.yaml prerequisite, successor, order, and parallel relation owner
upstream design ../../agents/canonical/skills.md reader-facing catalog projection
upstream design ../../agents/internal-routines/design-implementation-correspondence.md universal design-to-implementation correspondence
downstream implementation ../../tools/agent/skills/skill_route_catalog.py catalog resolver
downstream implementation ../../tools/agent/orchestration/route.py capability and phase route materialization
downstream implementation ../../tools/agent/skills/skill_dependency_map.py dependency graph validation
downstream implementation ../../tools/agent/orchestration/agent_team.py typed ToolCall materialization
downstream implementation ../../tools/runtime/lifecycle/bootstrap_agent_run.py handoff and manifest transport
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py runtime alignment readback
downstream implementation ../../tools/validation/semantic/convention/check_convention_compliance.py canonical route convention gate
@dependency-end
-->

# Skill / Tool Invocation Graph

## Reader Map

この文書は、skill、capability、ToolCall、manifest、dependency/order/routing/parallel edge、JSON、Mermaid、readback を同じ source snapshot から対応付ける設計正本です。先に owner boundary と universe を読み、次に canonical serialization、invariants、checker 入出力、failure semantics を確認します。最後に catalog-derived な source inventory と Design-To-Implementation Trace を使って実装・レビューへ渡します。個別の skill 本文は `agents/skills/*.md`、読者向け一覧は [agents/canonical/skills.md](../../agents/canonical/skills.md)、関係は `agents/skills/skill-dependencies.yaml`、共通対応遷移は [agents/internal-routines/design-implementation-correspondence.md](../../agents/internal-routines/design-implementation-correspondence.md) が所有します。

## Responsibility / Owner Boundaries

| 責務 | 唯一の正本 owner | projection / materializer | 境界 (`agents/skills/catalog.yaml`) |
| --- | --- | --- | --- |
| prerequisite / successor / order / parallel relation | `agents/skills/skill-dependencies.yaml` | `skill_dependency_map.py`, `route.py` | 関係、順序、routing candidate をここからだけ読む。prompt や prose で再定義しない |
| typed capability / owner / phase route | `route.py` の typed route packet と owner surface | `route.py` | explicit typed capability と owner を解決する。prose keyword は選択器ではない |
| ToolID / ToolCall / manifest | orchestration/tool packet owner | `agent_team.py`, `bootstrap_agent_run.py` | materialized records は既存 identity の ID/digest を参照し、prose から発見しない |
| visualization | [agents/skills/code-visualization.md](../../agents/skills/code-visualization.md) の projection owner | planned graph checker | source universe から実際の nodes/edges/order を生成する。手書き graph は許可しない |
| equality / stale readback | planned `check_skill_tool_invocation_graph.py` と既存 alignment/convention checkers | checker outputs | source、canonical JSON、generated Mermaid、reader projection の一致を fail-closed で判定する |
| design/implementation correspondence | [agents/internal-routines/design-implementation-correspondence.md](../../agents/internal-routines/design-implementation-correspondence.md) | handoff/review owner | clause fingerprint と forward/reverse coverage を統合する |

`catalog.yaml` の `skill_families` が source snapshot の skill universe であり、count は毎回 materialize して readback する実測値である。schema は固定 bucket 数を持たず、追加・削除は source snapshot の count を変える。人工的な分類や番号付けは graph universe ではない。

## Exact Data / State Model

### Source universe

schema は `agent_canon.skill_tool_invocation_graph.v2` とする。checker の入力 snapshot から、次の集合を**実際に解決された全件**として構成する。

```text
SourceUniverse {
  source_snapshot: {catalog_sha256, dependencies_sha256, reader_index_sha256,
  identity_records: every unique IdentityRecord, stored once
  skill_refs: every catalog.skill_families entry                 # catalog-derived count
  capability_refs: every typed capability returned by the selected route
  toolcall_refs: every resolved ToolCall IdentityRecord Ref
  edge_projections: every actual prerequisite, successor, order, routing,
                    owner-before-adapter, owner relation, and parallel-independent relation
  order: explicit integer order for each ordered invocation, not edge-list position
}
```


[agents/canonical/skills.md](../../agents/canonical/skills.md) は reader/index link parity の検査対象に限られ、skill-count projection でも identity source でもない。skill rows は `agents/skills/catalog.yaml` と resolved/materialized IR から生成する。`skills.md` の canonical-doc/shim link が catalog の id と対応しない、link target が stale、または未登録 id を指す場合だけ reader-link parity failure とする。

### Artifact side-effect boundary

Graph construction and `check` are read-only with respect to the source
checkout.  A `graph` invocation without `--output` requires an explicit
`--runtime-root` (or `AGENT_CANON_RUNTIME_ROOT`) and writes the Markdown/JSON
projection below that external runtime root.  It never falls back to the
tracked `documents/runtime/` pair.  An explicit output must likewise be
external unless it names exactly `documents/runtime/skill-dependency-graph.md`
and its derived `.json` pair with a source-mutation capability.  That
capability has the exact `allowed_paths`, `purpose`, and `authority` fields;
the allowed paths are fixed to the two tracked graph files.  Source mutation
also requires an external runtime root and publishes a before/after evidence
record there.  The record identifies the capability, changed paths, and the
two source snapshots.  A capability cannot authorize an arbitrary source
path, and a runtime artifact is never treated as source mutation authority.

### Canonical identity records, references, and projection envelopes

```text
IdentityRecord {id, digest, kind, canonical_payload}
Ref {id, digest}
NodeProjection {ref: Ref, kind, display_label}
PhaseProjection {ref: Ref, display_label, order}
EdgeProjection {edge_ref: Ref, source_ref: Ref, target_ref: Ref, display_label}
ManifestEnvelope {manifest_ref: Ref, source_digest, identity_refs, edge_refs, coverage_refs, counts}
ReadbackEnvelope {readback_ref: Ref, source_digest, json_digest, mermaid_digest, projection_digests, evidence_refs, counts}
CheckResult {status, failure_refs, unresolved_refs, counts}
ExecutionContext {root_abs, resolved_locators, expires_at=invocation_end}
```



`ManifestEnvelope`、`CoverageEnvelope`、`ReadbackEnvelope` は ordered `Ref`、digest、counts だけを保持する。status、failure reason、unresolved detail は `CheckResult` の `failure_refs`/`unresolved_refs` から参照し、envelope に payload として重複しない。durable artifact の locator は `/` 区切りの logical repository-relative locator とし、絶対 path、`..`、`.`、empty segment、NUL を拒否する。absolute runtime path は execution context でだけ解決し、終了時に破棄する。

### Lifecycle state

```text
declared -> resolved -> canonicalized -> routed -> materialized -> projected -> read_back -> accepted
declared|resolved|canonicalized|routed|materialized|projected|read_back -> stale|blocked|failed
```

`resolved` は source owner から全 identity/relations を読み終えた状態、`canonicalized` は bytes/digest が確定した状態、`routed` は typed capability owner と phase が確定した状態、`materialized` は ToolCall/manifest が Ref のみで構成された状態、`projected` は JSON と Mermaid が同じ in-memory universe から生成された状態である。実装境界は `tools/agent/orchestration/route.py`、`tools/agent/orchestration/agent_team.py`、`tools/runtime/lifecycle/bootstrap_agent_run.py` である。

### Canonical serialization and digest

次の規則を schema の一部として固定する。

- 文字列は Unicode `NFC` に正規化してから UTF-8 bytes にする。display text は case を保持し、identifier/alias は `NFKC`、`casefold`、ASCII hyphen-case validation の順に適用する。`_`、空白、類似文字の暗黙変換はしない。
- alias は catalog の明示的 alias field からのみ読んで、正規化後に `{alias, alias_of}` へ materialize する。alias は identity を作らず、prose、purpose、description、trigger keyword は alias/capability/adapter selector にならない。
- canonical bytes は mapping の key を再帰的に sort し、object/array の全階層で同じ serializer を使う。approved identifier field の値は NFKC 後に casefold し、通常の表示文字列は NFC、UTF-8、compact JSON、末尾改行なしとする。従って mapping の挿入順と Unicode alias 表記は digest を不安定化しない。
- arrays は semantic order がある `order`/`logical_argv` 以外を `(kind,id,alias_of)` の順で並べる。ordered edges は `order` を持ち、入力配列の偶然の順序を意味にしない。JSON bytes は compact JSON、UTF-8、末尾改行なしとする。共通 packet の ASCII escaping/scalar rule は [agents/internal-routines/design-implementation-correspondence.md](../../agents/internal-routines/design-implementation-correspondence.md) と同じ canonical serializer を使う。
- digest は次の acyclic digest DAG で計算する。identity level の `IdentityPreimage` は `UTF8(domain) || NUL || UTF8(schema) || NUL || UTF8(id) || NUL || UTF8(kind) || NUL || canonical_payload_bytes` とし、domain は `agent-canon`、schema は `skill-tool-invocation-graph.v2`、`digest=SHA-256(IdentityPreimage)` とする。preimage は digest field を含まず、domain、schema、stable semantic `id`、`kind`、canonical payload をこの順に含み、各 field 間の separator は一つの NUL byte とする。
- 同一 `kind,id` かつ canonical preimage bytes が byte-for-byte 同じ場合だけ `duplicate_same_payload` として一件に収束する。同一 `kind,id` の preimage が一 byte でも異なれば `identity_collision`、異なる preimage が同じ digest を持てば `digest_collision`、同じ digest field が preimage と一致しなければ `digest_mismatch` とする。異なる IDで同じ identity payload を指せば `alias_or_identity_collision`、同じ normalized alias が別 target を指せば `alias_collision`、同じ edge/ToolCall IDで relation/args が違えば typed collision、projection/envelope に payload-bearing field があれば `payload_duplicate` として fail する。
- payload duplicate detection は `(kind,payload)` ではなく、全 kind 共通の canonical payload bytes index を使う。従って異なる kind が同じ canonical payload bytes を持つ cross-kind witness も `identity_collision`/`payload_duplicate` として fail する。

### Acyclic digest DAG and artifact readback

digest dependency は `identity preimages → ordered Ref/edge envelopes → graph payload → generated JSON artifact` とする。identity digest を先に確定し、ordered `Ref`、`EdgeProjection`、node/phase/command/tool projection envelope を canonicalize して envelope digest を計算し、その digest refs と counts から graph payload digest を計算する。generated JSON artifact は graph/coverage/projection digest refs と compact projectionsを含むが、JSON artifact 自身の `json_digest` field、`readback` envelope、Mermaid artifact digest は JSON digest preimage から除外して `json_digest=SHA-256(canonical_json_without_json_digest_readback_or_mermaid_digest)` とする。

Mermaid は graph digest と coverage digest の Ref だけを artifact metadata として保持し、`json_digest`、full JSON payload、artifact digest を保持しない。Mermaid の generated node/edge statements そのものから labels、Ref digest、explicit order、source/target を parser readback が再構成して projection identity digest を計算し、graph/coverage digest refs と比較する。`%%` comments は補助的な diagnostics に過ぎず、syntax statement を削除して comments だけ残した artifact は失敗する。readback は観測した JSON/Mermaid bytes digest を `ReadbackEnvelope` の digest として記録できるが、JSON artifact は Mermaid digest を入力にせず、Mermaid は JSON digest を入力にしない。従って JSON↔Mermaid に循環依存はなく、両方が同じ graph/coverage digest DAG の下流 projection となる。

## Invariants

- `SG-002` `catalog.yaml` は skill と catalog-owned command identity の唯一の owner、`skill-dependencies.yaml` は dependency/order/routing/parallel relation の唯一の owner、[agents/canonical/skills.md](../../agents/canonical/skills.md) は reader/index link parity target とする。
- `SG-003` 各 payload は一つの `IdentityRecord {id,digest,kind,canonical_payload}` に一度だけ保存し、全 consumer は `Ref {id,digest}` を参照する。projection envelope は Ref + compact display fields、edge projection は edge/source/target Ref + compact label に限る。
- `SG-004` durable artifact は logical repository-relative locator のみ、absolute runtime path は execution 時だけとする。
- `SG-005` canonical serialization は field order、NFC/identifier normalization、UTF-8、domain-separated digest、array ordering を上記規則に従う。
- `SG-006` duplicate/collision/alias ambiguity は silent merge せず typed failure とする。prose keyword は reject-only guard であり adapter、capability、skill、ToolID の選択に使わない。
- `SG-007` typed capability owner と phase が確定してから adapter、ToolCall、実行を materialize する。adapter は owner の代わりに capability を発見しない。
- `SG-008` dependency、order、routing、owner-before-adapter、owner relation、parallel edge は source owner と resolved owner relations の実際の集合を保持し、prompt や hand-authored Mermaid で再定義しない。
- `SG-009` source、JSON、Mermaid、skills.md reader/index links は同一 source snapshot と digest refs を持つ。skills.md は skill-count projection ではなく link parity target であり、差分は stale/reader-link failure とする。
- `SG-010` Mermaid は checker が source universe から生成した実際の全 nodes/edges/order の projection であり、compact labels、一つの complete block、full-manifest base64 の不在を満たす。
- `SG-011` checker は source↔materialized IR↔JSON↔Mermaid の identity/edge/order equality、current input digest、skills.md reader/index link parity、actual coverage を readback する。欠落・未知・重複・payload duplicate・stale は fail-closed とする。
- `SG-012` #461 で固定された log command order は immutable edge/order として `ensure → status → stage → snapshot → commit → compare/rebase → push → readback → check-clean` を保持する。外部 preflight と内部 transaction の境界を graph が混ぜない。
- `SG-013` graph、manifest、coverage、readback、design handoff は同じ snapshot の identity/digest を参照し、stale artifact の再利用・silent refresh・partial success を許さない。
- `SG-014` selected design clause fingerprint は graph snapshot に結び付き、implementation handoff の target/evidence と forward/reverse coverage を持つ。
- `SG-015` identity digest、Ref/edge envelope digest、graph payload digest、JSON artifact digest、Mermaid readback digest は acyclic dependency order を守り、JSON↔Mermaid の相互 digest 依存を持たない。

## Side Effects

source read、normalization、digest、JSON/Mermaid projection、coverage/readback は deterministic artifact side effect である。route/ToolCall の実行、absolute path resolve、runtime-log publication は execution side effect であり、durable identity payload を mutate しない。planned checker が生成する projection は source owner を変更せず、source snapshot と生成 artifact の digest/readback を記録する。関係する owner は `tools/agent/skills/skill_dependency_map.py` と `tools/validation/semantic/runtime/check_agent_runtime_alignment.py` である。

## Failure Semantics and prose guard

| failure | result | readback |
| --- | --- | --- |
| catalog skill/command missing or unknown | `unresolved_source` / `failed` | catalog locator、source snapshot、欠落 ID |
| relation/ToolID/phase/edge missing, unknown, or stale | `coverage_or_relation_stale` / `failed` | source and resolved owner relations digests |
| same ID with different payload, alias, edge, or ToolCall collision | `identity_collision` / `failed` | all colliding IDs/digests |
| embedded payload/base64 or absolute durable locator | `payload_embedded` / `absolute_locator` / `failed` | violating artifact locator |
| adapter/capability selected before typed owner | `owner_order` / `blocked` | owner, adapter, phase edges |
| prose keyword or existing description selected a route | `keyword_only_route` / `blocked` | reject-only guard match; no adapter verdict |
| JSON/Mermaid projection identity or digest-DAG readback differ | `projection_mismatch` / `digest_dag_cycle` / `failed` | graph/coverage refs, recomputed projection identities, and artifact digests |
| source/JSON/reader-link parity digest changed | `stale_artifact` / `reader_link_parity` / `failed` | changed input digest, catalog/IR digest, and selected snapshot |
| projection/envelope contains canonical payload or full ToolCall/edge data | `payload_duplicate` / `failed` | projection Ref and offending field; canonical `IdentityRecord` locator |
| immutable #461 order changed | `owner_order_drift` / `blocked` | ordered edge sequence and clause `SG-012` |

既存の prose terms（`purpose`、`description`、`triggers`、`keyword`、`related`、`adapter` を含む）は compatibility 用の reject-only guard である。guard は無効な入力を拒否するだけで、adapter/capability/ToolID/skill を選ばない。選択は `agents/skills/catalog.yaml`、`agents/skills/skill-dependencies.yaml`、`tools/agent/orchestration/route.py` の explicit identity と relation に限る。

## Checker Contract: Inputs / Outputs / Equality


出力は `agent_canon.skill_tool_invocation_check.v1` の JSON とし、field order は `schema,source_snapshot,counts,identity_digests,edge_order_digest,json_digest,mermaid_digest,reader_link_parity_digest,projection_digests,failure_refs,unresolved_refs,status`、各配列は canonical sort とする。`counts` は catalog/materialized IR の catalog-derived な `skills` と `commands`、さらに resolved `capabilities/tools/toolcalls/phases/edges` の実測 count を持つ。`skills.md` の行数を skill/command count に使わない。failure detail は IdentityRecord として一度だけ保存し、output は `failure_refs` を持つ。


## Current Catalog Inventory (readback evidence)

現行の skill 集合・source order は `agents/skills/catalog.yaml`、関係は
`agents/skills/skill-dependencies.yaml` から読みます。件数と生成 projection の一致は
上記 [Checker Contract](#checker-contract-inputs--outputs--equality) の実際の出力で確認します。
この設計文書へ全件一覧の snapshot を複写せず、追加・廃止に追従する別の一覧を保守しません。
生成・readback の証拠は対象 source snapshot とともに既存 artifact owner へ保存し、
[Artifact side-effect boundary](#artifact-side-effect-boundary) の外部出力と tracked pair の境界を保持します。

## Complete Mermaid Projection Contract


```mermaid
flowchart LR
  D["skill-dependencies.yaml\nrelation owner"] --> U
  P["skills.md\nreader/index links"] --> K["equality checker"]
  U --> G["graph payload digest\ncoverage refs"]
  G --> J["canonical JSON\nordered fields digests refs"]
  J --> K
  M --> K
  K -->|equal current| A["accept readback"]
  K -->|missing stale collision| F["fail closed"]
```

## Design-To-Implementation Trace

| clause | current/planned implementation owner | exact file / symbol | reverse mapping rule |
| --- | --- | --- | --- |
| `SG-004..SG-006` | current serialization/identity owner | `tools/agent/skills/skill_dependency_map.py:_canonical_bytes`, `_canonicalize`, `_identity_preimage`, `_IdentityStore` | field order, normalization, digest, duplicate, or collision changes require these clauses |
| `SG-009..SG-011` | current projection/readback owner | `tools/agent/skills/skill_dependency_map.py:render_graph_mermaid`, `:_parse_mermaid_syntax`, `:readback_mermaid`; `tools/validation/semantic/skills/check_skill_tool_invocation_graph.py` | any JSON/Mermaid/source/skills.md equality, stale, count, or generated-node change maps to these clauses |
| `SG-012` | current log lifecycle owner | `tools/runtime/archive/runtime_log_archive_git.py`, [documents/design/runtime-log-repository-lifecycle.md](runtime-log-repository-lifecycle.md) | command order or preflight/transaction boundary changes map to SG-012 and the corresponding RL clause |
| `SG-013..SG-014` | current handoff and review owners | `tools/agent/skills/skill_dependency_map.py:build_graph`, `tools/validation/semantic/skills/check_skill_tool_invocation_graph.py`, [agents/internal-routines/design-implementation-correspondence.md](../../agents/internal-routines/design-implementation-correspondence.md) | manifest/readback/design-fingerprint changes map to the clause before implementation |
| `SG-015` | current digest/readback owner | `tools/agent/skills/skill_dependency_map.py:_identity_preimage`, `:_json_digest_from_graph`, `:_parse_mermaid_syntax`, `:readback_mermaid`; `tools/validation/semantic/skills/check_skill_tool_invocation_graph.py` | digest preimage, DAG level, JSON self-digest/readback/Mermaid-digest exclusion, Mermaid ref-only metadata, or circular-readback changes map to SG-015 |

### Implementation record and forward/reverse mapping

この実装は AgentCanon final main `eeb451bd4b829e5417b810804a9d67dfb4ba570d` を設計入力として、設計文書の trace を変更する前の SHA-256 `a28cf776915d006aaffe868185816601c8feb11c7c4375b00b6caf18805c1506` に対応付けて記録します。生成 schema は `agent_canon.skill_tool_invocation_graph.v2` です。実装時点の design SHA-256 は generated graph の `design_correspondence.design_sha256` に保存し、DIC-001..DIC-009 の target/validation logical-path、全 explicit adapter の ToolID/schema、clause fingerprint、forward/reverse review をこの表と checker で満たします。

Explicit adapter correspondence is part of the trace and is validated before graph materialization. The typed visualization owner is always emitted first; only the selected adapter follows it.

| adapter ToolID | argument schema | route/materialization evidence |
| --- | --- | --- |
| `agent_canon.visualization.adapter.dependency_manifest` | `agent_canon.visualization.arguments.dependency_manifest.v1` | `tools/agent/skills/skill_route_catalog.py:build_visualization_adapter_tool_call`; `tools/agent/orchestration/capability_route.py:decide_capabilities` |
| `agent_canon.visualization.adapter.algorithm_flowchart` | `agent_canon.visualization.arguments.algorithm_flowchart.v1` | `tools/agent/skills/skill_route_catalog.py:build_visualization_adapter_tool_call`; `tools/agent/orchestration/route.py:decide_skills` |
| `agent_canon.visualization.adapter.document_mermaid` | `agent_canon.visualization.arguments.document_mermaid.v1` | `tools/agent/skills/skill_route_catalog.py:build_visualization_adapter_tool_call`; `tools/agent/orchestration/route.py:decide_skills` |
| `agent_canon.visualization.adapter.repository_graph` | `agent_canon.visualization.arguments.repository_graph.v1` | `tools/agent/skills/skill_route_catalog.py:build_visualization_adapter_tool_call`; `tools/agent/orchestration/route.py:decide_skills` |
| `agent_canon.visualization.adapter.knowledge_graph` | `agent_canon.visualization.arguments.knowledge_graph.v1` | `tools/agent/skills/skill_route_catalog.py:build_visualization_adapter_tool_call`; `tools/agent/orchestration/route.py:decide_skills` |

The correspondence checker covers `DIC-001`, `DIC-002`, `DIC-003`, `DIC-004`, `DIC-005`, `DIC-006`, `DIC-007`, `DIC-008`, and `DIC-009`, plus these changed paths in both forward and reverse mappings: `agents/skills/catalog.yaml`; `documents/design/skill-tool-invocation-graph.md`; `documents/runtime/skill-dependency-graph.json`; `documents/runtime/skill-dependency-graph.md`; `tests/agent_tools/test_route.py`; `tests/agent_tools/test_skill_dependency_map.py`; `tools/validation/semantic/skills/check_skill_tool_invocation_graph.py`; `tools/agent/orchestration/capability_route.py`; `tools/agent/orchestration/route.py`; `tools/agent/skills/skill_dependency_map.py`; and `tools/agent/skills/skill_route_catalog.py`. Missing clause, DIC, adapter, or path coverage is a typed `design_correspondence_missing` failure.

| forward clause | implementation target (logical locator / symbol) | focused evidence / validation route | reverse trigger |
| --- | --- | --- | --- |
| `SG-004..SG-006` | `tools/agent/skills/skill_dependency_map.py:_IdentityStore`, `_canonical_bytes`, `_canonicalize`, `_identity_preimage` | `test_identity_payloads_are_unique_and_all_projections_are_refs`; typed collision/reference, insertion-order, and Unicode-alias tests | any payload duplication, Ref, Unicode/field-order, or digest-preimage change |
| `SG-007..SG-008` | `tools/agent/orchestration/route.py:decide_skills`; `tools/agent/skills/skill_route_catalog.py:build_visualization_adapter_tool_call`; `tools/agent/orchestration/capability_route.py:decide_capabilities`; `skill_dependency_map.py:_build_owner_and_adapter_calls`, `_add_edge` | capability route, every explicit adapter ToolID/schema, owner-before-adapter ToolCall, seven edge-type and ordering checks | any route, ToolCall, phase, edge, or untyped adapter heuristic change |
| `SG-009..SG-011` | `skill_dependency_map.py:render_graph_mermaid`, `:_parse_mermaid_syntax`, `:readback_mermaid`, `check_artifacts` | actual one-block Mermaid syntax readback; JSON/Mermaid exact equality and stale/omission failure | any node/edge/order/coverage/readback or generated-artifact change |
| `SG-013..SG-014` | [documents/design/skill-tool-invocation-graph.md](skill-tool-invocation-graph.md) trace; `tools/validation/semantic/skills/check_skill_tool_invocation_graph.py` | `CHECK_SCHEMA=agent_canon.skill_tool_invocation_check.v1`; DIC trace and generated readback | any manifest/readback/design fingerprint or correspondence target change |
| `SG-015` | `skill_dependency_map.py:_identity_preimage`, `:_json_digest_from_graph`, `:_parse_mermaid_syntax`, `:readback_mermaid` | graph/json/Mermaid digest equality, JSON preimage excludes self/readback/Mermaid digest, no absolute locator/base64 marker | any preimage, DAG layer, self-digest, Mermaid syntax, or readback change |


## Evidence And Assumption Ledger

| kind | statement | evidence / owner | status |
| --- | --- | --- | --- |
| current state | `catalog.yaml` の `skill_families` が source skill universe で、`skill-dependencies.yaml` は同じ skill id 集合を relation owner とする | `agents/skills/catalog.yaml`, `agents/skills/skill-dependencies.yaml` | checked |
| target state | source/JSON/Mermaid equality と generated actual nodes/edges/order は `tools/validation/semantic/skills/check_skill_tool_invocation_graph.py` が readback する | `SG-009..SG-011`, `SG-015` | checked |
| assumption | `normalization` / `正規化` は本文の canonical serialization に定義した Unicode NFC/NFKC、casefold、UTF-8 の手順を指す | `SG-005`, `SG-006` | explicit |

## Clause IDs

この文書の design clauses は `SG-001` から `SG-015` です。clause、current/planned owner、source locator、reverse evidence は同一変更で更新し、個別 skill にこの契約を複製しません。
