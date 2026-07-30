<!--
@dependency-start
contract policy
responsibility Defines the language-neutral semantic Docstring contract, its canonical template skeleton, and its language projection trace.
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ../rule/README.md document filename, placement, and language rules
upstream design ../design/cpp-build-layout.md selects derived-repo native C++ target identities and build layout
upstream design ../../agents/skills/catalog.yaml selects reviewer capabilities for the touched surface
upstream design ../../agents/skills/skill-dependencies.yaml selects reviewer prerequisite and dependency order
downstream implementation ../../templates/README.md indexes template projection consumers and sparse Docstring boundaries
downstream design ./coding-conventions-python.md projects the contract into Python docstring syntax and public-surface rules
downstream design ./coding-conventions-cpp.md projects the contract into C++ documentation syntax and native-boundary rules
downstream implementation ../../templates/documents/design-document.template.md consumes the semantic skeleton in the reusable design template
downstream implementation ../../templates/experiments/_template/run.py projects the contract into the later Python code template
downstream implementation ../../templates/experiments/_template/cases.py projects the contract into the later Python module template
downstream implementation ../../tools/ci/run_python_quality_checks.sh checks language-level Python docstring presence and style
downstream design ../../agents/skills/python-review.md reviews Python semantic projection when its changed-surface route is selected
downstream design ../../agents/skills/cpp-review.md reviews C++ semantic projection when its changed-surface route is selected
downstream design ../../agents/skills/oop-type-design.md selects language-neutral responsibility and type boundaries before projection
@dependency-end
-->

# Docstring Semantic Contract

## Reader map

この文書は、Docstring の意味契約、再利用可能な template skeleton、言語 adapter への
投影、review の判定境界を所有します。

- **設計者**: `Semantic Contract` と `Reviewer Decision Matrix` で、コードの意味から必要な
  clause を導出します。
- **実装者**: `Canonical Template Skeleton` を起点に、意味のある clause だけを実装
  Docstring へ投影します。
- **language reviewer**: Python / C++ の adapter が意味を保持しているかを確認します。
- **reviewer / maintainer**: `Forward / Reverse Trace` を閉じ、コード・設計・Docstring の
  不整合を判定します。

`documents/conventions/DOCSTRING_GUIDE.md` は semantic contract と template skeleton の
唯一の owner です。language convention は syntax / format projection、template は
projection consumer であり、同じ契約を再定義しません。

## Ownership and fixed projection paths

| responsibility | canonical owner or projection path | role |
| --- | --- | --- |
| semantic contract | `documents/conventions/DOCSTRING_GUIDE.md` | 唯一の正本 |
| canonical template skeleton | `documents/conventions/DOCSTRING_GUIDE.md#canonical-template-skeleton` | 言語非依存の clause source |
| reusable document-template projection | `templates/documents/design-document.template.md` | 後続実装で skeleton を参照する既存 template |
| Python adapter projection | `documents/conventions/coding-conventions-python.md` | Python docstring syntax / format |
| C++ adapter projection | `documents/conventions/coding-conventions-cpp.md` | C++ documentation syntax / native format |
| Python code-template projection | `templates/experiments/_template/run.py` | 後続実装で runtime code へ投影 |
| Python module-template projection | `templates/experiments/_template/cases.py` | 後続実装で module responsibility を投影 |
| Python public surface | `documents/conventions/coding-conventions-python.md` | `__all__` と公開 export の owner |

`__all__` は Docstring contract の一部ではありません。Python public surface owner へ
分離し、Docstring 側では公開名、namespace、field、annotation を再掲しません。

## Semantic contract

Docstring は型名や namespace の説明ではなく、読者が実装の意味を再構築するための
最小の責務契約です。次の clause は固定欄ではなく、実装・設計との意味関係がある場合
だけ記載します。

| clause | 記載する意味 |
| --- | --- |
| responsibility | この unit が存在する責務と観測可能な目的 |
| precondition | 呼び出し側が満たすべき、コードだけでは自明でない条件 |
| postcondition | 戻り値、状態、出力について呼び出し後に成立する条件 |
| invariant | 呼び出し前後または lifecycle 中に保持される条件 |
| side effect | I/O、mutation、cache、logging、environment、randomness、subprocess 等 |
| failure semantics | exception、error code、partial effect、retry、rollback、fail-closed の意味 |
| ownership / lifetime | resource、pointer、view、callback、borrow、transfer、release の責任 |
| algorithm / design | correctness が algorithm、近似、順序、収束、数値安定性、設計 clause に依存する場合 |

次の内容は Docstring の責務ではありません。

- signature、annotation、namespace、access modifier、inheritance、field の全列挙
- compiler / type checker が既に検証する型事実
- 全引数・全属性・全 method・全例外の機械的な列挙
- 使用例の一律要求、長い narrative、実装行の逐語的な説明

## Semantic delta and non-enforcement

Docstring が保持するのは、code、type、signature、namespace、または design trace の
静的表現からは導出できない semantic delta だけです。既に読める事実を言い換えるため
の説明、design trace の複製、全欄の穴埋めは契約ではありません。

- semantic delta が responsibility 以外にない自明な unit は、短い responsibility だけで
  completion とします。
- 自明な function に長文、全 clause、全引数説明、全例外説明を強制しません。
- `omit` は不足ではなく、静的表現または既存 design evidence から追加の意味が導けない
  ことを確認した正の判断です。
- design trace は対応関係と根拠を保持する owner surface であり、trace ID、path、owner
  metadata、または同じ文章を Docstring に再掲しません。必要な意味だけを projection
  します。

したがって、Docstring の性能は行数、見出し数、coverage、`Args` / `Returns` token 数では
なく、必要な semantic delta のみで読者の判断を成立させることを評価します。

## Reviewer decision matrix

Reviewer は module / class / function という有限の Docstring 種別から欄を選びません。
実装、design clause、observable effect の意味関係から、各 target / clause / adapter の
projection 要否を導き、後述の sparse trace record として materialize します。同一
Docstring に複数の関係が同時に成立してよく、関係がなければ追加 clause の projection
は作りません。この matrix は関係を導く decision aid であり、結果分類や文章量・欄数を
増やす checklist ではありません。

| evidence in code or design | decision relation | clause | reviewer question |
| --- | --- | --- | --- |
| state transition、mutable state、lifecycle、aggregate operation | transition changes an observable state or preserves a state rule | postcondition / invariant | 遷移後の状態と保持条件が読者に復元できるか |
| pure function with a nontrivial return、output、or result condition | result meaning is not derivable from the signature, types, or an obvious expression | postcondition | 副作用がなくても、返却結果の成立条件をコード再解析なしに判断できるか |
| file/network/database/process access、mutation、cache、logging、environment access | operation crosses or changes an external boundary | side effect | effect の owner、trigger、順序、失敗時の残存状態が分かるか |
| resource、pointer、view、iterator、callback、handle、lock、buffer | value or callback crosses a lifetime/ownership boundary | ownership / lifetime | borrow、transfer、release、alias、callback lifetime が誤読されないか |
| exception、error result、partial write、retry、rollback、timeout、fail-closed | failure changes caller action or persisted state | failure semantics | failure 条件、partial effect、retry/rollback の意味が一致するか |
| algorithm、approximation、ordering、convergence、numerical stability、proof/design clause | correctness depends on a non-obvious design choice | algorithm / design | どの設計条件を守る必要があるか、正本へ辿れるか |
| non-obvious input normalization, precondition, unit, valid range | caller obligation is not evident from the signature | precondition | 境界で守るべき条件が明示されているか |
| none of the above and no non-obvious public behavior | responsibility is sufficient; any omitted clause needs static-surface evidence | no additional clause | 不要な projection を足さず、省略根拠を trace へ残しているか |

clause の owner、partial-effect semantics、algorithm/design source、または public
contract が未確定で、実装者が Docstring で補ってはいけない場合は、trace record の
`projection.materialization=owner_returned` として設計 owner へ返します。

### Sparse trace record schema

各 target × clause × adapter について、次の最小 record を materialize します。これは
`include` / `omit` / `escalate` の分類表ではなく、projection の存在、省略、owner 返却を
正の結果として保持する sparse record です。適用しない詳細 field は空欄で埋めず省略し、
core identity と reviewer decision は常に残します。

```yaml
docstring_trace_record:
  record_id: <stable trace identifier>
  target:
    identity: <repo-relative path:qualname:span or responsibility region>
    responsibility_region: <cohesive implementation boundary>
  clause:
    canonical_name: <responsibility|precondition|postcondition|invariant|side_effect|failure|ownership_lifetime|algorithm_design>
    relation: <semantic relation derived from the reviewer matrix>
    semantic_delta: <meaning not recoverable from the static surface>
  adapter:
    kind: <document-template|python|cpp>
    owner_path: <adapter or template owner path>
    projection_path: <consumer path>
    projection_anchor: <section|qualname|comment anchor or null>
  evidence:
    source_anchor: <code, design clause, or static-surface path:line>
    observation: <state/effect/failure/ownership/result fact>
    static_surface: <what code/type/signature/namespace/design trace already exposes>
  rationale:
    projection_basis: <why this semantic delta is reader-relevant>
    duplication_check: <why the projection does not copy an owner fact>
    omission_evidence: <required when materialization is omitted>
    owner_return_reason: <required when materialization is owner_returned>
  projection:
    materialization: <present|omitted|owner_returned>
    text_or_reference: <projected clause, omission record, or owner packet reference>
  reviewer_decision:
    reviewer: <catalog-selected reviewer or design owner>
    evidence_ref: <review/readback evidence path or record id>
    decision_note: <why this materialized result closes or returns the projection>
```

`materialization=omitted` は、`evidence.static_surface` に semantic delta が十分表現
済みであること、または追加 clause が同じ情報を重複することを明記した場合だけ有効です。
`materialization=owner_returned` は未確定 contract の owner path と理由を持ちます。
`materialization=present` は adapter の projection anchor と reader-visible clause を
持ちます。これらは materialized result の値であり、Docstring 全体へ一律適用する欄の
分類ではありません。

## Canonical template skeleton

この skeleton は固定全欄の form ではなく、責務と意味関係から必要な snippet を合成・
選択する language-neutral な構造です。まず responsibility を置き、reviewer decision
matrix で必要と判断された snippet だけを追加します。角括弧は optional であり、
意味関係がなければ省略します。

```text
Docstring := ResponsibilitySnippet
             [ + PreconditionSnippet ]
             [ + PostconditionSnippet ]
             [ + InvariantSnippet ]
             [ + SideEffectSnippet ]
             [ + FailureSnippet ]
             [ + OwnershipLifetimeSnippet ]
             [ + AlgorithmDesignSnippet ]

ResponsibilitySnippet      := <one concise responsibility sentence>
PreconditionSnippet        := <caller obligation not evident from static expression>
PostconditionSnippet       := <non-obvious result or state condition after the operation>
InvariantSnippet           := <state or lifecycle rule preserved across the operation>
SideEffectSnippet          := <I/O, mutation, cache, logging, environment, or randomness>
FailureSnippet             := <failure condition and partial/retry/rollback meaning>
OwnershipLifetimeSnippet  := <borrow, transfer, release, alias, or callback lifetime>
AlgorithmDesignSnippet     := <non-obvious correctness, ordering, convergence, or design rule>
```

Snippet は matrix の意味関係から選択し、同じ関係に対応する複数の snippet は必要な
範囲で合成できます。`ResponsibilitySnippet` 以外に semantic delta がなければ、生成物
は responsibility の一文だけです。空欄を埋めること、固定順序を守ること、各 snippet
を一度ずつ使うことは completion 条件ではありません。matrix で選択された結果を
sparse trace record へ materialize してから language adapter の syntax へ投影します。

この skeleton の reusable document-template projection target は
`templates/documents/design-document.template.md` です。そこへ semantic clause をコピー
して第二正本を作らず、contract owner への参照と projection/trace 欄だけを後続実装で
追加します。

## Projection consumers and acceptance trace

document-template、Python、C++ は別々の projection consumer です。semantic contract と
matrix はこの guide に残し、各 consumer は syntax、format、責務領域、projection anchor、
acceptance trace だけを持ちます。

### Document-template projection

- consumer: `templates/documents/design-document.template.md`
- responsibility region: authority / decision status、target state、OOP/type boundary、
  dependency/effect、adversarial review、reconstruction、acceptance、evidence ledger
- acceptance trace: `adapter.kind=document-template` とし、template section anchor と
  design clause の source anchor を record に保存します。semantic clause 本文をこの
  templateへ複製せず、canonical guide への owner reference と projection/trace 欄だけを
  後続実装で追加します。

### Python projection

- adapter owner: `documents/conventions/coding-conventions-python.md`
- consumer: `templates/experiments/_template/run.py`、
  `templates/experiments/_template/cases.py`
- responsibility regions: `run.py` の `compact_timestamp` / `resolve_run_dir`（結果と
  output directory 条件）、`run_case_worker`（case result、worker-local effect）、
  `run_experiment`（case dispatch と artifact write）、
  `execute_visualization_notebook`（subprocess / notebook artifact）、
  `require_managed_runner_route`（failure semantics）、`main`（orchestration boundary）、
  `cases.py` の module-level case-definition region
- acceptance trace: `adapter.kind=python`、qualname/responsibility region、Python
  projection anchor、selected catalog reviewer、static-surface evidence を一つの record
  に保存します。後続実装では既存 Python docstring prose をこの consumer projection
  へ変換し、language convention に残った semantic duplicate owner を削除します。

### C++ projection

- adapter owner: `documents/conventions/coding-conventions-cpp.md`
- native-consumer join: `documents/design/cpp-build-layout.md` が派生 repo の C++ target
  identity を選び、`cpp/include/<project>/...` または `cpp/src/...` の native source/header
  surface とこの adapter projection を結びます。
- responsibility regions: public header の declaration / ownership boundary と、source
  implementation の algorithm / failure / native side effect boundary
- acceptance trace: `adapter.kind=cpp`、header/source anchor、Doxygen projection、native
  ownership/header evidence、selected catalog reviewer を record に保存します。後続実装
  では既存 C++ docstring/comment prose をこの projection consumer へ変換し、C++ convention
  側の semantic duplicate owner を削除します。AgentCanon C++ scaffold は、この build
  design が owner と target identity を定義した場合に限り、別 change として追加します。

## Evidence And Assumption Ledger

normalization の意味、owner、evidence、validation を、次の短い structured ledger で固定
します。record は必要な根拠だけを保持し、説明文や path の重複を増やしません。

| id | normalization meaning | owner | evidence | validation |
| --- | --- | --- | --- | --- |
| DAL-01 | C++ native consumer は build design が選ぶ `cpp/include/<project>/...` / `cpp/src/...` target identity に正規化する | `documents/design/cpp-build-layout.md` | dependency graph の upstream design edge と design document source anchor | fresh graph、`check_design_doc_claims.py`、C++ review selected by catalog |
| DAL-02 | C++ Docstring projection は syntax / format と native target anchor の join に正規化する | `documents/conventions/coding-conventions-cpp.md` + `documents/design/cpp-build-layout.md` | C++ projection record の adapter owner、target identity、header/source anchor | design claim checker と C++ adapter readback |
| DAL-03 | reviewer 選択は changed-surface evidence を catalog/capability projection へ正規化する | `agents/skills/catalog.yaml` + `agents/skills/skill-dependencies.yaml` | materialized route packet と dependency order | `tools/agent_tools/route.py` と orchestration check |
| DAL-04 | projection の省略は static surface に semantic delta が十分表現済みという record に正規化する | `documents/conventions/DOCSTRING_GUIDE.md` | sparse trace の `static_surface`、`omission_evidence`、reviewer decision | docs check、prose readback、design claim checker |

## Language projection boundary

Python adapter は Google/NumPy/PEP 257 互換の syntax、`Args`、`Returns`、`Raises`、
`Yields`、indentation、quote style を選びます。C++ adapter は Doxygen-compatible
comment、declaration/header placement、exception/error wording を選びます。
どちらの adapter も semantic clause の追加条件、ownership 判断、failure の意味を
独自に変更しません。

Python adapter の `__all__`、public export、package surface は
`documents/conventions/coding-conventions-python.md` が所有します。C++ adapter の
ABI/header/native ownership の詳細は `documents/conventions/coding-conventions-cpp.md`
が所有します。

## Skill routing boundary

skill routing の唯一の選択面は canonical catalog / capability projection です。routing
input は changed surface、language、type boundary、design clause relation、projection
kind とし、catalog が materialize した selected capability と dependency order をそのまま
利用します。

| routing owner | projection input / result |
| --- | --- |
| `agents/skills/catalog.yaml` | public skill/capability identity and capability projection |
| `agents/skills/skill-dependencies.yaml` | prerequisite, successor, and dependency order |
| `tools/agent_tools/route.py` | request plus changed-surface evidence to materialized route packet |

catalog が返した capability projection が language-neutral design、Python、C++、または
Markdown の reviewer scope を決めます。selected route と dependency order が reviewer
起動、static type facts、format facts、semantic contract judgement の owner boundary を
定め、guide はその materialized result を利用します。

## Validation and review boundary

- `pydocstyle` と Ruff D は、language-level の存在・syntax・format signal を検証する。
- `pyright` と C++ compiler/build は、annotation、signature、namespace、header、ABI の
  static fact を検証する。
- OOP/readability checker は責務境界の signal を提供するが、clause の意味充足を判定しない。
- semantic clause の妥当性、設計との整合、side effect/failure/ownership の完全性は
  selected reviewer が判定する。
- 全引数・全属性・`Args`/`Returns` token の存在を意味契約の gate にしない。
- 実装 mechanism が存在し、なお未解決の behavior oracle がある場合だけ test design を
  追加する。Docstring prose 自体を test-first の対象にしない。

### Performance and non-enforcement evaluation

性能評価は Docstring の行数や clause 数ではなく、次の読者結果で行います。

1. **Decision sufficiency**: 読者が code を再解析せず、該当する design clause、side
   effect、failure semantics、ownership / lifetime を判断できる。
2. **Semantic economy**: code、type、signature、namespace、design trace から導出できる
   情報を重複記載せず、必要な semantic delta だけを保持する。
3. **Minimal completion**: 契約差分がなければ短い responsibility で閉じ、長文や全 clause
   を要求しない。
4. **Projection fidelity**: 選択した snippet が Python / C++ adapter の syntax へ投影
   されても、canonical owner の意味・failure・ownership 判断を変えない。

行数、coverage、見出し数、`Args` / `Returns` token 数、全欄の存在は性能指標でも gate
でもありません。reviewer decision matrix は semantic relation を導くために使い、
文章量を増やすチェックリストとして使いません。

## Positive completion and design trace

Completion は欄の充足率ではなく、次の forward/reverse correspondence が閉じることです。
責務以外の semantic delta がない場合は responsibility-only の対応で閉じ、projection の
省略は static-surface evidence を持つ正の materialized result になります。

1. **Forward**: canonical template skeleton の各 selected clause が、対象実装の
   `path:start-end:qualname` または cohesive responsibility region と、language adapter
   の Docstring clause へ対応する sparse trace record を持つ。
2. **Reverse**: 実装・design evidence に現れる state transition、pure-function result、
   effect、ownership、failure、algorithm/design condition が、projection present record、
   static-surface evidence 付き omission record、または owner-return record のいずれかへ
   戻れる。
3. **Consistency**: Docstring が design clause にない保証、effect、failure、ownership を
   発明していない。未確定の内容は owner-return record として設計 owner へ戻る。
4. **Readback**: template source、adapter projection、実装 Docstring、review decision、
   fresh graph を同じ対象 trace で再読し、forward/reverse の欠落を closeout 前に解消する。

### Design-to-implementation trace

| trace id | source / design clause | current canonical path | later projection consumer | acceptance evidence |
| --- | --- | --- | --- | --- |
| DSC-01 | semantic contract, matrix, sparse record schema | `documents/conventions/DOCSTRING_GUIDE.md` | same section remains the source | record core fields and relation readback |
| DSC-02 | canonical skeleton | `documents/conventions/DOCSTRING_GUIDE.md#canonical-template-skeleton` | `templates/documents/design-document.template.md` | document-template record with section anchor |
| DSC-03 | document-template responsibility region | this section | `templates/documents/design-document.template.md` | authority/target/acceptance section trace |
| DSC-04 | Python syntax/public surface | `documents/conventions/coding-conventions-python.md` | `templates/experiments/_template/run.py`, `cases.py` | Python record per responsibility region and adapter readback |
| DSC-05 | C++ syntax/native boundary and build-design join | `documents/conventions/coding-conventions-cpp.md` + `documents/design/cpp-build-layout.md` | derived-repo `cpp/include/<project>/...` / `cpp/src/...` target identity | C++ record with build-design anchor and header/source trace |
| DSC-06 | existing prose migration | this guide plus language convention owners | existing Python/C++ prose converted into projection consumers | duplicate semantic owner removed and adapter record retained |
| DSC-07 | reviewer routing | catalog, capability, and dependency owners | catalog-materialized route packet | no keyword branch or all-reviewer activation |
| DSC-08 | positive completion | this section | implementation Docstring and review artifact | every relation has present/omitted/owner-return record |
| DSC-09 | fresh graph/readback | `Fresh graph and readback route` | dependency graph and source readback artifacts | fresh status, graph query, docs/header checks |

### Subsequent write set

The following files are intentionally later work, not this design-phase change:

- `templates/documents/design-document.template.md`
- `templates/experiments/_template/run.py`
- `templates/experiments/_template/cases.py`
- `documents/conventions/coding-conventions-python.md`
- `documents/conventions/coding-conventions-cpp.md`
- `agents/skills/oop-type-design.md`
- `agents/skills/python-review.md`
- `agents/skills/cpp-review.md`

This list is a trace target, not permission to edit those files in the current revision.
AgentCanon C++ scaffold はこの write set に含まず、`cpp-build-layout.md` の owner decision 後に
別 change として設計します。

## Fresh graph and readback route

Source or reader-map changes invalidate the previous graph. Regenerate before consuming
dependency facts, then read back the exact owner and projection edges:

```bash
CARGO_TARGET_DIR=<task-local-cargo-target> tools/bin/agent-canon graph build --root . --format json
CARGO_TARGET_DIR=<task-local-cargo-target> tools/bin/agent-canon graph status --root . --profile default --format json
CARGO_TARGET_DIR=<task-local-cargo-target> bash tools/agent_tools/check_dependency_graph.sh --changed --print-edges
```

After graph publication, rerun dependency-header checks and `agent-canon docs check` for the
changed guide and reader map. Read back the sparse trace schema, projection paths, catalog route,
and graph edges from the fresh source snapshot. A stale graph status is a blocker to dependency
readback, not a reason to consume the previous snapshot.

## Mechanical checks

Changed Markdown remains subject to dependency-header validation, formatter, and docs checks.
Those checks establish source readability and graph integrity; they do not replace the
reviewer decision matrix or the forward/reverse semantic trace.

## References

- [Coding conventions index](README.md)
- [Python coding conventions](coding-conventions-python.md)
- [C++ coding conventions](coding-conventions-cpp.md)
- [Document rules](../rule/README.md)
