# Codex Intake

<!--
@dependency-start
contract agent-runtime
responsibility Owns task intake, checkout continuity, bounded context reading, and repository boundaries.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
@dependency-end
-->

Use [Codex Workflow](CODEX_WORKFLOW.md) to select the current phase.

## Optional Context

Read the row that can resolve the current decision. For Skills, use the
[owner-first reading rule](../skills/agent-orchestration.md#owner-first-read-trace).

| Missing decision or active operation | Read only the matching owner/slice |
| --- | --- |
| Repository purpose or workflow overview is unknown | [repository README](../../README.md), [agents overview](../README.md), or [workflow index](../workflows/README.md), whichever answers it |
| Task family or Skill route is unresolved | [routing](CODEX_ROUTING.md#contract-required-skill-set), [task families](../TASK_WORKFLOWS.md), selected `$agent-orchestration` / task-family Skill; [Skill index](../skills/README.md) only for discovery |
| Implementation execution is active | selected `$codex-task-workflow` and task-family Skill; [implementation](CODEX_IMPLEMENTATION.md#5-implementation) |
| Checkout/dependency identity changed or is not established | [identity readback](../COMMUNICATION_PROTOCOL.md#checkout-identity-readback), [branch reuse](#branch-reuse-default); unchanged commands do not retrigger it |
| Subagent delegation is selected | [subagents](CODEX_SUBAGENTS.md); role candidates do not activate themselves |
| A file must be placed or moved | [placement](ARTIFACT_PLACEMENT.md); an existing in-scope path needs no placement survey |
| An active review requires its process | [review process](../../documents/conventions/REVIEW_PROCESS.md) |
| Coordination is required by the selected route | [coordination](../../documents/codex/AGENTS_COORDINATION.md) |
| Python is being edited | [Python conventions](../../documents/conventions/coding-conventions-python.md) |
| Note creation/retention or a structured learning finding is active | [notes lifecycle](../../documents/operations/notes-lifecycle.md), selected [learning Skill](../skills/agent-learning.md) |
| Validation obligations are unresolved | [profile/check matrix](../../documents/runtime/runtime-profiles-and-check-matrix.md); no environment-selection preflight |
| A dependency module is being changed | [dependency owner](../../documents/rule/dependency-module-changes.md) |
| A relevant unresolved hazard or prior failure is identified | the matching [guardrail](../../documents/notes/guardrails/README.md) or [engineering avoidance](../../documents/notes/guardrails/engineering_avoidances.md), not the entire collection |
| Product container work is explicitly in scope | the product's own container documentation and execution owner, not an assumed `docker/README.md` in every checkout |

## Agent Canon Freshness

通常のコード・文書変更は、既存の作業経路で着手します。親のテスト・Docker・CI・GPU は親の
既存 entrypoint を使います。AgentCanon source/runtime が変更対象の場合は
[AgentCanonの更新手順](../skills/agent-canon-update.md) を使います。

## Branch Reuse Default

同じ作業を担うbranch・PR・checkoutを継続します。作業場所、branch、目的と変更範囲は
現在の会話・Issueで確認し、`git status`、対象差分、`git worktree list` で実状態を読みます。
既存の差分・未公開commit・利用者ファイルを保持して進めます。

- 新しいbranchや作業場所が必要なら、標準の `git worktree add`、`git clone`、
  `git switch` を依頼された範囲で使います。新規配置の目安は `workspace/<topic>/<repo>`、
  branch名にはIssue番号を含めます。作成済みの配置はそのまま使います。
- 開始時とPR公開前は [mainの取込みと競合解消](../../documents/rule/repository-topic-clone.md#main取込みと競合解消)
  に従います。
- 衝突する書込みは同じcheckout内で順番に行い、既存の作業状態を保持します。
  他者の変更の採否が必要な部分は保留し、合意済みの独立作業を続けます。
- 利用を終えたcheckoutは、保持する内容の保存先と利用終了を確認し、
  `git worktree remove` または対象cloneの削除を使います。
- [標準Gitのcheckout手順](../../documents/rule/repository-topic-clone.md) を必要な操作に
  適用します。Gitがbranch・worktree・merge状態を所有し、会話・Issueが作業範囲を保持します。

## Context Sweep

実装、設計変更、文書改訂、実験計画の前に、repo evidence を根拠にします。
まず現在の cause、適用される constraints、変更後に必要な guarantee を特定し、
その判断を変える範囲だけを読みます。過去 task の context sweep や handoff は
既定の着手条件にせず、現在の cause/guarantee が同じ根拠を要求するとき
だけ再利用します。依頼された対象・成果物・受入条件を `requested_scope` として保持し、
その全体を満たす担当と検証を選びます。
未選択の出力を調査開始の前提にせず、profile / document bucket も request に無関係
である evidence がある場合だけ `not_applicable` にします。
担当による分割は作業順序を決めるために使います。実際の範囲更新は、共通の
[scope principle](../../ROOT_AGENTS.md#always-on-boundary) に従います。

- `documents/`
- repository-qualified GitHub Issue URLs/numbers and private packet locators
- private `agent-canon-log/knowledge/` (metadata and locator only)
- `documents/notes/knowledge/`
- `documents/notes/guardrails/`
- `documents/notes/failures/`
- `documents/notes/themes/`
- `documents/notes/branches/`
- `documents/notes/worktrees/`
- `documents/notes/experiments/`
- `references/`

memory は固定 packet/read の対象にしません。owner/path、failure evidence、recurrence
decision が選択された後、必要な topic だけを `agent-canon k search` / `k read` で private
logへ on-demand に検索します。stable preference は対象 owner への明示変更として扱います。

Search hits and nominated paths are candidates, not edit authority. Confirm the
selected owner and affected callers/consumers; follow only dependency edges that
can change scope or validation.
Before splitting or retiring an implementation, use the shared
[owner and retirement rule](../../ROOT_AGENTS.md#always-on-boundary) to check
existing assets and callers. A bounded edit needs no broad history scan. When
the next action is settled, proceed through its owner; read the relevant owner
before interpreting or repairing tool output.

## Missing File Or Path Triage

file や path の欠落を見つけたときは、再作成、削除済み判定、repo-local 例外扱いの前に template と shared canon を確認します。

1. current repo で、欠落している path が root symlink view、synced root copy、shared workflow / skill / tool / memory surface、または template 由来の scaffold かを確認する
1. template root または登録された template remote / current template main で同じ path の有無と現在の正本形を確認する
1. standalone AgentCanon source checkout と親の development checkout で同じ path の有無、rename、移動、外部 runtime への移行理由を確認する
1. AgentCanon-owned surface なら [documents/runtime/bootstrap-runtime.md](../../documents/runtime/bootstrap-runtime.md)、[documents/runtime/runtime-log-archive.md](../../documents/runtime/runtime-log-archive.md)、および選択した owner Skill に従い、standalone source update、shared runtime update、または意図的削除のどれかに分類する
1. template と canon のどちらにも無く、task 固有に必要な file だけを新規作成候補にし、既存実装・文書で足りない理由を説明する

欠落を見つけた agent は、handoff や review artifact に `missing_file_triage` として確認した template path、canon path、分類、次 action を記録します。
欠落 path の判断は、template / canon 確認後の `missing_file_triage` に基づけます。

## Repository Task Boundary

普通の相談、壁打ち、routing-only advice、説明だけの turn は conversational
turn として扱います。その場合は会話だけで応答します。

GitHub Actions run、PR check、GitHub Issue を読むだけの GitHub-only read
inspection は GitHub inspection として扱います。

local repo state 確認、file edit、validation、PR / issue mutation、local CI
実行、または実装作業へ切り替わった時点で repository task として扱い、
切り替えをユーザー向け update で明示してから通常の workflow gate に入り
ます。

LCPの全文規則は [`agent-orchestration.md#Local Capability Priority`](../skills/agent-orchestration.md#local-capability-priority) が所有します。このworkflowは、LCPが選択された場合に、そのownerが選んだ既存canonical recordのlocatorだけを参照します。

## ユーザー向け言語

ユーザー向けの作業更新、最終報告、レビュー要約、handoff guidance、
reader-facing docs は日本語で書きます。機械可読の key、command、path、
role id、schema は正本表記を保ちます。

handoff では、この言語方針を必要な文脈とともに伝えます。

## 1. Intake

- ユーザー要求から変更対象と acceptance criteria を短く固定する
- その範囲で必要な context sweep と library sweep を行い、owner・変更面から
  route と検証を選ぶ。調査結果による具体化を、要求範囲の無断拡張と混同しない
- must-do、must-not-do、completion-evidence の clause ID は既存 task record に残し、
  coordination/resumption が要求する場合だけ選択 owner の artifact route を使います。
  bounded one-writer task は owner/path/validation note で閉じます。
- 各 clause に source bucket を付け、`current_request`、`durable_user_preference`、`repo_or_code_precedent`、`domain_or_external_constraint`、`unknown_or_open_question` を混ぜずに扱う
- 質問・deferred / escalation の前に [Decision Order](../skills/agent-orchestration.md#decision-order) で Goal 全体の有効な合意・進捗・残件を確認し、取得できる根拠から不明点を解決する
- 本人の判断・入力・必要な権限が残る場合は、確認済みの根拠と依存する clause を既存記録に明示し、その clause を未完了として保持する。独立した認可済み作業は継続する
- durable user preference は今回 request や repo evidence と結び付いたときだけ task requirement へ昇格する
- 着手時の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- skill を user-facing に書くときは `$skill-name` を既定にし、`skills=<...>` でも同じ表記を維持する
- agent-side の再発防止知識を残す必要がある場合は、選択済み context で
  `agent-canon k search --query <failure-evidence>` を先に実行し、既存 topic は同じ private
  topicへ追記します。独立 topicだけを `agent-canon k/f add` で記録します。raw chatはprivate
  logへそのまま追記しません。
