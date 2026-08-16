<!--
@dependency-start
contract issue
responsibility Records the completed integration of canonical software engineering principles across AgentCanon design, implementation, refactor, review, and validation.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
downstream design ../../documents/conventions/software-engineering-principles.md canonical engineering policy
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
status: resolved
source: user
severity: S2
problem: 言語・paradigmをまたぐソフトウェア工学原則の正本と競合時の判断順序がなく、設計・refactor・review・OOP文書へ判断が分散している。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/717
done: 一般原則の正本、専門ownerとの境界、既存skillへの消費経路、誤用防止、検証経路を一つのreview可能な変更として完成させる。
affected_surfaces: PHILOSOPHY.md, documents/conventions/, agents/skills/comprehensive-development.md, agents/skills/refactor-loop.md, agents/skills/change-review.md, notes/knowledge/coding_decision_methods.md
edit_scope: owner-bounded
required_action: canonical policyを追加し、top-level reader route、OOP specialization、design/refactor/review consumer、knowledge-note boundaryを同じ責務graphへ接続する。
close_condition: PR #718 と #721 がmergeされ、一般原則の正本が一意で、既存ownerが同じprecedenceを参照し、local Issue recordがclosed/resolvedとなり、repository-owned required checksがpassしている。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/717
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/721

## Resolution snapshot

- Initial canonicalization: PR #718, merged as
  `1ebe6726917d2d3d1edfea466adce602ff5ed60e`.
- Remaining policy-restatement cleanup: PR #721, merged as
  `c20f3d6a0a8e2a82c10895cbb23128bc488f8c38`.
- Durable closeout baseline: `main@01b4aebcf050ce599385b9bd5dccfa9848f6d9db`.
- Durable closeout branch: `fix/717-close-durable-issue-record`.
- The original source branch `canon/software-engineering-principles-717` is merged and no
  longer exists on the remote.
- `documents/conventions/software-engineering-principles.md` is the sole normative owner of
  cross-language, paradigm-independent software engineering principles. This closed record
  stores requirement, implementation, validation, and closeout trace only.

## Root cause and resolved ownership

The repository previously lacked one canonical owner for general engineering principles, so
callers either re-derived precedence per task or over-activated OOP, review, and refactor
surfaces as if each were a general policy owner. PR #718 created the missing owner and routed
existing consumers to it. PR #721 removed the remaining durable restatement from the refactor
consumer and this Issue record.

| Surface | Resolved responsibility |
| --- | --- |
| `PHILOSOPHY.md` | top-level philosophy and reader route only |
| `software-engineering-principles.md` | general principles, precedence, misuse prevention, and evidence model |
| `object-oriented-design.md` | object-contract and SOLID specialization only |
| `comprehensive-development.md` | design and delivery consumer |
| `refactor-loop.md` | behavior-preserving refactor consumer |
| `change-review.md` | findings-first review consumer |
| `notes/knowledge/coding_decision_methods.md` | non-canonical external method and source note |
| Issue / PR | current requirement, implementation trace, validation evidence, and closeout state |

## Canonical references

This historical record does not redefine the principles or their conflict order. The canonical
clauses remain in:

- [判断の優先順位](../../documents/conventions/software-engineering-principles.md#判断の優先順位)
- [SEP-01 / SEP-02: contract と invariant](../../documents/conventions/software-engineering-principles.md#1-contractcorrectnessinvariant)
- [SEP-03 / SEP-05: 責務と依存境界](../../documents/conventions/software-engineering-principles.md#2-責務と依存境界)
- [SEP-06 / SEP-08: 単純さと抽象化](../../documents/conventions/software-engineering-principles.md#3-単純さと抽象化の-admission)
- [SEP-09 / SEP-10: 変更単位と完全性](../../documents/conventions/software-engineering-principles.md#4-変更単位と完全性)
- [SEP-11〜SEP-14: 検証、失敗、観測性、traceability](../../documents/conventions/software-engineering-principles.md#5-verification再現性運用)

## Durable closeout scope

- Move `issues/open/AC-20260815-software-engineering-principles.md` to the same name under
  `issues/closed/`.
- Set `status: resolved`, add `resolved_by:`, and update `close_condition` to represent the
  implemented and validated state.
- Keep implementation, policy, skill, workflow, checker, schema, runtime, and template
  surfaces unchanged.
- Preserve the Issue-to-branch-to-PR-to-validation trace without turning the closed record
  into a second policy source.

## Validation ownership

Implementation validation already completed on the semantic changes:

- PR #718 head `af079cd7f174707caeaabca72020b79994a6cea1`
  - AgentCanon Static Gates `31863261867`: success
  - Issue Mirror `31863261875`: success
  - Agent Runtime Dashboard `31863261887`: success
- PR #721 head `dcaeea2dcd1b80bb0edb0ff41c40dd660cfef299`
  - AgentCanon Static Gates `31872734111`: success
  - Issue Mirror `31872734109`: success
  - Agent Runtime Dashboard `31872734121`: success
  - CodeQL actions/python: success

The closeout change is admitted only when the repository-owned PR checks pass:

- `static-gates`
- `dashboard`
- `issue-mirror-check`

For pull requests, `.github/workflows/issue-mirror.yml` intentionally skips remote mutation.
After merge, the protected-main publication workflow synchronizes the closed local record to
GitHub and readback must show Issue #717 closed without state drift.

## Acceptance readback

- The general-principles canonical owner remains unique.
- Philosophy, convention index, OOP specialization, design/delivery, refactor, review, and
  knowledge-note surfaces retain their bounded responsibilities.
- No new skill, workflow, tool, checker, schema, receipt, negative token, runtime selector,
  or template projection is introduced.
- The durable Issue record is under `issues/closed/`, uses `status: resolved`, contains
  `resolved_by:`, and has a completed `close_condition`.
- The Issue thread links the closeout branch, PR, validation results, and any remaining risk.
