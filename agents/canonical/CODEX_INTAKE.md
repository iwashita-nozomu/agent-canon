# Codex Intake

<!--
@dependency-start
contract agent-runtime
responsibility Owns task intake, checkout continuity, bounded context reading, and repository boundaries.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
@dependency-end
-->

Read the selected section for task intake or a change to the relevant checkout/context.
Return to [Codex Workflow](CODEX_WORKFLOW.md) for phase selection; do not
load inactive phases or restart completed intake merely by following a link.

## Optional Context

These are lookup routes, not a startup checklist. Read a named section only
when its fact can change the current decision; stop once that fact is resolved.
Reuse already loaded instructions and selected owners. Inactive rows require
neither reading nor a `not_applicable` inventory unless an active contract asks.
Selected Skills retain their existing full-body/EOF admission; delegated
canonical documents require only the selected section, not every linked file.

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

The former Base Runtime Packet / Cross-Cutting Packet lists are represented by
these conditions, not by an unconditional bundle. A configured route may require
a specific slice; the index does not itself activate that route. Read generated
`.codex/personal/skills/<selected-skill>/SKILL.md` only for a selected Skill.

## Agent Canon Freshness

通常のコード・文書変更は、既存の作業経路で要求差分へ着手します。環境診断・変更の
適用条件は [ROOT_AGENTS.md の Always-On Boundary](../../ROOT_AGENTS.md#always-on-boundary)
に従います。この節は、task 開始ごとの source/parent 環境分類、freshness preflight、
AgentCanon の更新・再構築を要求しません。

- AgentCanon source/runtime の変更が今回の要求範囲にある場合だけ、standalone source checkout から `$agent-canon-update` と `$pr-processing` に入ります。親repoへlive root view、vendor、submodule pinを同期しません。consumer root [AGENTS.md](../../AGENTS.md) は、親が明示 composer で common [ROOT_AGENTS.md](../../ROOT_AGENTS.md) と consumer-specific text を合成して通常 file として管理します。
- 親で AgentCanon source の変更を所有する場合だけ、repository-topic lifecycle の `<anchor>/workspace/<topic>/agent-canon` checkout と既存 cleanup route を使います。親の product test、Docker、CI、GPU は親の既存 entrypoint で実行し、AgentCanon runtime はそれらを発見または mount しません。root instruction composition は runtime projection ではありません。
- Issue 修正の作業 branch は開始時と PR 公開前に最新 main を取り込み、競合があればその変更範囲で解消します。包含済みなら merge は no-op です。これは作業 source の統合であり、runtime 更新や環境構築ではありません。別の AgentCanon 保守 PR の merge・配布完了を、本題へ戻る前提にしません。
- 必要な検証が実行不能なら、失敗した command、理由、未検証の性質を既存 Issue / PR に残し、その操作と独立した編集・差分確認・PR 公開を続けます。未実施を成功扱いせず、対象外の環境修理・再構築や他 Issue の完了を終了条件へ追加しません。診断だけで環境変更は認可されません。

## Branch Reuse Default

既存 branch / PR が現在の task、追加 user instruction、または follow-up と同じ ownership surface を担える場合は、その branch / PR を継続します。通常の branch / worktree 作成 route は、作成前に creation authority と理由を記録します。force-create または ref overwrite を含む route だけが、creation と destructive の両方を要求します。

- 同じ checkout は複数 chat/session が同時に使う場合があります。unknown dirty/staged/untracked state と branch/worktree state は user または別 chat 所有として保存します。`git restore`、`git reset`、forced `git clean`、mutating `git stash`、checkout/switch、branch/worktree create/delete/move/rename/prune は protected Git mutation として扱います。proven exact task ownership は approval request に含める path を限定し、explicit destructive approval は引き続き必須です。
- Git authority は操作リスクで分けます。通常の branch create / worktree add は同じ command segment の creation authority/reason のみを要求し、force-create または ref overwrite は creation と destructive authority/reason の両方を要求します。既存 branch の checkout/switch、branch/worktree の delete/rename/prune、reset、restore、forced clean、mutating stash、およびその他の履歴/参照破壊操作は destructive authority/reason を要求します。`latest` / `apply` / merge update wrapper は実際に branch/worktree を作成する owner route でない限り destructive authority/reason のみを要求します。`branch --set-upstream-to`、`branch --unset-upstream`、`branch --edit-description` などの tracking/description metadata 操作と、reversible な `worktree lock/unlock` は ref、履歴、worktree を変更しないため protected destructive Git mutation ではありません。worktree の remove/move/repair/prune/force-add は protected operation です。ambient 変数や prior segment は authority になりません。
- destructive Git safety は `tools/runtime/authority/hook_safety.py` の pure owner を dispatcher が呼び出します。session 開始時に dispatcher registration を load 済みの session では次の tool call から更新後 script が効きます。hook table 自体が未 load の既存 session は session restart 後に保護対象になります。
- 衝突時は current branch/worktree を維持し、status を保存して user の指示を待ちます。

- `repository_topic_clone.py` と `dependency_module_change.py` の canonical
  `prepare` / `merge-main` は、非空 owner evidence と computed
  `workspace/<topic-slug>/<repo-name>` identity が揃う repo-local topic workspace に限り、
  operation-level の追加承認なしで dispatch できます。reuse は `prepare` に含まれます。
  これは lifecycle tool が管理する path の作成・再利用・使用だけを対象とし、shared
  checkout の raw Git mutation や protected update wrapper の authority を免除しません。
- `dependency_module_change.py status` は adapter-only の read-only command で、owner
  evidence を要求せず、generic repository-topic lifecycle または operation-level approval
  carve-out の権限を持ちません。
- closeout は `repository-topic-clone` または `dependency-module-change` skill の
  `cleanup` dispatch を経由します。computed clone identity、owner/marker evidence、
  clean state、remote head/tree readback を渡し、ordinary `CleanupProof` / receipt が
  返った場合だけ `--apply` を受理します。publication artifacts は存在する場合だけ
  coherent enrichment として保持します。proof 不足、collision、unknown dirty state は
  checkout/topic root を保持して typed hold として記録します。

- 通常 task の authority は、user が別 branch を明示した場合の `user_request` です。AgentCanon source update の authority は、AgentCanon branch / PR workflow と canonical update tool が owner の `agent_canon_workflow` です。
- 「fresh start」「dirty state 回避」「追記の分離」「task 途中の追加指示」「既存 PR の checklist 追記」は、既存 branch / PR 継続の理由として扱います。
- branch / worktree 作成前に run bundle、work log、または PR body へ `branch_creation_reason=<reason>` または `worktree_creation_reason=<reason>` と authority 対応箇所を記録します。それだけでは実行権限になりません。current-task user approval 後の同じ shell segment に、通常作成なら creation authority/reason、force-create/ref overwrite なら creation と destructive の両 authority pair を置いた場合だけ実行できます。
- AgentCanon source 変更は standalone source checkout を source owner とし、branch / ahead / diverged / dirty state を evidence として collision-safe merge / review を続けます。親で作業する場合は repository-topic lifecycle の `<anchor>/workspace/<topic>/agent-canon` checkout を再利用します。親の pin や root projection は作成しません。
- standalone source の変更は非並列 single-stream の既定です。write-capable handoff を並列化する場合は、各 handoff に repository-topic-clone で準備済みの `writer_target`（絶対 checkout_root、固定 branch、正規化済み remote、allowed_paths）を付け、同じ checkout_root は spawn 前に拒否します。独立 stream の workspace placement は、replaceable responsibility unit、disjoint write scope、依存/merge order、validation route、reviewer ownership を固定して選択します。parent は ready な全 stream を launch し、全 descendant を monitor し、同一責任・同一 worker context を再利用します。細粒度の fresh-agent fan-out は独立 stream とみなしません。
- repository source は `repository-topic-clone` の一つの prepare route で扱います。exact identity の既存 checkout と named local/remote branch は再利用し、branch が無い場合だけ最新 `origin/main` から作成します。parent または同一 repository の branch は `linked-worktree`、dependency repository は `independent-clone` を選び、どちらも同じ `<anchor>/workspace/<topic>/<repo>` placement にします。各 source branch は candidate review / PR 前に integration executor が最新 `origin/main` を通常 merge し、conflict はその owner が状態を保持して意図的に解消します。競合を検出したら `conflict_preservation.py` で merge-base、base/ours/theirs の stage/blob、hunk、unaffected user/unknown content、disposition、原因、期待機構、正確な edit delta を記録し、解消後の保存 readback を通します。whole-file checkout/reset/reclone/overwrite/regeneration は reconstruction map なしでは不許可です。`origin/main` の read/CAS だけでは merge 済みの代替になりません。writer target は短命な handoff 値であり、claim、PID、expiry、daemon、writer registry は作成しません。

## Context Sweep

実装、設計変更、文書改訂、実験計画の前に、repo evidence を根拠にします。
context sweep は `requested_scope` を保存したうえで work packet を作る手順です。
先に user request から要求された file、workflow、check、doc、PR state を
`requested_scope` として固定し、task topic、runtime profile、implementation
surface router、semantic-index / context-pack、dependency review の structured
output で `work_scope` を段階化します。選ばれなかった profile / document bucket
は、request に無関係である evidence がある場合だけ `not_applicable` にします。
Large delivery / Shared canon でも、bounded responsibility route は作業順序を
決める artifact です。対象範囲の正本は `requested_scope` に残します。読む
slice を選ぶ場合は、coverage map に `covered_surfaces`、`deferred_surfaces`、
`omitted_surfaces` と理由を残してから進めます。

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

raw text search の hit だけで編集対象を決めません。
user、parent、handoff、router が示した path は候補として保存し、候補の確定と edit owner の確定を同一視しません。編集に入る前に既存の [`Owner-First Read Trace`](../skills/agent-orchestration.md#owner-first-read-trace) で selected Skill と operational owner を解決し、必要な dependency/downstream edge を入口、呼び元、実装、consumer、既存 test のうち判断を変える面へ bounded にたどって、候補が本当にその owner の差し替え可能な単位かを確認します。判断を変えない面は既存の `covered_surfaces`、`deferred_surfaces`、`omitted_surfaces` に理由付きで分類し、候補が支持されない場合は route を更新してから編集します。検索 hit を修正 surface にする場合は、hit path を保存し、dependency header graph と責務 owner で edit scope を展開します。owner boundary、差し替え可能な単位、validation route、`external public API/behavior/schema unchanged` が evidence で閉じたら、implementation-executable TargetStateContract に固定された complete responsibility unit を作ります。write-capable child handoff は `agents/task_catalog.yaml#workflow_activation_policy` が要求する typed route だけで materialize します。空の unresolved-decision set は即時に選択 route へ遷移し、owner gate は完了後だけです。明示された bounded owner/path/targeted-validation request も同じ typed route で扱います。
asset reuse investigation は decomposition / prototyping より前に行います。
split / extraction または suspected predecessor の現行欠落では splitter が
current module/helper/type/test/docs と `git log`、`-S`、deleted paths、prior PR /
Issue、predecessor tests を調査します。bounded non-split edit には historical
scan を一律適用しません。known な asset path、capability、disposition、reason、
test paths は既存 `reuse_survey` に advisory context として載せ、選択した asset
と test context から slice を導きます。同一 asset に触れる slice を merge してから
child handoff に同じ known context を渡します。context の不在は dispatch または
writing を block しません。
bounded route では、existing tool の実行と patching を tool-owned evidence から開始します。#335 の既存 tool 先行実行は維持しますが、結果の解釈や修正に入る前に、生成された compact `SKILL.md` を `bootstrap.sh ... tool run --root <registered-project> skill-document-reader -- ...` で `file_eof=true` まで読みます。Skill が委譲する場合だけ、canonical owner document の必要な見出しを `section_eof=true` まで読みます。canonical ファイル全体の EOF は要求しません。`implementation_read=ready` はこの条件を満たしたときだけ使い、可視 prefix や既知 path だけでは unlock しません。bounded route は route と validation profile の signal であり、実装 behavior は契約完全実装ポリシーから導きます。

## Skill read admission

The canonical [`agent-orchestration` Owner-First Read Trace](../skills/agent-orchestration.md#owner-first-read-trace)
owns compact `SKILL.md` EOF/section-EOF/readback requirements and the
no-duplicate-receipt/body rule. This workflow preserves its existing-tool-before-read
exception and sets `implementation_read=ready` only after that owner trace and
any delegated sections reach their required EOF.

```bash
git grep -l "topic keywords" -- <responsibility-scoped dirs> \
  | sed -n '1,200p' > reports/search_hits.txt
bash tools/analysis/dependencies/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --search-hits-file reports/search_hits.txt
```

`dependency_edit_scope.txt` は path artifact として残します。会話、Issue、PR body、または run bundle の本文には、件数、主要 path、編集した file、確認した file、意図的に外した candidate だけを書きます。

## Missing File Or Path Triage

file や path の欠落を見つけたときは、再作成、削除済み判定、repo-local 例外扱いの前に template と shared canon を確認します。

1. current repo で、欠落している path が root symlink view、synced root copy、shared workflow / skill / tool / memory surface、または template 由来の scaffold かを確認する
1. template root または登録された template remote / current template main で同じ path の有無と現在の正本形を確認する
1. standalone AgentCanon source checkout と親の development checkout で同じ path の有無、rename、移動、外部 runtime への移行理由を確認する
1. AgentCanon-owned surface なら [documents/runtime/bootstrap-runtime.md](../../documents/runtime/bootstrap-runtime.md)、[documents/runtime/runtime-log-archive.md](../../documents/runtime/runtime-log-archive.md)、および選択した owner Skill に従い、standalone source update、shared runtime update、または意図的削除のどれかに分類する
1. template と canon のどちらにも無く、task 固有に必要な file だけを新規作成候補にし、既存実装・文書で足りない理由を run bundle に残す

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

repo-changing run では `team_manifest.yaml` の
`run.user_facing_language_policy` を handoff packet に含め、subagent と reviewer
が同じ方針を参照できる状態で渡します。`bootstrap_agent_run.py` と
`bootstrap_agent_run.py` の `USER_FACING_LANGUAGE=ja` を起動時 evidence として
扱います。

## 1. Intake

- context sweep と library sweep を先に行う
- 変更対象と acceptance criteria を短く固定する
- `user_request_contract.md` に must-do、must-not-do、completion-evidence の clause ID を書く
- coordination、resumption、または selected workflow が要求する場合だけ `schedule.md` を TODO 正本として materialize し、stage plan / clause coverage / planned work units を concrete にする。bounded one-writer task は owner/path/validation note で閉じる
- 各 clause に source bucket を付け、`current_request`、`durable_user_preference`、`repo_or_code_precedent`、`domain_or_external_constraint`、`unknown_or_open_question` を混ぜずに扱う
- 不明点は notes、guardrails、documents、prior logs、local code / tests で解決できるかを `Requirements Resolution Sweep` に記録してから deferred / escalation を決める
- active な must-do、must-not-do、completion-evidence clause に `unknown_or_open_question` を残さない
- durable user preference は今回 request や repo evidence と結び付いたときだけ task requirement へ昇格する
- 着手時の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- skill を user-facing に書くときは `$skill-name` を既定にし、`skills=<...>` でも同じ表記を維持する
- agent-side の再発防止知識を残す必要がある場合は、選択済み context で
  `agent-canon k search --query <failure-evidence>` を先に実行し、既存 topic は同じ private
  topicへ追記します。独立 topicだけを `agent-canon k/f add` で記録します。raw chatはprivate
  logへそのまま追記しません。
