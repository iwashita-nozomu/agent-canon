<!--
@dependency-start
contract issue
responsibility Tracks integration of canonical software engineering principles across AgentCanon design, implementation, refactor, review, and validation.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
downstream design ../../documents/conventions/software-engineering-principles.md target canonical engineering policy
downstream design ../../PHILOSOPHY.md top-level reader route
downstream design ../../documents/conventions/README.md convention index and discovery route
downstream design ../../documents/conventions/object-oriented-design.md OOP and SOLID specialization
downstream design ../../agents/skills/comprehensive-development.md design and delivery consumer
downstream design ../../agents/skills/refactor-loop.md refactor consumer
downstream design ../../agents/skills/change-review.md review consumer
downstream design ../../notes/knowledge/coding_decision_methods.md external method and source note
@dependency-end
-->

# [設計原則] ソフトウェア工学の原則を設計・実装・レビューの正本へ統合する

issue_id: AC-20260815-software-engineering-principles
status: in_progress
source: user
severity: S2
problem: 言語・paradigmをまたぐソフトウェア工学原則の正本と競合時の判断順序がなく、設計・refactor・review・OOP文書へ判断が分散している。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/717
done: 一般原則の正本、専門ownerとの境界、既存skillへの消費経路、誤用防止、検証経路を一つのreview可能な変更として完成させる。
affected_surfaces: PHILOSOPHY.md, documents/conventions/, agents/skills/comprehensive-development.md, agents/skills/refactor-loop.md, agents/skills/change-review.md, notes/knowledge/coding_decision_methods.md
edit_scope: owner-bounded
required_action: canonical policyを追加し、top-level reader route、OOP specialization、design/refactor/review consumer、knowledge-note boundaryを同じ責務graphへ接続する。
close_condition: PRがmergeされ、一般原則の正本が一意で、既存ownerが同じprecedenceを参照し、repository-owned validationがpassしている。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/717

## Current snapshot

- Baseline: `main@c5fa3a22c8486952dc6dede0cc3a25e5ba7741e5`
- Active branch: `canon/software-engineering-principles-717`
- Existing duplicate Issue / PR / branch: none found by bounded search
- Current canonical gap: general principles exist as fragments, but no language- and
  paradigm-neutral owner defines their precedence, misuse boundary, or shared evidence model.

## Existing responsibility map

| Surface | Current responsibility | Gap before this issue |
| --- | --- | --- |
| `PHILOSOPHY.md` | top-level responsibility、agent/tool、source-of-truth philosophy | detailed engineering precedence を持つには広すぎる |
| `documents/conventions/object-oriented-design.md` | class、state、inheritance、composition、`Protocol`、SOLID | functional、numerical、shell、workflow、document/tooling change の一般ownerにはできない |
| `agents/skills/change-review.md` | findings-first review、cause、root-cause closure、validation selection | KISS / YAGNI / DRY 等の意味を局所で再推論する |
| `agents/skills/refactor-loop.md` | behavior-preserving structural refactor | abstraction admission と principle conflict の一般正本がない |
| `agents/skills/comprehensive-development.md` | cross-surface delivery integration | design slice が選ぶ一般原則の共通順序がない |
| `notes/knowledge/coding_decision_methods.md` | SWEBOK、ATAM、ADR、Google Engineering Practices 等のsource note | shared policy と source note の境界が曖昧になり得る |

## Root cause

一般原則を持つべき責務が一つの canonical policy として materialize されず、top-level
philosophy、OOP specialization、operational skill、external method note に分散している。
そのため caller は次のどちらかを選ばされる。

1. task ごとに同じ原則と競合順序を再推論する。
2. OOP / review / refactor 文書を一般 policy として過剰に起動し、第二正本を増やす。

新しい checker や checklist で解決すると、原則を運用するための ceremony と gate surface
が増え、元の責務欠落を隠すだけになる。

## Target ownership

### Canonical owner

`documents/conventions/software-engineering-principles.md` を、設計、実装、refactor、review、
validation に共通する言語・paradigm非依存 policy の唯一の正本とする。

`documents/design/` ではなく `documents/conventions/` に置く。特定 module の target state
ではなく、複数 repository task が共有する判断規約だからである。

### Owner boundaries

| Owner | Owns | Does not own |
| --- | --- | --- |
| `PHILOSOPHY.md` | top-level philosophy と最初の reader route | 個別原則の全文、task-specific target state |
| `software-engineering-principles.md` | 一般原則、優先順位、誤用防止、evidence model | OOP固有の形、language syntax、個別設計 |
| `object-oriented-design.md` | object contract と SOLID specialization | 全changeへのOOP activation |
| language convention | language/toolchain固有規約 | cross-language owner |
| task design | target state、tradeoff、assumption、implementation trace | 一般policyの第二正本 |
| Issue / PR | current snapshot、scope reduction、implementation / validation evidence | 長期policyの唯一の根拠 |
| `notes/knowledge/` | external source / method note | mandatory shared policy |

## Canonical decision precedence

原則が競合した場合は次の順序を固定する。

1. 明示された user / domain contract、safety、correctness
2. semantic invariant、state / lifecycle owner、public compatibility
3. root-cause closure、reachable failure handling、cleanup / recovery
4. responsibility / dependency boundary、information hiding、authority boundary
5. testability、reproducibility、operational observability
6. simplicity、change locality、reuse、abstraction cost
7. stylistic consistency

下位原則は上位contractを弱めない。

- DRY のために異なる数理意味、unit、停止条件、failure semantics を統合しない。
- KISS のためにerror、cleanup、migration、root mechanismを落とさない。
- YAGNI のために要求済みbehaviorやconsumer migrationを未完にしない。
- locality のためにshared ownerのinvariantをcaller patchで迂回しない。
- extensibility のためにconcrete callerのないinterface / registry / wrapperを追加しない。

## Principle model

### Contract and invariant

- user / domain contract、precondition、postcondition、invariant、stop condition、failure
  semantics、compatibility、side effect、cleanup を先に固定する。
- 同じ state transition、identity、transaction、lifecycle、consistency rule は一つの
  canonical owner が持つ。
- test は implementation trace ではなく contract、counterexample、stable oracle を固定する。

### Responsibility and dependency

- separation of concerns は、異なる actor / change reason、invariant、state lifecycle、effect、
  reader / caller、validation owner を分ける。
- single responsibility は one-file / one-function 規則ではなく、replaceable responsibility
  と同じ変更理由を表す。
- high cohesion は同じ invariant と lifecycle をowner内に集め、low coupling は別ownerの
  internal representationではなくstable contractへ依存する。
- information hiding は temporary path、storage、生成順序、diagnostic token をpublic APIへ漏らさない。
- high-level policyをconcrete detailへ従属させないが、差し替え根拠のないabstractionも作らない。

### Simplicity and abstraction admission

- KISS は完全なcontractを満たす候補の中で、owner、surface、state、branch、invariantの総数が
  少ない設計を選ぶ。shortest code / minimum diffではない。
- YAGNI はconcrete caller、current requirement、reachable failure、stable external boundaryの
  ないspeculative mechanismを追加しない。現在要求された完成条件を省く原則ではない。
- DRY は同じknowledge、policy、invariant、state ownerの複数正本をなくす。textual similarity
  だけで異なる意味を統合しない。
- abstractionは同じ意味、contract、change reason、failure semantics、実在consumer、明確な
  canonical ownerがある場合だけadmissionする。

### Change and verification

- scopeはsymptom fileやrepo-wide cleanupではなく、evidence-bounded complete owning unitと、
  到達するconsumer、failure、cleanup、contract、docs、tests、validationで閉じる。
- public surface変更はcanonical targetとconsumer migrationを一つの完成条件にする。
- validationはchanged propertyとreachable riskに対応させ、選ばれないfull gateやnegative receipt
  を追加しない。
- determinism、idempotency、reproducibilityは、それぞれ必要なsurfaceのowner contractとして定義する。

### Failure and traceability

- implementation defect、invalid input、expected domain/numerical breakdown、environment unavailable、
  external permission/rate/billing failure、verification unavailable、conflict/stale snapshotを区別する。
- failureをsilent fallback、ignore、successへ変換しない。
- observabilityはstate transition、input class、owner、first failure、effect/cleanup resultを追える範囲にする。
- requirement → Issue → canonical clause → branch/PR/diff → validation → accepted sourceのtraceを保つ。

## Runtime integration

新しいpublic skill、workflow、tool、checker、schema、score、receipt、negative tokenは追加しない。
既存ownerがcanonical policyのmaterial clauseだけを消費する。

### Design / delivery

`agents/skills/comprehensive-development.md` はcross-surface planで、contract / invariant、canonical
owner、responsibility/effect boundary、abstraction admission、complete owning unit、validation/recoveryを
先に固定する。全原則checklistは作らない。

### Refactor

`agents/skills/refactor-loop.md` はbehavior preservationを最優先にし、DRY / KISS / YAGNIを
canonical policyへ委譲する。異なる意味の統合、minimum-diff symptom patch、speculative abstraction、
incomplete migrationを拒否する。

### Review

`agents/skills/change-review.md` はprinciple名だけをfindingにせず、具体的なcontract、invariant、
owner、dependency、reachable failureとselected clauseを結ぶ。OOP-sensitive changeだけを専門ownerへ委譲する。

### OOP specialization

`documents/conventions/object-oriented-design.md` はgeneral policyのspecializationとし、class、state、
inheritance、composition、`Protocol`、public object modelがmaterialに変わる場合だけ起動する。

### Knowledge note

`notes/knowledge/coding_decision_methods.md` は外部method/source noteとして残し、AgentCanonの
mandatory policyを所有しないことを明示する。

## Implementation scope

- `PHILOSOPHY.md`
- `documents/conventions/README.md`
- `documents/conventions/software-engineering-principles.md` (new canonical owner)
- `documents/conventions/object-oriented-design.md`
- `agents/skills/comprehensive-development.md`
- `agents/skills/refactor-loop.md`
- `agents/skills/change-review.md`
- `notes/knowledge/coding_decision_methods.md`
- `issues/open/AC-20260815-software-engineering-principles.md`

必要なdependency header、index、reader route、GitHub mirrorを同じchangeで閉じる。
runtime selector、skill catalog、workflow DAG、tool implementation、CI gateは変更しない。

## Non-goals

- 原則ごとのskill / checker / workflow / schemaを作ること
- 各PRへSOLID / KISS / YAGNI / DRY checklistを必須化すること
- source codeを一括refactorすること
- 全既存文書へ原則名を機械的に追記すること
- external engineering frameworkのceremonyをmandatory processへ複製すること
- OOP checker activationを広げること
- external source noteを削除すること

## Validation plan

既存ownerのcheckerだけを使う。

```bash
python3 tools/agent_tools/check_dependency_headers.py --root .
python3 tools/agent_tools/check_convention_compliance.py --root .
python3 tools/agent_tools/repo_structure_contract.py --root .
python3 tools/agent_tools/responsibility_scope.py --root .
python3 tools/agent_tools/issue_sync.py --root . --repo iwashita-nozomu/agent-canon --github-check
```

加えて、changed Markdownのrelative link、heading、dependency edgeをread backし、PRの
repository-owned required checksを確認する。外部環境で観測できないpropertyはbranch defectと
混同せず、remaining verificationとしてIssue / PRへ残す。

## Acceptance criteria

- 一般原則のcanonical ownerが`software-engineering-principles.md`に一意化される。
- `PHILOSOPHY.md`とconvention indexから正本へ到達できる。
- design/delivery、refactor、reviewの既存skillが同じprecedenceとevidence modelを参照する。
- OOP文書がspecializationとなり、全changeへOOP/SOLIDを要求しない。
- knowledge noteがnon-canonical source noteであることを明示する。
- KISS / YAGNI / DRY / minimum diff / SOLIDの誤用とconflict resolutionを持つ。
- 新しいskill、workflow、tool、checker、schema、receipt、negative tokenを追加しない。
- dependency header、Markdown link、document/index/issue validationがpassする。
- Issueからbranch、PR、validation、remaining riskを辿れる。
