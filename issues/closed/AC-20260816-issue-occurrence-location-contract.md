<!--
@dependency-start
contract issue
responsibility Records the completed requirement that generated Issues identify confirmed defect occurrence locations.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
upstream design ../../agents/skills/issue-finding-report.md canonical issue-production workflow
downstream design ../../.agents/skills/issue-finding-report/SKILL.md runtime discovery adapter
@dependency-end
-->

# [Issue記載品質] 問題の発生箇所を具体指定する

issue_id: AC-20260816-issue-occurrence-location-contract
status: resolved
source: user
severity: S2
problem: issue-finding-reportがaffected surfaceとevidenceの存在だけを要求し、問題を観測したsource/artifact snapshot、path、stable locatorを必須化していない。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/752
done: すべてのIssue候補がconfirmed occurrence locationを持ち、広い変更候補と観測位置を区別し、欠落問題とcross-surface disconnectも再調査なしで追跡できる。
affected_surfaces: agents/skills/issue-finding-report.md, .agents/skills/issue-finding-report/SKILL.md, project_template/agent-canon-static-seed.json
edit_scope: owner-bounded
required_action: canonical skillのpacket、location schema、Issue body contract、completion guardを更新し、runtime shimとtemplate consumer境界を検証する。
close_condition: PR #753がmergeされ、canonical ownerがconfirmed occurrence locationを要求し、runtime shimとproject_templateのconsumer境界が維持され、repository-owned checksが成功している。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/752
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/753

## Resolution snapshot

- Initial observed source: `main@84f2b06a6f5e6e2b3727da7d5af83c0746d9835f`.
- Implementation branch: `fix/752-issue-location-contract`.
- Final implementation base: `main@7438fd14bb1cbc418ebd593fc5e4b775fb31813c`.
- Validated implementation head: `605ff5ba9e96140f0aae086cc44f22e499f804ca`.
- PR #753 was squash-merged as `5e6d88e49049bd96115b2b0727ddc868f19a6ff7`.
- Durable closeout baseline: `main@5e6d88e49049bd96115b2b0727ddc868f19a6ff7`.
- Durable closeout branch: `docs/752-close-durable-record`.
- Durable closeout PR: https://github.com/iwashita-nozomu/agent-canon/pull/756.
- Pre-merge review state: zero review submissions and zero review threads.
- Remaining verification: none.

## Finding

Issue の本文に repository や広い affected surface が書かれていても、どの
function、config key、document heading、artifact field、command phase で問題を
観測したかを必須にする契約がありませんでした。このため、後続担当者が同じ調査を
繰り返さないと修正起点を確定できませんでした。

## Occurrence Locations

### Location 1: packet schema が候補 surface だけを保持していた

```text
repository: iwashita-nozomu/agent-canon
snapshot: 84f2b06a6f5e6e2b3727da7d5af83c0746d9835f
path: agents/skills/issue-finding-report.md
locator_type: heading
locator: ## Multi-Agent Partition -> Issue Finding Packet -> affected_surfaces
lines: unavailable:connector inspection used a stable Markdown anchor instead of a line-only locator
observation: packet had candidate affected_surfaces but no field for confirmed observed locations.
evidence: file content at the recorded commit listed affected_surfaces followed by duplicate_search without an occurrence-location record.
```

### Location 2: Issue completion contract lacked a concrete locator requirement

```text
repository: iwashita-nozomu/agent-canon
snapshot: 84f2b06a6f5e6e2b3727da7d5af83c0746d9835f
path: agents/skills/issue-finding-report.md
locator_type: heading
locator: ## Issue Candidate Contract -> "Populate the minimum issue form" and "Issue body sections"
lines: unavailable:connector inspection used stable sentence and heading anchors
observation: the contract required problem/evidence/done and Finding/Abstract Cause/Required Fix/Evidence, but no confirmed occurrence-location section or completion guard.
evidence: exact anchored clauses in the recorded source snapshot.
```

### Location 3: template is a consumer, not a second skill owner

```text
repository: iwashita-nozomu/project_template
snapshot: ef503efdb829fb7017cde994d523241f0e8cf187
path: agent-canon-static-seed.json
locator_type: data-field
locator: source_repository and source_commit
lines: L1-L4
observation: the template identifies AgentCanon as the source repository and does not contain a duplicate issue-finding-report skill or GitHub Issue Form owner.
evidence: source_repository=iwashita-nozomu/agent-canon; repository search returned no issue-finding-report copy and .github/ISSUE_TEMPLATE is absent.
```

## Resolved contract and ownership

候補変更・検証範囲を $A$、確認済み観測位置を $O$ とすると、$A$ は作業候補を
示すだけで $O$ を特定しません。PR #753 はこの二つを異なる契約対象として保持する
ようにしました。

- canonical owner は `agents/skills/issue-finding-report.md` のままです。
- `affected_surfaces` は候補 edit / verification scope としてのみ使います。
- `occurrence_locations` は immutable snapshot、path、stable locator、任意の行範囲、
  observation、evidence command/output を保持します。
- absence defect は bounded search universe、snapshot、exact query、zero-match または
  missing-field result で表現し、架空の source location を作りません。
- cross-surface disconnect は broken invariant を示す producer / consumer の両端点を
  記録します。
- confirmed occurrence location がまだない場合だけ `defer_with_reason` と
  `need verification` に残し、root cause や required fix を confirmed として完成扱い
  しません。
- `.agents/skills/issue-finding-report/SKILL.md` は canonical owner への thin pointer を
  維持します。
- `project_template` は AgentCanon static seed の consumer であり、第二正本を持ちません。

## Validation evidence

Validated head `605ff5ba9e96140f0aae086cc44f22e499f804ca`:

- AgentCanon Static Gates / `static-gates`: success.
- Agent Runtime Dashboard / `dashboard`: success.
- Issue Mirror / `issue-mirror-check`: success.
- Entrypoint Owner Map: success.
- CodeQL: success with no new alert in the changed code.
- Failing or in-progress check: none.

## Durable closeout scope

- Move this record from `issues/open/` to `issues/closed/`.
- Set `status: resolved` and add `resolved_by:`.
- Preserve the confirmed occurrence evidence and implementation trace.
- Change no skill policy, runtime shim, project template, workflow, checker, or schema in this
  closeout change.

## Closeout evidence

- PR #753 was merged only after current main equaled its base, all protected checks succeeded,
  and review submissions and review threads were both zero.
- Merge commit `5e6d88e49049bd96115b2b0727ddc868f19a6ff7` contains only the canonical skill contract and
  its durable Issue record; no project_template implementation was added.
- The first protected-main Issue Mirror sync correctly projected the still-open durable record
  and therefore reopened GitHub Issue #752. PR #756 moves the canonical record to
  `issues/closed/` with `status: resolved`, preventing future main-push sync from restoring the
  obsolete in-progress state.
- GitHub Issue #752 contains the branch, validated head, PR #753, merge commit, closeout PR #756,
  final review basis, checks, and label-reconciliation evidence.
