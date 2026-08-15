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

- Historical baseline (pre-#718): `main@c5fa3a22c8486952dc6dede0cc3a25e5ba7741e5`.
- Integrated main: `main@1ebe6726917d2d3d1edfea466adce602ff5ed60e`, the merge of PR #718
  (`Canonicalize software engineering principles`).
- Source branch / PR state: `canon/software-engineering-principles-717` and PR #718 are
  integrated; no active source branch remains on the remote.
- Existing duplicate Issue / PR / branch: no duplicate was found by bounded search; this
  Issue remains the durable requirement and integration record for the open Issue #717.
- Current canonical state: `documents/conventions/software-engineering-principles.md` owns
  the general policy, and the listed consumer surfaces route to it. This follow-up removes
  the remaining durable policy restatement from this Issue and `refactor-loop.md`.

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

## Canonical policy references

この Issue は現在の要求、証拠、スコープ、統合結果を記録します。一般原則の意味や
判断順序を第二の durable policy として複製しません。判断の正本は次の節です。

- [判断の優先順位](../../documents/conventions/software-engineering-principles.md#判断の優先順位)
- [SEP-01 / SEP-02: contract と invariant](../../documents/conventions/software-engineering-principles.md#1-contractcorrectnessinvariant)
- [SEP-03 / SEP-05: 責務と依存境界](../../documents/conventions/software-engineering-principles.md#2-責務と依存境界)
- [SEP-06 / SEP-08: 単純さと抽象化](../../documents/conventions/software-engineering-principles.md#3-単純さと抽象化の-admission)
- [SEP-09 / SEP-10: 変更単位と完全性](../../documents/conventions/software-engineering-principles.md#4-変更単位と完全性)
- [SEP-11〜SEP-14: 検証、失敗、観測性、traceability](../../documents/conventions/software-engineering-principles.md#5-verification再現性運用)

Consumer-specific behavior remains in the owning surfaces:
`comprehensive-development.md`、`refactor-loop.md`、`change-review.md`、
`object-oriented-design.md`、および外部 method/source note は、それぞれの責務と
必要な canonical clause への参照だけを持ちます。

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
