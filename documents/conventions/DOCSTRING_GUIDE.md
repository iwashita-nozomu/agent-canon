<!--
@dependency-start
contract policy
responsibility Defines the language-neutral semantic Docstring contract, its canonical template skeleton, and its language projection trace.
upstream design ../rule/README.md document filename, placement, and language rules
upstream design ../design/cpp-build-layout.md selects derived-repo native C++ target identities and build layout
upstream design ../../agents/skills/catalog.yaml selects the OOP/type-design capability owner
upstream design ../../agents/skills/skill-dependencies.yaml selects reviewer prerequisite and dependency order
downstream implementation ../../templates/README.md indexes template projection consumers and sparse Docstring boundaries
downstream design ./coding-conventions-python.md projects the contract into Python docstring syntax and public-surface rules
downstream design ./coding-conventions-cpp.md projects the contract into C++ documentation syntax and native-boundary rules
downstream implementation ../../templates/documents/design-document.template.md consumes the semantic skeleton in the reusable design template
downstream implementation ../../templates/experiments/_template/run.py projects the contract into the Python code template
downstream implementation ../../templates/experiments/_template/cases.py projects the contract into the Python module template
downstream design ../../agents/skills/python-review.md routes explicit Docstring review and semantic projection when selected
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
| reusable document-template projection | `templates/documents/design-document.template.md` | skeleton を参照する既存 template |
| Python adapter projection | `documents/conventions/coding-conventions-python.md` | Python docstring syntax / format |
| C++ adapter projection | `documents/conventions/coding-conventions-cpp.md` | C++ documentation syntax / native format |
| Python code-template projection | `templates/experiments/_template/run.py` | runtime code への current projection |
| Python module-template projection | `templates/experiments/_template/cases.py` | module responsibility の current projection |
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
projection 要否を導き、既存 DIC の path / clause / evidence trace に束縛します。同一
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
contract が未確定で、実装者が Docstring で補ってはいけない場合は、既存 DIC の evidence
trace から設計 owner へ返します。

### DIC path / clause / evidence trace

既存の Design-Implementation Correspondence (DIC) record が semantic completeness の
owner です。各 function に別の materialized record schema を追加せず、DIC-004 の変更
target と clause ID、DIC-005 の forward / reverse coverage、そして validation / evidence
locator を current projection に結び付けます。

各 projection の trace は次の4点を持つ既存 DIC の対応関係として read back します。

| trace field | content | positive completion evidence |
| --- | --- | --- |
| path | repo-relative current projection path | changed-path inventory と implementation target |
| section | section、qualname、または cohesive responsibility region | projection anchor と責務境界 |
| clause | `responsibility` などの clause と `DSC-*` / DIC clause ID | forward clause mapping |
| evidence | source、static-surface、review、または canonical readback locator | reverse evidence mapping |

present、omitted、owner-returned は projection の結果分類として DIC evidence に記録
できます。omitted は static surface で意味が閉じる positive decision、owner-returned は
未確定 contract を owner に戻す positive decision です。いずれも function ごとの新しい
schema、全 function の record、固定 field の穴埋めを要求しません。

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
を一度ずつ使うことは completion 条件ではありません。matrix で選択された結果を既存 DIC の
path / clause / evidence trace に束縛してから language adapter の syntax へ投影します。

この skeleton の reusable document-template projection target は
`templates/documents/design-document.template.md` です。そこへ semantic clause をコピー
して第二正本を作らず、contract owner への参照と projection/trace 欄を追加します。

## Projection consumers and acceptance trace

document-template、Python、C++ は別々の projection consumer です。semantic contract と
matrix はこの guide に残し、各 consumer は syntax、format、責務領域、projection anchor、
acceptance trace だけを持ちます。

### Document-template projection

- consumer: `templates/documents/design-document.template.md`
- responsibility region: authority / decision status、target state、OOP/type boundary、
  dependency/effect、adversarial review、reconstruction、acceptance、evidence ledger
- acceptance trace: template section anchor と design clause の source anchor を既存 DIC
  の path / section / clause / evidence trace に保存します。semantic clause 本文をこの
  templateへ複製せず、canonical guide への owner reference と projection/trace 欄だけを
  追加します。

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
- acceptance trace: qualname/responsibility region、Python projection anchor、selected
  reviewer、static-surface evidence を既存 DIC の path / section / clause / evidence trace
  に保存します。既存 Python docstring prose はこの consumer projectionへ変換し、language
  convention に残った semantic duplicate owner を削除します。

### C++ projection

- adapter owner: `documents/conventions/coding-conventions-cpp.md`
- native-consumer join: `documents/design/cpp-build-layout.md` が派生 repo の C++ target
  identity を選び、`cpp/include/<project>/...` または `cpp/src/...` の native source/header
  surface とこの adapter projection を結びます。
- responsibility regions: public header の declaration / ownership boundary と、source
  implementation の algorithm / failure / native side effect boundary
- acceptance trace: header/source anchor、Doxygen projection、native ownership/header
  evidence、selected reviewer を既存 DIC の path / section / clause / evidence trace に保存
  します。既存 C++ docstring/comment prose はこの projection consumer へ変換し、C++ convention
  側の semantic duplicate owner を削除します。AgentCanon C++ scaffold は、この build
  design が owner と target identity を定義した場合に限り、別 change として追加します。

## Evidence And Assumption Ledger

normalization の意味、owner、evidence、validation を、次の短い structured ledger で固定
します。record は必要な根拠だけを保持し、説明文や path の重複を増やしません。

| id | normalization meaning | owner | evidence | validation |
| --- | --- | --- | --- | --- |
| DAL-01 | C++ native consumer は build design が選ぶ `cpp/include/<project>/...` / `cpp/src/...` target identity に正規化する | `documents/design/cpp-build-layout.md` | canonical dependency readback と design document source anchor | canonical CI/readback、`check_design_doc_claims.py`、native-path candidate |
| DAL-02 | C++ Docstring projection は syntax / format と native target anchor の join に正規化する | `documents/conventions/coding-conventions-cpp.md` + `documents/design/cpp-build-layout.md` | C++ projection record の adapter owner、target identity、header/source anchor | design claim checker と C++ adapter readback |
| DAL-03 | reviewer 選択は changed-surface evidence を existing language/docs candidates へ正規化し、OOP ownerだけを capability projection へ渡す | `tools/agent/orchestration/agent_team.py` + `agents/skills/catalog.yaml` | candidate list、OOP route packet、dependency order | `language_review_candidates`、`route.py`、orchestration check |
| DAL-04 | projection の省略は static surface に semantic delta が十分表現済みという DIC evidence に正規化する | `documents/conventions/DOCSTRING_GUIDE.md` | DIC path / section / clause / evidence trace | docs check、prose readback、design claim checker |

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

skill routing は、既存の changed-path routing と設計 owner の capability 選択を分離します。
`agent_team.language_review_candidates` が language implementation path と convention /
template documentation path を読み、選択された touched surface に対応する reviewer を
返します。catalog capability は pre-implementation の OOP/type design owner を選ぶ場合に
だけ使います。新しい Docstring capability、keyword branch、または reviewer branch は追加
しません。

| routing owner | projection input / result |
| --- | --- |
| `agents/skills/catalog.yaml` | OOP/type design owner の capability identity and selection |
| `agents/skills/skill-dependencies.yaml` | prerequisite, successor, and dependency order |
| `tools/agent/orchestration/agent_team.py` | changed paths から language reviewer candidates を選択 |
| `tools/agent/orchestration/route.py` | OOP/type design capability と既存 route packet を materialize |

`agent_team.language_review_candidates` は Python implementation path（`python/`、`tests/`、
`.py` / `.pyi`）、native C/C++ implementation path（native suffix または `src/`、`include/`、
`lib/`、`cmake/` marker）、および document/config・convention/template path を判定します。
それぞれ `python_reviewer`、`cpp_reviewer`、`docs_workflow_steward` を候補にし、convention /
template docs は `docs_workflow_steward` が所有します。guide は selected candidate の
surface に応じて semantic clause を読み戻します。catalog capability は OOP/type design owner
の選択に限り、language reviewer の選択は既存 candidates が担います。

## Validation and review boundary

- `pydocstyle` と Ruff D は、明示的な language-level Docstring review の存在・syntax・format signal を検証する。
- `pyright` と C++ compiler/build は、annotation、signature、namespace、header、ABI の
  static fact を検証する。
- OOP/readability checker は責務境界の signal を提供するが、clause の意味充足を判定しない。
- semantic clause の妥当性、設計との整合、side effect/failure/ownership の完全性は
  selected reviewer が判定する。
- 全引数・全属性・`Args`/`Returns` token の存在を意味契約の gate にしない。
- 実装 mechanism が存在し、なお未解決の behavior oracle がある場合だけ test design を
  追加する。Docstring prose 自体を test-first の対象にしない。

### Explicit Docstring review boundary

`pydocstyle` は compile/runtime/graph/header correctness の必要条件ではなく、
shared PR/static gate では実行しません。明示的な Docstring review で、対象を限定して
`tools/bin/agent-canon pydocstyle-review --target <repo-relative.py>` を実行します。このtoolは
source-root resolverが選ぶAgentCanon canonical D213 configを適用し、toolが無い場合または
診断がある場合は明示 command が nonzero で終了します。

AgentCanon の既定 review convention は source root 配下の
`tools/validation/ci/config/pydocstyle.toml` で D213 を選択し、相反する D212 を無視します。D212 と D213
を同時に要求しません。親固有のDocstring reviewは親ownerの別commandで実行し、AgentCanon
canonical configのauthorityを置き換えません。
PR の blocking predicate には pydocstyle を含めず、pydocstyle の missing/diagnostic を
merge gateへ昇格しません。他の active profile が選択する compiler、runtime、graph、
header、Rust、workflow、container、docs、registry、pytest、pyright などの owner gate は
それぞれの正本に従います。

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

1. **Forward**: canonical template skeleton の各 selected clause が、current projection
   の `path`、`section`（`qualname` または cohesive responsibility region）、clause ID、
   evidence locator として既存 DIC trace に対応する。
2. **Reverse**: 実装・design evidence に現れる state transition、pure-function result、
   effect、ownership、failure、algorithm/design condition が、DIC の path / section /
   clause / evidence join へ戻れる。static surface で閉じる omission と owner へ返す
   未確定 contract も同じ DIC evidence で正の判断として保持する。
3. **Consistency**: Docstring が design clause にない保証、effect、failure、ownership を
   発明していない。未確定の内容は DIC evidence から設計 owner へ戻る。
4. **Readback**: template source、adapter projection、実装 Docstring、review decision を
   同じ DIC trace で再読し、forward/reverse の欠落を closeout 前に解消する。dependency /
   skill projection source が変わった場合は、canonical CI と selected edge/readback evidence
   を使用する。一般の Docstring projectionには local runtime-event certificate や graph
   freshness gate を追加しない。

### Design-to-implementation trace

| trace id | source / design clause | current canonical path | current projection consumer | acceptance evidence |
| --- | --- | --- | --- | --- |
| DSC-01 | semantic contract, matrix, DIC path / clause / evidence trace | `documents/conventions/DOCSTRING_GUIDE.md` | same section remains the source | DIC path, clause, and evidence readback |
| DSC-02 | canonical skeleton | `documents/conventions/DOCSTRING_GUIDE.md#canonical-template-skeleton` | `templates/documents/design-document.template.md` | document-template record with section anchor |
| DSC-03 | document-template responsibility region | this section | `templates/documents/design-document.template.md` | authority/target/acceptance section trace |
| DSC-04 | Python syntax/public surface | `documents/conventions/coding-conventions-python.md` | `templates/experiments/_template/run.py`, `cases.py` | DIC path/section/clause/evidence readback for Python regions |
| DSC-05 | C++ syntax/native boundary and build-design join | `documents/conventions/coding-conventions-cpp.md` + `documents/design/cpp-build-layout.md` | derived-repo `cpp/include/<project>/...` / `cpp/src/...` target identity | DIC path/section/clause/evidence readback with build-design anchor |
| DSC-06 | existing prose migration | this guide plus language convention owners | existing Python/C++ prose converted into projection consumers | duplicate semantic owner removed and DIC trace retained |
| DSC-07 | reviewer routing | `agent_team.language_review_candidates` plus OOP capability owner | existing changed-path candidates and OOP route packet | language implementation/docs candidates; no keyword/new branch |
| DSC-08 | positive completion | this section | implementation Docstring and review artifact | each current path has forward/reverse DIC trace; no per-function record |
| DSC-09 | dependency/skill projection readback | `Dependency/skill projection readback route` | canonical CI and selected source/edge readback | canonical CI/readback evidence when those projections change |

### Current projection set

The approved design and this implementation are bound to the following 11 current projection
paths. Each row is a cohesive path/section trace target, not a requirement for a function-level
record. The existing DIC path / clause / evidence trace owns semantic completeness.

| current path | forward projection section / region | clause trace | reverse evidence trace |
| --- | --- | --- | --- |
| `documents/conventions/DOCSTRING_GUIDE.md` | `Semantic contract`, `Canonical template skeleton`, `Positive completion and design trace` | DSC-01, DSC-08; DIC-004..006 | guide matrix, skeleton, and DIC readback |
| `documents/conventions/README.md` | conventions index / Docstring owner reference | DSC-01 | owner link and docs check |
| `documents/conventions/coding-conventions-python.md` | Python Docstring syntax / public-surface projection | DSC-04, DSC-06 | syntax/format section and Python adapter readback |
| `documents/conventions/coding-conventions-cpp.md` | C++ documentation syntax / native-boundary projection | DSC-05, DSC-06 | Doxygen/native anchor and cpp-build-layout reference |
| `templates/README.md` | template Docstring projection index | DSC-02, DSC-03 | guide reference and docs check |
| `templates/documents/design-document.template.md` | design-template Docstring projection | DSC-02, DSC-03 | owner reference and projection fields |
| `templates/experiments/_template/run.py` | module, result, worker, artifact, subprocess, failure, and orchestration regions | DSC-04, DSC-08 | Python syntax/static check and DIC reverse readback |
| `templates/experiments/_template/cases.py` | module-level case-definition region | DSC-04, DSC-08 | Python syntax/static check and DIC reverse readback |
| `agents/skills/oop-type-design.md` | OOP/type boundary and Docstring projection route | DSC-07, DIC-007 | OOP capability route and skill docs readback |
| `agents/skills/python-review.md` | Python implementation-path reviewer route | DSC-04, DSC-07 | `agent_team.language_review_candidates` and Python review readback |
| `agents/skills/cpp-review.md` | native implementation-path reviewer route | DSC-05, DSC-07 | `agent_team.language_review_candidates` and C++ review readback |

Convention and template documentation paths are current consumers owned by
`docs_workflow_steward`; Python/C++ reviewers are candidates when the changed surface also
contains the corresponding language implementation paths. AgentCanon C++ scaffold remains out of
scope, and `cpp-build-layout.md` continues to own any future native target identity decision.

## Dependency/skill projection readback route

General Docstring changes close through the DIC trace and targeted docs, dependency-header, runtime
alignment, and routing checks. This evidence set contains no local runtime-event certificate or
fresh-graph status gate. Local `.active_run` state remains task-local runtime state, while canonical
readback evidence establishes dependency and skill projection state.

When a dependency or skill projection source changes, read back the selected owner and edges through
the canonical CI/static gate and its fresh-checkout evidence, together with the targeted dependency
header, runtime-alignment, and route checks. The canonical GitHub static-gate result is the accepted
positive evidence for this projection branch; local task state remains outside that evidence path.

## Mechanical checks

Changed Markdown remains subject to dependency-header validation, formatter, and docs checks.
Those checks establish source readability and header integrity; canonical CI/readback evidence
covers dependency/skill projection edges when those owners change. They do not replace the reviewer
decision matrix or the forward/reverse semantic trace.

## References

- [Coding conventions index](README.md)
- [Python coding conventions](coding-conventions-python.md)
- [C++ coding conventions](coding-conventions-cpp.md)
- [Document rules](../rule/README.md)
