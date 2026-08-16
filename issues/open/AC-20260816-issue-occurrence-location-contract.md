<!--
@dependency-start
contract issue
responsibility Tracks the requirement that generated Issues identify confirmed defect occurrence locations.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
upstream design ../../agents/skills/issue-finding-report.md canonical issue-production workflow
downstream design ../../.agents/skills/issue-finding-report/SKILL.md runtime discovery adapter
@dependency-end
-->

# [Issue記載品質] 問題の発生箇所を具体指定する

issue_id: AC-20260816-issue-occurrence-location-contract
status: in_progress
source: user
severity: S2
problem: issue-finding-reportがaffected surfaceとevidenceの存在だけを要求し、問題を観測したsource/artifact snapshot、path、stable locatorを必須化していない。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/752
done: すべてのIssue候補がconfirmed occurrence locationを持ち、広い変更候補と観測位置を区別し、欠落問題とcross-surface disconnectも再調査なしで追跡できる。
affected_surfaces: agents/skills/issue-finding-report.md, .agents/skills/issue-finding-report/SKILL.md, project_template/agent-canon-static-seed.json
edit_scope: owner-bounded
required_action: canonical skillのpacket、location schema、Issue body contract、completion guardを更新し、runtime shimとtemplate consumer境界を検証する。
close_condition: branch、PR、validation evidenceがIssue #752から追跡でき、statusがready for reviewになる。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/752

## Finding

Issue の本文に repository や広い affected surface が書かれていても、どの
function、config key、document heading、artifact field、command phase で問題を
観測したかを必須にする契約がありません。このため、後続担当者が同じ調査を
繰り返さないと修正起点を確定できません。

## Occurrence Locations

### Location 1: packet schema が候補 surface だけを保持する

```text
repository: iwashita-nozomu/agent-canon
snapshot: 84f2b06a6f5e6e2b3727da7d5af83c0746d9835f
path: agents/skills/issue-finding-report.md
locator_type: heading
locator: ## Multi-Agent Partition -> Issue Finding Packet -> affected_surfaces
lines: unavailable:connector inspection used a stable Markdown anchor instead of a line-only locator
observation: packet has candidate affected_surfaces but no field for confirmed observed locations.
evidence: file content at the recorded commit lists affected_surfaces followed by duplicate_search without an occurrence-location record.
```

### Location 2: Issue completion contract lacks a concrete locator requirement

```text
repository: iwashita-nozomu/agent-canon
snapshot: 84f2b06a6f5e6e2b3727da7d5af83c0746d9835f
path: agents/skills/issue-finding-report.md
locator_type: heading
locator: ## Issue Candidate Contract -> "Populate the minimum issue form" and "Issue body sections"
lines: unavailable:connector inspection used stable sentence and heading anchors
observation: the contract requires problem/evidence/done and Finding/Abstract Cause/Required Fix/Evidence, but no confirmed occurrence-location section or completion guard.
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

## Abstract Cause

The workflow conflated two different objects:

- candidate edit or verification scope $A$;
- confirmed observation locations $O$.

$A$ says where work may be required; it does not identify $O$. A usable Issue
needs an evidence-backed trace from every observation in $O$ to the proposed
work in $A$. Treating `affected_surfaces` as occurrence evidence drops that
trace and forces the next owner to repeat discovery.

## Required Fix

Add a location record requiring immutable snapshot identity, concrete path,
stable locator, optional snapshot-relative line range, observation, and evidence.
Define explicit handling for absence findings and producer/consumer disconnects.
An Issue with no confirmed location must remain investigation/`need verification`
rather than being presented as a confirmed root-cause repair task.

## Evidence

- GitHub Issue: https://github.com/iwashita-nozomu/agent-canon/issues/752
- AgentCanon base: `main@84f2b06a6f5e6e2b3727da7d5af83c0746d9835f`
- project_template base: `main@ef503efdb829fb7017cde994d523241f0e8cf187`
- active branch: `fix/752-issue-location-contract`
