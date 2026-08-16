<!--
@dependency-start
contract design
responsibility Defines semantic parent-audit units while keeping path ownership canonical in responsibility-scope.toml.
upstream design ../rule/README.md document placement and Japanese prose rules
upstream design responsibility-scope-management.md owns the unique tracked-path ownership relation
upstream design ../structure/repo-structure-contract.toml owns path existence and filesystem kind
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md owns runtime projection mechanics
downstream design ../parent-repository-audit/README.md owns the reader route
downstream implementation ../../tools/agent_tools/parent_repository_audit.py enumerates units and evidence
downstream implementation ../../tests/agent_tools/test_parent_repository_audit.py verifies semantic selection and failure semantics
@dependency-end
-->

# 親レポ監査の設計

## Reader Map

この文書は、親 repository の監査を semantic change surface ごとの unit に分解し、path
ownership、structure existence、runtime projection と混同しないための設計正本です。最初に
型と不変条件、次に source/evidence 境界、unit map、実行・failure semantics、最後に一回限り
legacy migration ledger を読みます。

## Canonical Types And Invariants

親 repository の tracked path の有限集合を `P`、`responsibility-scope.toml` の scope 集合を
`S` とします。include/exclude glob から導かれる関係を

```text
owns : P × S -> {false, true}
```

とすると、path ownership の正しさは次の全域一意条件です。

```text
for every p in P: cardinality({s in S | owns(p, s)}) = 1
```

この条件は実在する tracked path だけを分類します。ある scope glob の逆像が空であることは
正常であり、path の存在を要求しません。存在と filesystem kind は structure contract が
別に所有します。したがって、owner checker は tracked path を一度だけ走査し、owner が 0
または 2 以上の path だけを finding にします。

監査 unit の有限集合を `U`、stable semantic surface の集合を `F` とします。各 unit は

```text
surfaces : U -> nonempty finite subsets of F
```

を `Related Change Surfaces` から宣言します。`--surface f` は `f` を含む unit を選択します。
path 名や directory glob はこの relation を所有しません。`--scope` は selected tracked
evidence の部分集合を作るだけで、unit または owner を選びません。

## Separation Of Responsibilities

| Source | Sole responsibility | Explicitly does not own |
| --- | --- | --- |
| `responsibility-scope.toml` | tracked path -> owner/class | required path existence、audit unit selection |
| `documents/structure/repo-structure-contract.toml` | expected path -> filesystem kind | owner/class、semantic audit route |
| `documents/runtime/shared-runtime-surfaces.toml` | source/view projection mechanics | parent path ownership、general structure |
| `documents/parent-repository-audit/audit-unit/*.md` | semantic invariant、repair、validation、close | broad path coverage、owner overlap |
| `tools/agent_tools/parent_repository_audit.py` | unit enumeration、surface selection、evidence receipt | path ownership classification |

新しい通常 path を追加するとき、owner/class の変更は一つの `responsibility-scope.toml` だけに
記録します。required structure なら structure contract に存在/kind を追加しますが、同じ
owner/class や category を複製しません。runtime view を追加する場合だけ projection manifest
を変更します。

## Canonical Source And Evidence

- `documents/parent-repository-audit/README.md`: reader route と選択境界。
- `documents/parent-repository-audit/audit-unit/*.md`: unit ごとの正本。
- `tools/agent_tools/parent_repository_audit.py`: deterministic projection。
- `tests/agent_tools/test_parent_repository_audit.py`: semantic selection と failure oracle。
- 親の tracked tree、branch、commit、finding、repair/readback receipt: 親固有 evidence。
- generated report、inventory、run bundle: 再生成可能な evidence/projection。

AgentCanon source と親 root は別の publication lane です。source contract を親側で直接
上書きせず、親固有 finding を AgentCanon 正本へ取り込みません。

## Canonical Audit Unit Map

各 unit は `Owner Responsibility`、`Invariant`、`Evidence Sources`、`Repair Route`、
`Validation`、`Close Condition`、`Related Change Surfaces`、`Legacy Migration IDs` を持ちます。

| Unit | Stable surfaces | Responsibility |
| --- | --- | --- |
| `ci-hooks-skills` | `surface:ci.hooks-skills`<br>`surface:skill.catalog`<br>`surface:skill.dependencies`<br>`surface:skill.runtime-shim`<br>`surface:skill.graph` | CI、hooks、public skill、catalog/dependency/runtime adapter |
| `code-type-boundaries` | `surface:code.type-boundary`<br>`surface:code.oop-responsibility`<br>`surface:implementation.trace`<br>`surface:language.python`<br>`surface:language.native` | public API、型、OOP responsibility、language boundary |
| `dependency-integrity` | `surface:dependency.headers`<br>`surface:dependency.graph`<br>`surface:dependency.manifests` | dependency header、manifest、graph direction |
| `docs-design-trace` | `surface:docs.design-trace`<br>`surface:docs.reader-map`<br>`surface:docs.formatter` | reader route、design trace、Markdown correctness |
| `environment-containers` | `surface:environment.containers`<br>`surface:runtime.profiles`<br>`surface:devcontainer`<br>`surface:gpu.host-driver` | Docker、devcontainer、runtime profile、host-driver boundary |
| `ownership-root-views` | `surface:agentcanon.root-views`<br>`surface:agentcanon.source-root`<br>`surface:submodule.pin` | AgentCanon source、pin、root view、publication boundary |
| `repository-structure` | `surface:repo.structure`<br>`surface:responsibility.scope` | required/optional path existence と filesystem kind |
| `templates-generated-boundaries` | `surface:templates.generated-boundary`<br>`surface:evidence.artifacts`<br>`surface:docs.canon` | template、source、generated/evidence classification |
| `tests-and-oracles` | `surface:tests.oracle`<br>`surface:runtime.validation`<br>`surface:code.behavior` | test oracle と必要十分な validation |


## Deterministic Execution

```bash
python3 tools/agent_tools/parent_repository_audit.py list --root <parent-root> --format text
python3 tools/agent_tools/parent_repository_audit.py list --root <parent-root> \
  --surface <stable-surface> --scope <tracked-evidence> --format text
python3 tools/agent_tools/parent_repository_audit.py check --root <parent-root> \
  --unit-status <pass|closed|failed|deferred|blocked> --format text
```

unit file は path 昇順、surface selector は CLI の最初の出現順を保持します。未知 surface、
path escape、missing scope、invalid unit、parent Git missing は typed failure です。scope なしの
実行は全 tracked path を evidence として数えますが、coverage/overlap を再分類しません。
submodule 内部は親 tracked universe に展開しません。

unit receipt の集約は、`failed|deferred` を failed、`blocked` を blocked、全て
`pass|closed` の場合だけ closed とします。finding は owner repair、target readback、close
まで進め、blocked unit は未完了のまま次 unit へ進みます。

## Validation And Close Condition

変更後は少なくとも次を確認します。

1. `responsibility_scope.py` が全 tracked path に owner 1 件を与える。
2. 空の ownership glob は no-match failure にならない。
3. unowned tracked path と overlapping ownership は fail する。
4. structure contract は path/kind だけを保持し owner/category を持たない。
5. audit unit は semantic surface を持ち broad path selector を持たない。
6. `--scope` は evidence のみ、`--surface` は unit selection のみを変える。
7. legacy migration ID は全 171 件が一つの unit にだけ対応する。

close condition は、owner relation が一意、structure と projection の境界が維持され、
semantic unit selection と receipt aggregation の focused tests が pass することです。

## One-Time Legacy Migration Ledger

次の表は旧 checklist から unit への一回限りの対応を保持します。実行時の owner map、path
selector、または新規項目の registry ではありません。

| Stable ID | Canonical audit unit |
| --- | --- |
| `PRA-C040` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C041` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C042` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C047` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C048` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C049` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C055` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C092` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C093` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C094` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C095` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C096` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-X026` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-X028` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-X029` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-X030` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-X031` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-X035` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-X049` | `documents/parent-repository-audit/audit-unit/ci-hooks-skills.md` |
| `PRA-C052` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C053` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C054` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C071` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C072` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C073` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C074` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C075` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C076` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C077` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C078` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-X032` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-X033` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-X040` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-X041` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-X042` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-X043` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-X044` | `documents/parent-repository-audit/audit-unit/code-type-boundaries.md` |
| `PRA-C025` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-C026` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-C027` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-C028` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-C029` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-C030` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-C031` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-C032` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-X018` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-X019` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-X020` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-X021` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| `PRA-C033` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-C034` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-C035` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-C036` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-C037` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-C038` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-C039` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-X022` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-X023` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-X024` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-X025` | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| `PRA-C056` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C057` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C058` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C059` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C060` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C061` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C062` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C063` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C064` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C065` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C066` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C067` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C068` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C069` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C070` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-X036` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-X037` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-X038` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-X039` | `documents/parent-repository-audit/audit-unit/environment-containers.md` |
| `PRA-C001` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C002` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C003` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C004` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C005` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C006` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C007` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C008` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C009` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C010` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C011` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C012` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C013` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C014` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C015` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C016` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C017` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C018` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C019` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C020` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C021` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C022` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C023` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C024` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C087` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C088` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C089` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C090` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C091` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C097` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C098` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C099` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C100` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C102` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C103` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C104` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-C105` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X001` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X002` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X003` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X004` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X005` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X006` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X007` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X008` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X009` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X010` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X011` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X012` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X013` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X014` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X015` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X016` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X017` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X047` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X048` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X050` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X051` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X052` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-X053` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| `PRA-M01` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-M02` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-M03` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-M04` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-M05` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-M06` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-M07` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-M08` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C043` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C044` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C045` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C046` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C079` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C080` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C081` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C082` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C083` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C084` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C085` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C086` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C101` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C106` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C107` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C108` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C109` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C110` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-X027` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-X045` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-X046` | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| `PRA-C050` | `documents/parent-repository-audit/audit-unit/tests-and-oracles.md` |
| `PRA-C051` | `documents/parent-repository-audit/audit-unit/tests-and-oracles.md` |
| `PRA-X034` | `documents/parent-repository-audit/audit-unit/tests-and-oracles.md` |

全 ID は unit file 側にも一度だけ存在し、test がこの対応の全単射を readback します。
