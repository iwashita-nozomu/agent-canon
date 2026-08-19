<!--
@dependency-start
contract issue
responsibility Records the direct escalation contract for AgentCanon-owned defects discovered during consumer repository work.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
upstream design ../../agents/skills/issue-finding-report.md canonical issue-production and occurrence-location workflow
@dependency-end
-->

# [障害エスカレーション] AgentCanon起因問題をconsumer内で回避せず上流Issue化する

issue_id: AC-20260819-agentcanon-defect-upstream-escalation
status: in_progress
source: user
severity: S2
problem: 進行中のconsumer作業でAgentCanon起因の問題を確認しても、発生条件・発生箇所を固定して上流Issueへ送るadmission ruleとconsumer内回避実装の禁止境界がない。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/784
done: AgentCanon起因問題が再現条件とconfirmed occurrence locationを伴う上流Issueへ送られ、consumer Issueのscopeと終了条件を拡張せず、consumer内回避策を解決扱いしない。
affected_surfaces: agents/skills/issue-finding-report.md, issues/open/AC-20260819-agentcanon-defect-upstream-escalation.md
edit_scope: owner-bounded
required_action: canonical issue-production skillにdirect AgentCanon defect escalation packet、owner判定、upstream Issue作成、consumer scope分離、local workaround禁止を追加する。
close_condition: canonical skillとdurable recordがPRでreview可能になり、current mainを取り込んだheadでrequired checksが成功する。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/784

## Finding

`issue-finding-report` は、蓄積ログや反復挙動を abstract cause ごとにまとめる
経路と、Issue 候補に immutable snapshot、path、stable locator、observation、
evidence を要求する経路を持っています。しかし、別リポジトリの作業中に failure
の正本が AgentCanon 側だと判明した場合を activation condition に含めていません。

そのため、同じ failure を consumer 側の copy、symlink、fallback、bypass、
validation 緩和、例外 config で隠し、AgentCanon の発生条件・発生箇所・修正履歴を
残さない余地があります。

## Occurrence Locations

### Location 1: direct-task admission がない

```text
repository: iwashita-nozomu/agent-canon
snapshot: 0ea5bb6d5d0bfc2e027698612aeb6fc5a3c8b0c2
path: agents/skills/issue-finding-report.md
locator_type: heading
locator: ## Use When
lines: unavailable:connector inspection used the stable Markdown heading and anchored bullet text
observation: activation conditions are accumulated logs, dashboard signals, repo-wide sweep, and recurring behavior; an active consumer task that identifies an AgentCanon-owned defect is not named.
evidence: main snapshot content under `## Use When` contains only the four accumulated/repeated-evidence routes.
```

### Location 2: consumer-local workaround boundary がない

```text
repository: iwashita-nozomu/agent-canon
snapshot: 0ea5bb6d5d0bfc2e027698612aeb6fc5a3c8b0c2
path: agents/skills/issue-finding-report.md
locator_type: heading
locator: ## Issue Candidate Contract
lines: unavailable:connector inspection used the stable Markdown heading and ordered contract clauses
observation: duplicate search, dependency expansion, occurrence location, durable record, and GitHub mirror requirements exist, but the current consumer Issue scopeを保つこととconsumer内回避実装を禁止するdispatch ruleがない。
evidence: the ordered contract has no clause for upstream-owner detection, consumer workaround prohibition, or cross-link-only dependency handling.
```

### Location 3: template は第二正本にできない

```text
repository: iwashita-nozomu/project_template
snapshot: 45d99b4d0fe8510c55db7cd13af37d46f86506f9
path: AGENTS.md
locator_type: heading
locator: # Repository instructions -> self-contained/static snapshot bullets
lines: unavailable:connector inspection used stable sentence and bullet anchors
observation: project_template is a self-contained static consumer and `.codex/` is a repository-owned read-only snapshot; AgentCanonの障害エスカレーション手順をtemplate側の第二正本として追加できない。
evidence: the recorded snapshot states that tracked project files are source of truth and static snapshots update only through explicit maintainer import.
```

## Abstract Cause

失敗 invariant を `f`、その canonical owner を `owner(f)` とします。
`owner(f) = AgentCanon` が bounded evidence で確定した後も consumer repository を
修正すると、原因 owner と修正 owner が分離し、同じ障害が別 consumer で再発します。

したがって、direct route の admission は単なる近接 path や vendored copy ではなく
`owner(f) = AgentCanon` の確認です。確認後は consumer workaround ではなく、
AgentCanon snapshot、failure condition、expected/actual、confirmed occurrence
locations、duplicate search を一つの上流 Issue に固定します。

## Required Fix

- current task で AgentCanon ownership が確認された場合を `issue-finding-report` の
  direct activation condition に追加する。
- `consumer_task`、`agentcanon_snapshot`、`failure_condition`、
  `expected_behavior`、`actual_behavior`、`occurrence_locations`、
  `duplicate_search`、`consumer_scope_disposition`、`upstream_issue` を一つの
  escalation packet として固定する。
- cross-repository disconnect では consumer observation endpoint と AgentCanon
  owner endpoint の両方を記録する。
- matching durable Issue を link し、存在しなければ local record と GitHub mirror を
  issue / PR publication owner 経由で作る。
- current consumer Issue の requested scope と completion criteria を維持し、
  AgentCanon Issue は dependency / blocker としてのみ cross-link する。
- AgentCanon finding を consumer-local copy、symlink、monkeypatch、source override、
  fallback、bypass、validation weakening、exception config で解決扱いしない。
- ownership または occurrence location が未確定なら root cause / required fix を
  確定扱いせず、`need verification` を伴う investigation に残す。

## Scope Boundary

変更対象は canonical skill とこの durable record だけです。

- `project_template` は consumer boundary の証拠であり、policy の第二正本を追加しません。
- public skill identity、catalog schema、generic blocker state machine、bot、
  auto-fix、consumer workaround は変更しません。
- 元の consumer Issue の範囲外にある AgentCanon 修正を、その Issue の終了条件へ
  追加しません。

## Validation

- `python3 tools/agent_tools/issue_sync.py --root .`
- `python3 tools/agent_tools/check_skill_frontmatter.py --root .`
- `python3 tools/agent_tools/skill_tool_commands.py check`
- `python3 tools/agent_tools/check_dependency_headers.py --changed`
- `bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing`
- `bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header`
- protected checks: `static-gates`, `dashboard`, `issue-mirror-check`
