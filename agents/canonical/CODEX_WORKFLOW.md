<!--
@dependency-start
contract agent-runtime
responsibility Documents Codex Workflow for this repository.
upstream design ../../ROOT_AGENTS.md root runtime entrypoint
upstream design ./CODEX_SUBAGENTS.md subagent routing contract
upstream design ../workflows/agent-canon-pr-workflow.md standalone source PR workflow
upstream design ../../issues/README.md durable AgentCanon operational finding storage
downstream design ../workflows/token-efficient-codex-workflow.md token-aware runtime mode overlay
downstream design ../../templates/agents/closeout_gate.md closeout gate contract
upstream design ../../documents/design/dependency-manifest-design.md dependency manifest design
upstream design ../../documents/design/semantic-responsibility-contract.md semantic delta and verification-owner contract
upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md runtime profile and risk-based validation routing
upstream design ../../documents/operations/BRANCH_SCOPE.md commit correctness and push contract
upstream design ../skills/tool-finding-report.md tool finding packet and prompt feedback workflow
downstream implementation ../../tools/agent_tools/task_close.py enforces closeout keys
@dependency-end
-->

# Codex Workflow

この文書は、Codex でこの repo を扱うときの標準フローです。
毎回同じ順序と repo evidence で進められるようにします。

## Reader Map

- This document owns the Codex task execution path from intake through completion, including routing, profile selection, implementation flow, and closeout.
- The early sections define startup reads and intake sweep; the middle sections classify tasks, completion bars, skills, and execution flow; the final section captures Codex-specific runtime rules.
- Start at `## Start Here` for any task, then jump to `## Required Intake Sweep` for repo state, `## Task Classification` for workflow selection, and `## Execution Flow` before implementation.
- For chunked reading, keep this map and `## Start Here` as the anchor, then load only the active profile or rule section named by the current run bundle.

## Start Here

1. `AGENTS.md` を読む
1. `agents/skills/README.md` と `$agent-orchestration` skill を読み、routing mode と skill set を先に決める
1. `agents/TASK_WORKFLOWS.md` で task family を決める
1. Runtime profile と implementation owner がまだ固定されていない repo-changing task では、広い packet 読解より先に canonical router / semantic-index / dependency review の structured output を取る
1. read-only worktree check で、必要なら別の AgentCanon source clone を使うかを分類する。AgentCanon source はこの repository か、親の `workspace/agent-canondevelop/<qualified-task>/agent-canon` にある独立 clone だけを扱う。更新が必要なら current checkout を保持し、standalone topic branch / PR workflow に入る。source branch の dirty / unpushed / divergent state は evidence として保持し、detached state は source owner identity repair へ route する
1. 選択された workflow/profile が必要とする Base Runtime Packet だけを読む。inactive profile の packet は `not_applicable` として記録する
1. Cross-Cutting Packet は選択 route、review gate、または structured tool finding が必要にした slice を読む
1. 実装を伴う task では `agents/workflows/implementation-waterfall-workflow.md` を読む
1. subagent を使う task では `agents/canonical/CODEX_SUBAGENTS.md` を読む
1. `agents/canonical/ARTIFACT_PLACEMENT.md` で文書の置き場を決める
1. 必要なら `.agents/skills/` から該当 skill を読む

Base Runtime Packet:

- `README.md`
- `agents/workflows/README.md`
- `agents/README.md`
- `agents/TASK_WORKFLOWS.md`
- `agents/canonical/CODEX_WORKFLOW.md`

Cross-Cutting Packet:

- `documents/conventions/REVIEW_PROCESS.md`
- `documents/codex/AGENTS_COORDINATION.md`
- `documents/conventions/coding-conventions-python.md`
- `documents/operations/notes-lifecycle.md`
- `agents/workflows/agent-learning-workflow.md`
- `documents/runtime/runtime-profiles-and-check-matrix.md`
- `documents/rule/dependency-module-changes.md`
- `documents/notes/guardrails/README.md`
- `documents/notes/guardrails/engineering_avoidances.md`
- `docker/README.md`

## Required Intake Sweep

### Agent Canon Freshness

task 開始時は read-only worktree check で、現在の AgentCanon source clone と親の作業領域を分類します。preflight の contract は checkout-preserving read-only classification です。更新が必要な場合は standalone topic branch / PR route に入ります。

- AgentCanon source/runtime変更は standalone cloneから `agents/workflows/agent-canon-pr-workflow.md` に入り、AgentCanon branch / PR / merge / main readbackを閉じます。親repoへroot view、vendor、submodule pinを同期しません。
- 親で source の変更が必要な場合は、親の ignored `workspace/agent-canondevelop/<qualified-task>/agent-canon` に clone し、完了時に exact clone path を削除します。親の product test、Docker、CI、GPU は親の entrypoint で実行し、AgentCanon runtime はそれらを発見または mount しません。
- standalone AgentCanon source branch が remote main と divergeしている場合はfail-closedとし、source branchのrebase/merge判断、AgentCanon PR、merge後main readbackを完了してから実装へ戻ります。
- `bootstrap_agent_run.py` の freshness preflight は script path ではなく `--workspace-root` を対象にします。親から起動したときは AgentCanon source clone の存在、runtime root の containment、source-unchanged readbackを確認します。`skipped_source_canon` は AgentCanon source checkout がこの task の owner でない場合だけ妥当です。

### Branch Reuse Default

既存 branch / PR が現在の task、追加 user instruction、または follow-up と同じ ownership surface を担える場合は、その branch / PR を継続します。通常の branch / worktree 作成 route は、作成前に creation authority と理由を記録します。force-create または ref overwrite を含む route だけが、creation と destructive の両方を要求します。

- 同じ checkout は複数 chat/session が同時に使う場合があります。unknown dirty/staged/untracked state と branch/worktree state は user または別 chat 所有として保存します。`git restore`、`git reset`、forced `git clean`、mutating `git stash`、checkout/switch、branch/worktree create/delete/move/rename/prune は protected Git mutation として扱います。proven exact task ownership は approval request に含める path を限定し、explicit destructive approval は引き続き必須です。
- Git authority は操作リスクで分けます。通常の branch create / worktree add は同じ command segment の creation authority/reason のみを要求し、force-create または ref overwrite は creation と destructive authority/reason の両方を要求します。既存 branch の checkout/switch、branch/worktree の delete/rename/prune、reset、restore、forced clean、mutating stash、およびその他の履歴/参照破壊操作は destructive authority/reason を要求します。`latest` / `apply` / merge update wrapper は実際に branch/worktree を作成する owner route でない限り destructive authority/reason のみを要求します。`branch --set-upstream-to`、`branch --unset-upstream`、`branch --edit-description` などの tracking/description metadata 操作と、reversible な `worktree lock/unlock` は ref、履歴、worktree を変更しないため protected destructive Git mutation ではありません。worktree の remove/move/repair/prune/force-add は protected operation です。ambient 変数や prior segment は authority になりません。
- destructive Git safety は `tools/agent_tools/hook_safety.py` の pure owner を dispatcher が呼び出します。session 開始時に dispatcher registration を load 済みの session では次の tool call から更新後 script が効きます。hook table 自体が未 load の既存 session は session restart 後に保護対象になります。
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
  clone/topic root を保持して typed hold として記録します。

- 通常 task の authority は、user が別 branch を明示した場合の `user_request` です。AgentCanon source update の authority は、AgentCanon branch / PR workflow と canonical update tool が owner の `agent_canon_workflow` です。
- 「fresh start」「dirty state 回避」「追記の分離」「task 途中の追加指示」「既存 PR の checklist 追記」は、既存 branch / PR 継続の理由として扱います。
- branch / worktree 作成前に run bundle、work log、または PR body へ `branch_creation_reason=<reason>` または `worktree_creation_reason=<reason>` と authority 対応箇所を記録します。それだけでは実行権限になりません。current-task user approval 後の同じ shell segment に、通常作成なら creation authority/reason、force-create/ref overwrite なら creation と destructive の両 authority pair を置いた場合だけ実行できます。
- AgentCanon source 変更は standalone source clone を source owner とし、branch / ahead / diverged / dirty state を evidence として collision-safe merge / review を続けます。親で作業する場合は ignored `workspace/agent-canondevelop/<qualified-task>/agent-canon` clone を再利用します。親の pin や root projection は作成しません。
- standalone source の変更は非並列 single-stream の既定です。独立 stream の workspace placement は、replaceable responsibility unit、disjoint write scope、依存/merge order、validation route、reviewer ownership を固定して選択します。parent は ready な全 stream を launch し、全 descendant を monitor し、同一責任・同一 worker context を再利用します。細粒度の fresh-agent fan-out は独立 stream とみなしません。
- repository source は `repository-topic-clone` の一つの prepare route で扱います。exact identity の既存 clone と named local/remote branch は再利用し、branch が無い場合だけ最新 `origin/main` から作成します。parent、dependency、standalone の区別は prepare 後の policy decorator です。各 source branch は candidate review / PR 前に integration executor が最新 `origin/main` を通常 merge し、conflict はその owner が状態を保持して意図的に解消します。`origin/main` の read/CAS だけでは merge 済みの代替になりません。

### Runtime Profile And Risk Selection

Establish structure, owner, and touched-surface evidence before selecting a
runtime profile. Use
`documents/runtime/runtime-profiles-and-check-matrix.md` only after that evidence fixes
the applicable validation and checker obligations.

- A runtime profile selects validation and checker obligations only. It does
  not limit context size, work scope, team mode, or task size.
- For every repo-changing implementation / patch / doc-edit work, including
  bounded owner/path/targeted-validation requests, use the selected
  write-capable `worker` / `spark_worker` handoff. Spawn or tool blockers produce
  typed blocked/retry/user-report evidence; the parent does not write.
- Record the selected profile and the evidence that made it applicable;
  inactive profiles remain unrecorded unless an active workflow explicitly
  asks for their status.

### Context Sweep

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
- `issues/`
- `memory/`
- `documents/notes/knowledge/`
- `documents/notes/guardrails/`
- `documents/notes/failures/`
- `documents/notes/themes/`
- `documents/notes/branches/`
- `documents/notes/worktrees/`
- `documents/notes/experiments/`
- `references/`

memory は固定 packet/read の対象にしません。owner/path、failure evidence、recurrence
decision が選択された後、必要な record だけを `agent-canon memory search` で on-demand
に検索します。stable preference は対象 owner への明示変更として扱います。

raw text search の hit だけで編集対象を決めません。
検索 hit を修正 surface にする場合は、hit path を保存し、dependency header graph と責務 owner で edit scope を展開します。owner boundary、差し替え可能な単位、validation route、`external public API/behavior/schema unchanged` が evidence で閉じたら、implementation-executable TargetStateContract に固定された complete responsibility unit を write-capable child handoff へ materialize します。空の unresolved-decision set は即時に one-pass handoff へ遷移し、owner gate は完了後だけです。明示された bounded owner/path/targeted-validation request も同じ child route で進めます。
bounded route では、existing tool の実行と patching を tool-owned evidence から開始します。runtime `SKILL.md` 読了は、対象 property を正本として持つ existing tool の実行後に必要な場合だけ使う follow-up context です。結果の解釈や修正に必要な owner surface だけを開きます。bounded route は route と validation profile の signal であり、実装 behavior は契約完全実装ポリシーから導きます。

```bash
git grep -l "topic keywords" -- <responsibility-scoped dirs> \
  | sed -n '1,200p' > reports/search_hits.txt
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --search-hits-file reports/search_hits.txt
```

`dependency_edit_scope.txt` は path artifact として残します。会話、Issue、PR body、または run bundle の本文には、件数、主要 path、編集した file、確認した file、意図的に外した candidate だけを書きます。

### Missing File Or Path Triage

file や path の欠落を見つけたときは、再作成、削除済み判定、repo-local 例外扱いの前に template と shared canon を確認します。

1. current repo で、欠落している path が root symlink view、synced root copy、shared workflow / skill / tool / memory surface、または template 由来の scaffold かを確認する
1. template root または登録された template remote / current template main で同じ path の有無と現在の正本形を確認する
1. standalone AgentCanon source clone と親の development clone で同じ path の有無、rename、移動、外部 runtime への移行理由を確認する
1. AgentCanon-owned surface なら `documents/runtime/bootstrap-runtime.md`、`documents/runtime/runtime-log-archive.md`、および選択した owner Skill に従い、standalone source update、shared runtime update、または意図的削除のどれかに分類する
1. template と canon のどちらにも無く、task 固有に必要な file だけを新規作成候補にし、既存実装・文書で足りない理由を run bundle に残す

欠落を見つけた agent は、handoff や review artifact に `missing_file_triage` として確認した template path、canon path、分類、次 action を記録します。
欠落 path の判断は、template / canon 確認後の `missing_file_triage` に基づけます。

### Repository Task Boundary

普通の相談、壁打ち、routing-only advice、説明だけの turn は conversational
turn として扱います。その場合は会話だけで応答します。

GitHub Actions run、PR check、GitHub Issue を読むだけの GitHub-only read
inspection は GitHub inspection として扱います。

local repo state 確認、file edit、validation、PR / issue mutation、local CI
実行、または実装作業へ切り替わった時点で repository task として扱い、
切り替えをユーザー向け update で明示してから通常の workflow gate に入り
ます。

LCPの全文規則は [`agent-orchestration.md#Local Capability Priority`](../skills/agent-orchestration.md#local-capability-priority) が所有します。このworkflowは、LCPが選択された場合に、そのownerが選んだ既存canonical recordのlocatorだけを参照します。

### ユーザー向け言語

ユーザー向けの作業更新、最終報告、レビュー要約、handoff guidance、
reader-facing docs は日本語で書きます。機械可読の key、command、path、
role id、schema は正本表記を保ちます。

repo-changing run では `team_manifest.yaml` の
`run.user_facing_language_policy` を handoff packet に含め、subagent と reviewer
が同じ方針を参照できる状態で渡します。`bootstrap_agent_run.py` と
`bootstrap_agent_run.py` の `USER_FACING_LANGUAGE=ja` を起動時 evidence として
扱います。

### 契約完全実装

実装 behavior は request clauses、acceptance contract、
`Implementation Source Packet`、`Design-To-Implementation Trace`、
dependency-expanded scope、validation route、review gate から導きます。
見た目の広さ、owner-bounded route、MVP、thin slice は暫定的な routing、
wave、validation profile の signal に留めます。owner boundary や impact surface が
違うと分かった時点で route を更新します。

repo-changing run では `team_manifest.yaml` の
`run.contract_complete_implementation_policy` を handoff packet に含めます。
`bootstrap_agent_run.py` の
`IMPLEMENTATION_COMPLETENESS_POLICY=contract_complete` を起動時 evidence として
扱います。contract gap、責務境界、API shape、依存方向、runtime contract の不足は
`design_issue_blocker` として Gate 5-6 に戻します。

### Design Integrity Gate

実装前の設計判断は、近い file、現在の finding、会話印象ではなく
owning responsibility model から始めます。Full staged route では `Abstract Design
Frame`、`Implementation Source Packet`、`Design Side-Effect Map`、
`Design-To-Implementation Trace` をそろえます。親は edit authorization を持たず、
write-capable child handoff の packet と gate を選択・relay します。
Gate 6 の detailed design review は、owner/design boundary、API shape、仕様解釈、
または別の unresolved claim が owning review gate では判定できない場合だけ選択します。
設計文書の存在だけでは別 review stage や artifact を生成しません。reviewer output は
hypothesis であり、decision-owning reviewer が current source snapshot、reachable
input/control path、contract、witness/static proof を確認して adjudicate します。

実装前の design gate は、run manifest の `run.active_design_packet` を唯一の
artifact ownership source とします。schema は `waterfall.design_packet.v1` で、
design artifact、technical design review、document-flow review の相対 path と
`document_flow_required` を必須にします。generator の precedence は、explicit
run `--active-design-packet` input、workflow-specific record、standard
`agents_config` artifact registry の順です。generator は選択 record を生成済み
run manifest に永続化し、以後その manifest が persisted authority になります。
gate は persisted manifest の `run.active_design_packet` を唯一の runtime input として
読み、manifest-declared path だけを active artifact route として消費します。
active packet の source reference には、同じ run bundle にある
`semantic_responsibility_contract.toml` を `artifact:` reference として含めます。
この instance は実装前に semantic delta、implementation action、obligation、一次検証
owner、supporting property/role、hard-edge closure を割り当てるために使います。
missing / unknown field / unknown schema / invalid field / outside-bundle path は typed blocker として
design owner に戻します。implementation handoff は、manifest-declared design artifact、
両 review の一致する `Design artifact path:`、最終 `decision=approve`、および required
な document-flow approval を要求します。

API shape、責務境界、path layout、命名、アルゴリズム、test oracle、依存方向、
runtime contract、config surface の判断が未確定なら、実装吸収ではなく
`design_issue_blocker=<issue>` と evidence を残して Gate 5-6 へ戻ります。local
fallback、wrapper、helper、branch、alternate route、test relaxation、docs
overwrite、implementation shortcut は Design Integrity Gate の外側です。

### Codex Goal Session State

Codex の goal は session runtime state として使い、repository に mirror file を作りません。

- stable な goal 機能は Codex runtime の既定を使い、shared config に feature flag を重ねません。
- user が goal-driven intent を示したが exact objective を渡していない場合は、parent が target-state-complete Objective を組み立てます。intake draft は read-only discovery として扱い、edit authorization は target-state-complete Objective と implementation handoff の固定後に開始します。
- coordination、resumption、または選択された workflow が durable lifecycle evidence を要求する場合だけ run bundle を materialize し、work unit と iteration state は `schedule.md`、実行結果と next action は `work_log.md`、acceptance は validation evidence に記録します。
- run bundle を選択しない task は semantic handoff または tool result で owner、replaceable unit、mechanism、validation route、unresolved branch を満たします。session goal の存在は write authorization、implementation readiness、closeout の追加 gate にしません。
- user が goal-driven task を指定した場合、session goal と実装計画は同じ objective と acceptance criteria を参照します。durable evidence が必要な場合は、その work breakdown を run bundle の `schedule.md` へ直接記録します。
- iteration の継続は `schedule.md` の open work、`work_log.md` の next action、未完了の validation evidence から判断します。session goal はその判断を表示できますが、repository state の正本にはしません。

### Token Observation And Adaptive Materialization

When the user asks to reduce token usage, or current session evidence shows
repeated context loading, duplicate agent decisions, oversized tool output, or
retry loops, apply `agents/workflows/token-efficient-codex-workflow.md`.

- Start from the project model and topology config. Runtime evidence owns any
  later task/profile classification or profile change.
- Materialize one accountable child for the current decision. Add a specialist
  only when a distinct input artifact, review focus, and output decision exist.
- Context may be large. Remove duplicated or decision-irrelevant copies, not
  context required by request clauses, owner boundaries, or traceability.
- Keep `worker` as the implementation default. Select `spark_worker` only from
  the typed parent packet. Explicit bounded owner/path/validation requests may
  close through the selected write-capable child route.
- Attribute change with the existing session comparison, role evaluator, and
  runtime dashboard tools. Missing post-change runtime evidence remains
  `missing`; it is not inferred from fewer configured roles.

Token-saving changes context loading while preserving correctness gates. The
active gates are those selected by runtime profile and risk class.

### Edit Execution Surface

Repo file edits use the responsibility-preserving execution surface:

1. 手編集で責務を追える編集は patch-based edit を使います。
1. 機械生成・一括変換・format は repo 内の script / formatter / generator を使います。
この選択は編集手段の選択です。対象範囲の正本は `requested_scope` に残します。
作業 log / run bundle には、`requested_scope`、選んだ `work_scope`、外した surface
の理由を必要な粒度で残します。user update では、既定から外れる編集手段を使う場合、
tool availability が作業判断に影響する場合、または user が編集手段を質問した場合に説明します。

### Library And Reuse Sweep

新しい code path、module、helper、test、script を足す前に、導入済みライブラリと既存の再利用候補を探索します。
dependency surface は task に応じて次を見ます。

- `docker/requirements.txt`
- `pyproject.toml`
- lockfile
- build file
- package manager file
- 必要なら `pipdeptree` / `deptry`

既存実装の探索対象は task に応じて次です。

- `python/`
- `tests/`
- `src/`
- `include/`
- `lib/`
- `scripts/`

既存実装がある場合は、その module を拡張または再利用します。
新規追加は、既存ライブラリや既存実装で足りない理由を reuse survey に残してから選びます。

### File Dependency Manifest

新規作成・編集する canonical design / workflow / tool / policy / template text file では、ファイル冒頭に `@dependency-start` / `@dependency-end` marker を持つ dependency manifest block を置きます。Routine notes、generated reports、closed issue records、archive / compatibility records は scanner の classification に従います。
設計正本は `documents/design/dependency-manifest-design.md` です。
旧 `Dependency Files:` block は新規・変更 file では使いません。

- manifest の内部 DSL は `<direction> <kind> <relative-path> <reason...>` です
- `direction` は `upstream` または `downstream` です
- `kind` は `design`、`implementation`、`environment` です
- path は manifest を持つ file から見た相対 path です
- 依存として書くのは、その file を理解・実行・検証するために読むべき repo 内の正本 file です。dependency list は実際の責務関係に基づけます
- upstream は「編集前に読む file」、downstream は「編集後に影響確認する file」として分けます
- 依存が無い direction は行を置きません。`none` placeholder は置きません
- Markdown は title 直後、Python / shell / TOML / YAML など comment 可能な file は shebang / encoding marker 直後、C-like file は先頭 comment block に置きます
- line comment しかない format では `# @dependency-start` のように line comment wrapping を使います
- commentless format や generated / binary / vendored external file は scan tool の分類に従い、必要なら同じ変更の design / manifest / README に理由を残します

編集 workflow:

1. 変更対象 file の manifest を先に読み、upstream edge の target を編集前 context として読む
1. manifest が無い checkable file を編集する場合は、同じ差分で `@dependency-start` block を追加する
1. downstream edge を持つ file を編集した場合は、差分後に downstream target を確認する
1. 新しい dependency edge を足す場合は、同じ変更で reverse edge も足すか、migration 中で足せない理由を review artifact に記録する
1. subagent handoff には `dependency_manifest_plan` と dependency header graph の再帰展開結果を含め、編集対象ごとの upstream / downstream edge、`dependency_edit_scope.txt` / `dependency_graph.tsv`、読む順序を handoff packet に載せる

closeout 前に、少なくとも次を実行します。

```bash
python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
```

dependency edge を追加・変更した場合は次も実行します。

```bash
bash tools/agent_tools/check_dependency_graph.sh --print-edges
```

`check_dependency_graph.sh` は upstream graph と downstream graph を別々に扱い、自己参照、reverse edge、kind mismatch、cycle を検証します。
移行期間中に repo 全体の既存 graph failure が残る場合でも、新規・変更 file は現行形式と reverse-edge を満たして closeout します。

## Task Classification

次の 6 つから 1 つ選びます。

- `Scoped Change`
- `Research-Driven Change`
- `Large Delivery`
- `Platform And Environment`
- `Comprehensive Development`
- `Adaptive Improvement Loop`

分類規則:
- code / docs / tools / runtime をまとめて rework するなら `Comprehensive Development`
- Docker / CI / dependency を触るなら `Platform And Environment`
  - `environment-maintenance` と `environment_change_proposal.md` を先に起こし、code requirement と blocked command を固定する
  - Host にrepo-local virtual environmentを作らず、AgentCanon environment validationはbootstrap container contractと実lifecycle readbackを使う。project environmentはproject-owned validatorへ委譲する
- 外部調査や比較実験が必要なら `Research-Driven Change`
- tuning、比較改善、探索的 protocol refinement を backlog 付きで回すなら `Adaptive Improvement Loop`
  - Agile outer loop とし、1 extension ごとに 1 waterfall run-id / 1 waterfall pass / 1 decision state へ分解する
- chunk ごとの delivery なら `Large Delivery`
- それ以外は `Scoped Change`

## Completion Bar

user-facing completion は、全 active clause、selected work unit、selected owning
review gate (when activated)、validation、closeout gate が揃った状態です。
closeout 前に reviewer と auditor は次を明示的に確認します。

- 各 must-do clause と completion-evidence clause が、実装、文書、test、command、artifact、または明示された deferred / rejected clause に対応している
- request に含まれる仕様と実際の product surface の間に未実装の gap が残っていない
- LCPが選択された場合は、[`agent-orchestration.md#Local Capability Priority`](../skills/agent-orchestration.md#local-capability-priority) の既存canonical record locatorを完了証拠として引用する
- validation は `necessary_presence`、`forbidden_presence`、`sufficient_behavior` を区別する。必要なpath・linkの存在や禁止された旧経路の不在をbehavior成立の十分条件へ昇格させず、behaviorの十分条件が要求されない作業に実行テスト・完全一致比較・網羅レビューを追加しない
- schedule、review、validation、commit / push、shared canon sync、follow-up 判断を含む今回 scope の task が 1 つも未完了で残っていない
- task が数式、擬似コード、仕様、method contract を持つ場合、runtime success ではなく
  静的解析・読み取りによる implementation alignment evidence が review artifact に
  主証跡として残っている
- accepted review findings が実装へ反映され、behavior、owner/design boundary、correctness、validation、または publication state を変えた same-owner repair だけが selected gate の rerun を要求している
- review reject、requested-change、または `required_change` への応答が、user
  request や design intent を捨てる rollback になっていない。実装 slice の
  revert / discard がある場合は、撤回、置換、owner 外、unsafe replacement、
  または escalation の authority と、保持された request clause が artifact に残っている
- deferred findings は今回の completion readiness への影響、理由、escalation を artifact に記録している

`closeout_gate.md` の CompletionCoverage consumer、typed owner boundary、
canonical formatter/dispatcher、validation-response、review integration が
揃った時点で、`user_completion_report=unlocked` にできます。

## Mechanical Completion Loop

実装後から user-facing completion までの間は、parent の自己判断だけで閉じず、次の機械的 loop を `closeout_gate.md` に evidence として残します。

1. `user_request_contract.md` の active clause、`schedule.md` の planned work unit、直近 review findings、validation blockers、commit / push、shared canon sync、follow-up 判断を一覧化します。
1. 最新 diff と tracked / untracked state を確認し、変更対象 file の dependency manifest、downstream edge、旧参照、copy / snapshot / backup path を見ます。
1. 静的解析、読み取り確認、docs / targeted tests / agent checks を先に実行します。
   repo-wide dependency review や broad execution は、最終候補の touched contract
   が要求して次の判断または最終 validation を変える場合だけ一度選択します。
   completion predicate は選択した canonical route で確定します。
1. 選択された owning review gate が diff-check を要求する場合だけ、read-only diff-check reviewer を起動し、選択された handoff、latest diff、validation evidence、dependency evidence を渡します。
1. 選択された review の output は hypothesis として decision-owning reviewer または ship reviewer が adjudicate します。current snapshot、reachable path、contract、witness/static proof があり、behavior、owner boundary、correctness、validation、または publication state を変える accepted finding だけ same-owner repair loop を開きます。rejected hypothesis は `reason_code` と `evidence_ref` を残し、wave / rollback を起こしません。
   この修正 loop では、review finding への応答を、同じ意図を保つ修正、
   再設計、または authority 付き escalation / replacement として扱います。
   Follow `agents/skills/agent-orchestration.md#Review Activation And Adjudication`
   after final validation topology selection; this workflow surface does not
   duplicate that semantic rule.
1. diff-check agent が `approve` し、未完了 work unit、未解決 finding、未実行 validation、未同期 canon、未 commit / push、未判断 follow-up が無い場合だけ loop を止めます。

`closeout_gate.md` の `review_convergence_complete=yes` と `diff_check_agent_complete=yes` が揃った時点で、`user_completion_report=unlocked` にできます。

## Contract-Required Skill Set

Codex では、まず `$agent-orchestration` を起点にし、`agents/skills/README.md` から current stage と contract に必要な skill を選びます。
user が skill を明示したい場合は `$skill-name` を使います。例: `$repo-onboarding`、`$research-workflow`、`$paper-writing`
細粒度の review pass、CLI adapter、artifact placement、validation helper は public skill ではなく、`documents/conventions/REVIEW_PROCESS.md` と `agents/canonical/` に寄せます。
repo-changing task では `python3 tools/agent_tools/route.py --prompt "<request>" --format json` の `ACTIVE_SKILLS` を routing declaration に使い、`$codex-task-workflow` は execution stage、`$subagent-bootstrap` は implementation / patch / doc-edit handoff が current stage に入った時点で active にします。
`bootstrap_agent_run.py` は `--task` 文面から prompt-derived
skill を追加し、選択済み skill ごとの repo tool route を
`run.repo_tool_routing_policy` に出します。repo tool route は skill ごとに
`show_skill_packet`、`required_commands`、
`task_matching_conditional_commands`、`validation_commands` の順で扱います。
後続 wave で関連 skill が active になった場合は、同じ
`skill_tool_commands.py show --skill <skill> --format text` を再生成してから
handoff に入ります。

Before a capability gap claim about an existing API, dependency, config,
or extension point, the implementation plan includes the
`documents/design/api-surface-traversal-policy.md` evidence trail. Helper wrappers,
native reusable API patches, and vendor/library edit proposals follow
after the public import/export/signature/nested-config/example path has been
checked and cited.

- workflow / runtime routing:
  - `agent-orchestration`
- repo 入口確認:
  - `repo-onboarding`
- subagent 起動:
  - `subagent-bootstrap`
- code review:
  - `change-review`
- Python diff:
  - `python-review`
- C / C++ diff:
  - `cpp-review`
- test design:
  - `test-design`
- owning implementation mechanism の確立または修復後に、semantic responsibility contract の owner と targeted validation で閉じない test-owned runtime risk が残る場合だけ `test-design` / `test_designer` を起動し、Activation Decision と boundary classification を先に返す。起動後は未解決oracleを必要十分に覆うケースだけを設計し、checker-owned property、重複契約、no-crash、内部形状固定をtestへ追加しない
- paper writing:
  - `paper-writing`
- general explanatory docs:
  - `long-form-writing` as the DSL-to-prose adapter when file/document responsibility is README, workflow, guide, migration, specification, or similar explanatory prose
- academic docs:
  - `academic-writing`
- Markdown diff:
  - `md-style-check`
- legacy worktree cleanup / drift diagnosis:
  - `worktree-start`
- worktree drift and cleanup:
  - `worktree-health`
- experiment inner loop:
  - `experiment-lifecycle`
- experiment review:
  - `experiment-review`
- tuning / research / experiment の backlog-driven outer loop:
  - `adaptive-improvement-loop`
- literature and prior art:
  - `literature-survey`
- research outer loop:
  - `research-workflow`
- 包括的 repo-wide delivery:
  - `comprehensive-development`
- environment and tool rollout:
  - `environment-maintenance`
- memory record の検索・更新・owner 昇格と agent-side 対話学習:
  `agent-learning` と Rust `agent-canon memory` を使う。stable preference は対象
  `AGENTS.md` または canonical owner への明示変更として扱う。

## Execution Flow

### 1. Intake

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
  `python3 tools/agent_tools/memory_record.py search --root . --search-path <owner> --failure-evidence <evidence>`
  を先に実行し、既存 topic は同じ record を update します。独立 topic の create は
  `plan` の readback 後に行います。raw chat は memory に追記しません。

### 2. Workflow Selection

- `agents/TASK_WORKFLOWS.md` から family を 1 つ選ぶ
- family をまたぐ場合も、主 family を 1 つ決める

### 3. Placement

- run 固有のメモは `reports/agents/<run-id>/`
- repo-wide の恒久文書は `agents/` か `documents/`
- 知見の蓄積は `documents/notes/`
- packet 出力は tree 順ではなく、`CROSS_CUTTING_DOCUMENT_PACKET`、`DESIGN_DOCUMENT_PACKET`、`IMPLEMENTATION_DOCUMENT_PACKET`、`WORKFLOW_SUBAGENT_PROMPT_PACKET` の順で handoff に使う

### 4. Run Bootstrap

repo-changing task では semantic handoff を既定にし、coordination、resumption、または
selected workflow が durable lifecycle evidence を要求する場合だけ bundle と
explicit subagent activation を materialize します。
stage の具体的な責務と実行条件は prose ではなく `.codex/agents/*.toml` を正本にします。
この文書は executable stage flow の正本です。workflow family 選定は
`agent-orchestration`、prompt / config drift 監査は `prompt_config_reviewer`
を先に通し、ここは executable stage flow に保ちます。
goal-driven task でも provisional bundle は coordination/resumption または owner-critical
evidence が次の判断を変える場合だけ作り、candidate role の handoff plan を先に
materialize しません。active runtime が明示許可を要求する場合は、許可があるときだけ
実際に起動します。

- repo を編集する
- specialist handoff を明示したい
- review artifact を残したい
- 長めの task で run 単位の記録が必要
- subagent と parent の責務を分けたい

full staged route でも、`scheduler`、`schedule_reviewer`、`designer`、`design_reviewer`、
active gate の場合の `document_flow_reviewer` は候補です。owner-critical decision または
distinct unresolved claim/risk が選択した stage だけを materialize し、W2 の completion
gate は approved typed contract evidence と active owner route で確定します。
bounded owner route は `external public API/behavior/schema unchanged` の場合だけ維持します。public surface の追加、縮小、削除、rename、restriction、deprecation、意味変更がある場合は `scoped_change` または broader route へ進み、`dependency/consumer/migration/docs closure` を scope 形成します。reader-facing docs、新用語、cross-surface risk がある場合も従来どおり broader route へ進みますが、その理由だけで同 closure を無条件要求しません。
Codex subagent では、候補 role を workflow family に応じて宣言しますが、owner-critical
decision、distinct unresolved claim/risk、または selected validation route が要求した
role だけを materialize します。W2 の completion predicate は approved typed contract
evidence と active owner route に結び付けます。
Agent Wave に固定 plan-review-edit 順序はありません。bootstrap は selected stages だけを
`team_manifest.yaml`、`schedule.md`、`workflow_monitoring.md` に記録します。
bootstrap は `run.pre_handoff_scope_policy` も出します。implementation
surface route は source packet seed であり、responsibility search、reuse
survey、stale-surface scan、dependency expansion を通してから
`allowed_paths`、`do_not_read`、`write_scope`、`validation_route`、
`review_gate` の handoff scope にします。
`bootstrap_agent_run.py` は
`run.default_quality_check_policy` も出します。この policy は active な
`change_reviewer`、`docs_workflow_steward`、
`python_reviewer`、`cpp_reviewer` と、それらから展開される Codex
`agent_type`、task-default / changed-path / manual enable / review-pack
provenance、軽量 static check command を記録します。review と edit の
handoff はこの policy を含めます。
学術文章では、これに `notation_definition_reviewer` と `logic_gap_reviewer` を追加します。
論文や thesis chapter では、さらに `citation_evidence_reviewer` を追加します。
interactive Codex で要件整理と実行計画立案を行う場合は、parent session 側の plan-mode command を使ってから planning specialist を起動します。official Codex CLI では `/plan` です。
default の model / reasoning authority は `agents/model_profiles.toml` の closed registry です。`.codex/agents/*.toml` は generated runtime readback view です。code survey、tool drift survey、機械 report 要約、execution-only experiment / log work は Luna/high profile、通常の planning / authoring / review child は `gpt-5.6-luna/high`、`worker` と `ship_reviewer` は `gpt-5.6-luna/xhigh`、final judgment は `ship_reviewer` または decision-owning reviewer、`spark_worker` は fixed-packet `gpt-5.3-codex-spark/low`、fresh read-only T14 `skill_evaluation` は evaluator-only `gpt-5.4-mini/medium` profile を使います。
- subagent の depth は `.codex/config.toml` と active spawn budget で管理します。必要な追加層がある場合は delegated stage owner が owner、入力 packet、write scope、review gate を明示して展開します。
- active frontier、write scope、nested reservation、queue は capacity handshake owner が宣言 topology から生成し、その typed contract を workflow capacity policy の唯一の authority とします。fixed packet の標準経路は one Spark と one post-completion owning gate で、Luna は ambiguous design、causal repair、graph-owned cross-owner integration、review を保持します。
- workflow family ごとの subagent prompt 正本は `agents/task_catalog.yaml` の `workflow_families[].subagent_prompt` です。
- budget を超える場合は例外扱いにし、`schedule.md` と `work_log.md` に理由、追加 role、expected output、write scope を残します。
- write-capable frontier は `team_manifest.yaml` の dependency order、wave plan、disjoint write scope、integration order、review gate と capacity readback から生成します。衝突する target は順序制約として扱い、同じ file / canonical surface / shared root contract に触る作業は先行 wave の validation と tool rerun 後に後続 waveへ回します。分離済み writer は available write capacity 内の同一 wave、追加判断が要る writer は current checkout 内の後続 wave へ直列化します。

Codex runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます。

標準コマンド:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "short task summary" \
      --task-id T1 \
      --owner "codex" \
      --workspace-root "$PWD"

bundle 出力には少なくとも次が含まれます。

- `CROSS_CUTTING_DOCUMENT_PACKET`
- `DESIGN_DOCUMENT_PACKET`
- `IMPLEMENTATION_DOCUMENT_PACKET`
- `WORKFLOW_SUBAGENT_PROMPT_PACKET`
- `IMPLEMENTATION_SURFACE_ROUTE_STATUS` と route command
- `TOOL_REUSE_LEDGER_STATUS`
- `PRE_EDIT_REJECTION_PREDICTION_STATUS`
- task id / fan-out budget / active role evidence

parent は subagent handoff でこの packet path 群と `team_manifest.yaml` の `run.subagent_prompt_packet` / role 別 `prompt_contract` を local/tool context 参照として持ち、prompt には `agents/COMMUNICATION_PROTOCOL.md` の `Fresh Subagent Context Capsule` で選択した fields だけを入れて requested scope を保持した bounded packet routing を維持します。
handoff には `allowed_paths`、`do_not_read`、context artifact path、expected output schema、
`PRIMARY_PATHS` / `FORBIDDEN_PATHS`、reuse ledger、pre-edit rejection prediction を含めます。
`cross_cutting_document_packet` は利用可能な reference list であり、role ごとの work packet を選ぶために使います。広い request では、packet に含めなかった reference を `omitted_surfaces` として理由付きで残します。

研究・実験つき変更:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "research-backed change" \
      --task-id T4 \
      --owner "codex" \
      --workspace-root "$PWD"

環境変更:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "platform or environment change" \
      --task-id T8 \
      --owner "codex" \
      --workspace-root "$PWD"

学術文章:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "academic writing task" \
      --task-id T10 \
      --owner "codex" \
      --workspace-root "$PWD"

包括的開発:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "comprehensive development pass" \
      --task-id T12 \
      --owner "codex" \
      --workspace-root "$PWD"

反復改善:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "adaptive improvement loop" \
      --task-id T13 \
      --owner "codex" \
      --workspace-root "$PWD"

Adaptive Improvement Loop では、outer run の `experiment_change_loop.md` に `Extension Backlog` を持ち、各 extension で別の waterfall run-id を作ります。
次の extension へ進む前に、直前 extension で選択された `waterfall-gate-check`、review、`task-close`、commit / push を完了させます。未選択の review artifact や full rerun は作りません。

`--task-id` を指定しても、`agents/task_catalog.yaml` の task-default specialist と `default_for_tasks` review pack は候補です。owner-critical decision または distinct unresolved claim/risk が有効化したものだけ materialize し、空の reviewer/template artifact は生成しません。
language-specific reviewer は `bootstrap_agent_run.py` が `--changed-path` か workspace の `git status --short` から自動で足します。
run bundle を起こしたら、`user_request_contract.md` を planning 前に埋めます。stage artifact、handoff、review では clause ID を明示します。
各 waterfall gate を次段へ進める前に `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate <gate>"` で中間 gate を確認します。

包括的開発の固定 Codex stack:

- `requirements_organizer`
- `manager_reviewer`
- `literature_researcher`
- `execution_planner`
- `plan_reviewer`
- `detailed_designer`
- `detailed_design_reviewer`
- `document_flow_reviewer`
- `project_reviewer`
- `docs_workflow_steward`
- `prompt_config_reviewer`
- `python_reviewer`
- `cpp_reviewer`
- `worker`

cost を無視して review coverage を優先する run では、research-driven change と comprehensive development は `--full-team` を許可します。

### 5. Implementation

- 実装は `agents/workflows/implementation-waterfall-workflow.md` の gate に従って進める
- selected gate の次段移行では `waterfall_gate_check.py` を通し、`WATERFALL_GATE_READY=yes`
  でない場合は指示された owner stage へ戻る
- 実装前に `design_brief.md` の `Abstract Design Frame`、`Installed Libraries And Existing Implementation Survey`、`Implementation Source Packet`、`Design Side-Effect Map`、`Design-To-Implementation Trace` を読み、抽象責務と概念 model から実装 slice と downstream side effect が導かれていることを確認してから、そこにある artifact、repo docs、dependency surface、code path を読了する。test plan は、active workflow または touched surface が post-implementation test design を選択し、その activation により `test_plan.md` が生成されたか必須になった場合のみ読了する
- selected design review がある場合だけ、実装前に `design_review.md` を読み、
  `Design Artifact Under Review` が現在の `design_brief.md` を指し decision が
  `approve` であることを確認する。設計を修正した後は selected Gate 6 で現行設計を
  adjudicate し直す
- selected design review がある run では、write-capable handoff route の前に
  `pre_handoff_gate_status` へ `design_review.md decision=approve`
  と `waterfall-gate-check --gate design` pass evidence を記録する。candidate artifact
  は記録や handoff を自動的に要求しない
- 詳細設計前に `bootstrap_agent_run.py` の `DESIGN_DOCUMENT_PACKET` を読み、その path 群を `design_brief.md` の `Upstream Requirement Packet` に転記する
- 詳細設計では `design_brief.md` の `Canonical Tree-Head Plan` に、この task の後に tracked tree に残してよい設計文書 path と実装 path を固定し、parallel design doc、implementation copy、snapshot、backup path を残さないことを明記する
- worker の実装入力は、各 implementation slice の前に明示された design artifact path、design section、request clause ID です。test plan item は、active workflow または touched surface が post-implementation test design を選択し、その activation により `test_plan.md` が生成されたか必須になった場合のみ実装入力に含めます
- worker は docs、workflow、prompt/config、validation output、dependency manifest、user-facing surface へ波及する変更を `Design Side-Effect Map` の item として扱い、implementation summary に owner stage と review gate を残す
- `Abstract Design Frame`、`Installed Libraries And Existing Implementation Survey`、`Implementation Source Packet`、選択された場合の承認済み `design_review.md`、design gate check、および design と現行 repo docs / code / dependency surface の整合が揃った時点で実装へ進む。design review が未選択なら semantic decision sufficiency と owner validation evidence を使い、欠けた場合だけ Gate 5-6 へ戻る
- 実装中に design issue が見つかった場合は、`design_issue_blocker=<issue>`、evidence、候補 option を artifact または structured handoff に残し、Gate 5-6 へ戻す。API shape、責務境界、path layout、命名、アルゴリズム、証明対象、test oracle、依存方向、runtime contract、config surface の欠落や矛盾は設計側で解決します。run bundle が無い bounded task も write-capable child packet を作って継続する
- `design_issue_blocker` は local fallback、wrapper、helper、分岐、別経路、test 緩和、docs 上書きではなく、Gate 5-6 の設計更新で閉じる。承認済み design と局所 precedent から一意に導ける typo、format、import、狭い機械的追従だけが同じ implementation pass で修正できる
- legacy-route drift と duplicate implementation は implementation GuardRail finding として扱い、旧 route、旧 wrapper、旧 helper、config mirror は caller migration で canonical owner へ統合する
- implementation は current tree head の canonical path だけを更新対象にし、`*_old`、`*_copy`、dated clone、parallel module、duplicate directory のような別 truth surface を作らない
- `bootstrap_agent_run.py` の `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker` を確認し、repo-changing implementation / patch / doc-edit work は、bounded でも write-capable handoff で進める。`worker` が既定で、`spark_worker` は Abstract Design Frame、design trace、naming、test-plan artifact / evidence（active workflow または touched surface が post-implementation test design を選択し、その activation により `test_plan.md` が生成されたか必須になった場合のみ）、dependency-expanded handoff scope に加え、`--select-agent-type implementer=spark_worker:<evidence>` が stdout / manifest に記録された場合だけ使います。選択済み candidate が blocked の場合は typed blocker を記録し、親は実行しません。
- 新規または rename する file、function、class、theorem、artifact、CLI flag、
  config key は、implementation handoff 前に naming plan で固定する。naming plan は
  対象概念、責務語彙、既存 naming family、採用名、avoid-name list を含み、
  `documents/rule/naming.md` と言語別規約を参照します。
  名前が未確定な場合は Gate 5-6 へ戻り、worker handoff 前に naming plan を確定します
- 明示 spawn 許可がある場合、実装前の repo inventory と tool drift survey は Luna/high の通常 role TOML へ、static validation failure triage と diff-local language review も該当 decision がある場合だけ `gpt-5.6-luna/high` review role TOML へ渡します。`gpt-5.4-mini/medium` は明示 T14 `skill_evaluation` の fresh read-only artifact-only `skill_evaluator` に限り、permanent team role にはありません。`worker` は `gpt-5.6-luna/xhigh` の既定 implementer で、typed parent-packet selection がある機械的 slice だけ `spark_worker` へ渡します。`.codex/config.toml` の `gpt-5.6-sol/high` parent は統合判断と次 gate 判定に集中します
- `spark_worker` を選択できる実装は、Abstract Design Frame から導かれた差し替え可能な単位で、public interface 変更なし、依存追加なし、仕様解釈なし、既存 test / docs の局所更新で閉じる slice だけにする。design trace と dependency-expanded handoff scope は必要 evidence であり、実際の選択には `--select-agent-type implementer=spark_worker:<evidence>` が必要です。
- 実装 subagent を起動するときは `IMPLEMENTATION_DOCUMENT_PACKET` の path 群を明示入力し、chat 要約ではなく packet path を読ませる
- すべての stage subagent を起動するときは `team_manifest.yaml` の `run.subagent_prompt_packet` と該当 role の `prompt_contract` を local/tool context 参照として扱い、prompt には選択済み `Fresh Subagent Context Capsule` fields を入れる
- `spark_worker` は design trace と dependency-expanded handoff scope が揃い、typed parent-packet selection が記録された bounded implementation slice にだけ使い、設計判断、scope 判断、review 判断は frontier owner / reviewer に残す
- chunk、slice、checkpoint、subpass の後は remaining planned work units と next gate を確認してから続行する
- repo-changing task では selected durable coordination/resumption route がある場合だけ current checkout の run bundle `work_log.md` を継続更新し、それ以外は structured handoff/tool-result evidence を使う
- 新規作業は current checkout で kickoff します。`WORKTREE_SCOPE.md` と `worktree_scope_lint.py` は legacy cleanup / drift diagnosis 専用です
- stale な `WORKTREE_SCOPE.md`、別 branch、別 path の action log を見つけた場合は、current checkout の `work_log.md` に観測事実と扱いを残す
- selected review の instance reuse / separation と implementation 着手条件は、semantic owner route と `.codex/agents/*.toml` の runtime projection に従う。同一責務・同一 context の review は再利用し、distinct unresolved claim/risk の場合だけ分ける
- 包括的開発では `project_reviewer` を intake と closeout に追加し、repo-wide な integration risk を確認する
- 文書主体の成果物では `document_flow_reviewer` を通し、上から順に読んだときの意味の通り方を確認する
- README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書で reader-facing 構成を変える場合は `long-form-writing` を DSL-to-prose adapter として読み、docs-impact がある distinct unresolved reader-path claim を owning gate が判定できない場合だけ `docs-completeness-review` を追加する
- 論文、thesis chapter、scholarly note のような学術文章では `academic-writing` を読み、notation / logic reviewer は distinct unresolved claim が owning gate の範囲を超える場合だけ選択する
- 投稿論文や thesis chapter の draft では `paper-writing` を読み、citation evidence reviewer は distinct unresolved citation claim が残る場合だけ追加する
- contract-only wrapper や checker-owned validation だけの変更では、static contract validation と canonical command evidence を validation route に置く。
  Approved typed contract evidence remains the completion criterion.
- validation tool の autofix は changed contract、changed lines、または task plan が名指しした checker-owned property に結び付く finding に適用し、広い validation で出た既存 style debt は residual evidence と repair route に分ける
- 研究・実験系の変更では active experiment profile の risk に応じて `report_reviewer` と research perspective reviewers を選ぶ
- JAX export / native runtime の task では、対象 implementation slice で `generic callable path`、`specialized coeff path`、`export-based generic path` のどれを触るか宣言する。generic path は `jax.export` artifact producer と consumer/runtime smoke を完了条件に含める
- cross-process export worker には serializable manifest と reconstruction recipe を渡す
- `LoadedProgram` のような runtime materialization は runtime vertex / lifetime scope として扱う
- まず導入済みライブラリ、既存 code path、既存 helper、既存 style を調べ、再利用と拡張を優先する
- 新規 helper や新規 module を足すときは、既存実装で足りる範囲と、導入済みライブラリの設定変更や薄い wrapper で足りる範囲を design packet に結び付ける
- worker は approved design または明白な局所 precedent に由来する variable、function、class、file、CLI flag、config key、public API identifier を使う
- implementation slice は contract-complete implementation として閉じる。request clause、acceptance contract、Implementation Source Packet、validation route を結び、implementation shortcut を見つけたら `design_issue_blocker` と evidence で design review へ戻す
- checkpoint review は diff だけでなく Abstract Design Frame、approved design packet、Design Side-Effect Map、source packet citation の一致を確認する
- role ごとの model / reasoning 設定は `.codex/agents/*.toml` に従う
- implementation の既定 candidate は `gpt-5.6-luna/xhigh` の `worker` とし、review / quality-check は active decision ごとに一つの `gpt-5.6-luna/high` role を選びます。Abstract Design Frame と design trace から導かれた機械的 slice は explicit parent-packet selection がある場合だけ `spark_worker` を使い、execution-only experiment / log work は Luna/high の `experiment_runner` に渡します。mini/medium は明示 T14 `skill_evaluation` の `skill_evaluator` だけです。
- parent-managed write-scope rule は `worker.toml`、`spark_worker.toml`、planning / reviewer TOML、`team_manifest.yaml` を正本にする
- 正本は `agents/` と `documents/` から先に直す
- runtime entrypoint は薄く保つ
- skill は repo 正本を置き換えず、導線だけを担う

### CompletionCoverage Applicability And State Contract

`CODEX_WORKFLOW.md` owns applicability and state transitions for the checked
CompletionCoverage read model. Existing ledger owners append facts; the W2
projection/check boundary derives the read model; `task_close` and
`report_artifact_checks` consume it. No reader may write back to the schema
owner or become a second state machine.

The minimal state is `context_binding`, `coverage_map`, `gate_evidence`,
`failure_response`, `completion_boundary`, and `projection_metadata`. State
transitions are `context_bound` → `design_pending` → `design_approved` →
`writer_release_pending` → `writer_released` → `source_freeze_pending` →
`source_frozen` → `change_review_pending` → `change_review_approved` →
`integration_pending` → `publication_ready` → `delivered`. A validation
failure enters `repair_pending`; same-intent repair returns to the owning gate,
and unresolved or intent-changing work enters `escalation_pending`.

`evaluate_completion_boundary` accepts one
`control_topology_ledger.json` snapshot for all routing/publication facts. Its
other inputs are schedule, open-work, repair, and crossing-edge state only;
parent-route and global-publication state remain outside a second direct
argument. It derives the independent predicates
`all_planned_chunks_complete` and `overall_delivery_complete`. Each chunk, slice,
checkpoint, or subpass remains an internal progress observation.

W2-20 is ordered as W2 design `APPROVE`, exactly one isolated-branch writer
release with collision preservation and
`branch_creation_reason=convergence_w2_gate_completion_authority`, source
freeze/review, then W3/integration-executor integration. `routing_gate=verified` is observed at
later integration/publication, while writer release authority remains the W2
design `APPROVE` plus isolated branch release.

W1 remains the producer of `ExecutionResourcePlan`. W2 consumes one broad
W2-12 plan/actual/readback/failure certificate mapping and one W2-19 ordered
GPU consumer mapping: candidate UUID set `A`, process-held `O_t` PID/start
identities, active reservations `R_t`, selected UUIDs, atomic lock/lease plus
post-lock readback, effective environment, terminal GPU identities, release
versus retained-for-descendant disposition, and typed insufficient-eligible or
mismatch failure. W2 does not parse NVML, select, reserve, construct the
environment, produce resources, or duplicate tests/gates.

### 6. Validation

- Validation uses one canonical formatter/check path for Markdown, math, and
  Mermaid plus selected non-Python static evidence. Duplicate CI, format,
  check, and synthetic retest paths are not additional completion predicates.
- After any validation failure, record `failing_contract`,
  `observation_level`, `cause_classification`, `intent_preservation`, and
  `evidence`. The canonical token-safe slug lists are owned by
  `documents/runtime/runtime-profiles-and-check-matrix.json` and projected into
  `documents/runtime/runtime-profiles-and-check-matrix.md`; this workflow only points
  to that taxonomy. Completion advances after response resolution through the
  owning repair route or recorded escalation.
- Shared canon、Large delivery、高 risk 変更では差分限定ではなく全 repo 対象で `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` を通し、dependency graph、header 欠落、header format を確認する。Routine docs / Focused code は changed-file dependency checks と relevant downstream review を evidence にできる
- Source freeze 後は canonical formatter/check path と選択した非 Python static
  evidence を一度記録する。別 CI、別 formatter、別 checker、checker-retest
  は W2 completion gate にならない。
- Hook、tool、skill、workflow、agent protocol、GitHub workflow、dependency manifest に触る前には `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` を走らせ、`TOOL_REJECTION_PREDICTED_GATE` を write-capable subagent handoff に渡す。予測 gate が出た場合は、gate-specific command と repair plan を実装前に固定する
- tool / checker / hook / reviewer / subagent feedback から実装へ進む場合は `$tool-finding-report` で finding packet を作り、raw artifact、structured artifact、impact、prompt feedback decision を handoff に渡す。`handoff_prompt_gap` または `shared_skill_or_workflow_gap` は次の write-capable subagent 起動前に prompt を修正し、`workflow_monitor.py --runtime-feedback ... action=prompt_repair` で記録する
- agent runtime / skill 変更では active profile に応じて `make agent-checks` または relevant subchecks を使う
- 文書変更では canonical formatter/check path が Markdown、math、Mermaid の
  format/check を一つの証跡として記録する。
- report を閉じる前には `documents/experiments/experiment-report-style.md` を確認する
- 研究系 task では `critical-review` と `report-review` の decision state を確認し、必要なら `research-perspective-review` を追加する

### 7. Closeout

#### Completion Readiness

- repo に残す差分がある task では、validation 後に commit を作る
- commit は `documents/operations/BRANCH_SCOPE.md` の Git 上の runnable unit として作る。validation が参照した source、config、schema、fixture、文書、tool entrypoint を tracked tree に含める。code 変更では file-level code dependency と関数 / public entrypoint 単位の call-site evidence も残す。commit SHA、source clone SHA、validation command、対象 path、残った dirty / untracked path の分類を evidence に残す
- commit / PR の切り方は `documents/operations/BRANCH_SCOPE.md` の範囲分割契約に従う。commit は実行単位、PR はレビュー単位として扱い、複数の問題、canonical owner、behavior or contract delta、validation route にまたがる差分は範囲表を作ってから merge 前に別 PR または別 commit へ分ける
- final report の前に branch push を行い、user が明示的に停止を指定した場合は停止理由を final report に残す
- user-facing final report は、`verification.txt` が `status=pass`、`closeout_gate.md` が `auditor_status=resolved` かつ `user_completion_report=unlocked`、`user_request_contract.md` が `all_clauses_resolved=yes` かつ `forbidden_drift_detected=no` の状態で出す
- `closeout_gate.md` の `all_planned_chunks_complete=yes` と `overall_delivery_complete=yes` が揃ったら、chunk completion を全体 completion evidence に統合する
- `closeout_gate.md` の `unfinished_tasks_absent=yes` で、予定作業、review 対応、validation、commit / push、shared canon sync、follow-up 判断の完了状態を示す
- `closeout_gate.md` の `dependency_headers_complete=yes` で、作成・編集した text file の依存 file header coverage を示す
- Full owner validation の static evidence とともに、`closeout_gate.md` の `repo_wide_static_analysis_complete=profile_selected` と canonical command evidence を記録します。
- Shared canon、Large delivery、高 risk 変更で、最終候補の touched contract が要求した場合だけ、`closeout_gate.md` の `repo_wide_dependency_tools_complete=yes` とともに一度だけ全 repo 対象の `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` と header 修正 evidence を残す。Routine docs / Focused code は targeted dependency evidence を残す
- `closeout_gate.md` の `canonical_format_check_status=pass` と選択した非 Python
  static evidence で、canonical validation を示す。別 CI は W2 gate ではない。
- `closeout_gate.md` の `completion_coverage_consumer=yes`、
  `mapping_error_sets_empty=yes`、`typed_owner_boundary_status=pass`、
  `review_findings_integrated=yes` で、仕様 coverage と review disposition を示す
- `closeout_gate.md` の `review_findings_integrated=yes` は、review reject /
  requested-change への応答として、user request と design intent が保持された
  evidence を要求します。revert / discard が含まれる場合は、撤回、置換、owner
  外、unsafe replacement、または escalation の authority を示します
- `closeout_gate.md` の `review_convergence_complete=yes` で、planned work、review findings、validation、dependency review、static analysis、reading evidence、commit / push、shared canon sync、follow-up 判断を構造化 loop evidence として残す
- `closeout_gate.md` の `subagents_closed=yes` で、run-local subagent の close と fresh lifecycle evidence を示す
- `closeout_gate.md` の `diff_check_agent_complete=yes` で、run-local diff-check artifact、read-only independent agent、latest diff ref、`approve` decision、findings disposition を示す
- `closeout_gate.md` の `canonical_tree_head_complete=yes` で、設計文書、implementation surface、snapshot tree、backup path の正本状態を示す
- `workflow_monitoring.md` の signals / behavior events / interventions / improvement decisions を埋め、skill / config / workflow / memory の改善判断を `applied`、`recorded`、`not_applicable` のいずれかにする
- hook、code checker、static analysis、CI、review tool の結果が parent protocol または subagent protocol を変えるべきかは protocol reviewer が確認し、`workflow_monitoring.md` に `hook_tool_feedback=reviewed`、`parent_protocol_update=<applied|recorded|not_required>`、`subagent_protocol_update=<applied|recorded|not_required>`、`protocol_feedback_reason=...` を残す
- evidence を確認済みの closeout では、`python3 tools/agent_tools/workflow_monitor.py --report-dir reports/agents/<run-id> --closeout-token-preset` で `evaluate_agent_run.py` が消費する standard behavior tokens を記録できます。この preset は記録 shortcut であり、canonical formatter/check、dependency review、diff-check approval、review finding resolution は個別 evidence として残します。
- evaluation reviewer が `tools/agent_tools/evaluate_agent_run.py --report-dir reports/agents/<run-id> --behavior-manifest evidence/agent-evals/agent_behavior_eval.toml --write` を pass し、`closeout_gate.md` の `agent_evaluation_complete=yes` と `agent_evaluation.md` の `feedback_actions_resolved: yes` が揃ったら、agent behavior evaluation と feedback resolution を complete にする
- `schedule.md` を TODO 正本として埋め、`work_log.md` に execution trail を残す
- `documents/notes/guardrails/engineering_avoidances.md` の log-derived avoid に当たる変更は、修正または reviewer escalation の対象にする
- user request が generic path の usable smoke を求める場合、generic path の producer / consumer evidence を completion evidence にする
- JAX export / native runtime の generic path は、`jax.export` artifact producer と consumer/runtime evidence を completion evidence にする
- 実験・性能改善では、planned comparison run、acceptance criteria、raw result、interpretation evidence を分けて示す
- trainer replacement、scalability、superiority、広い theorem は baseline comparison と scope-limited evidence で主張する
- failure-onset dimension を記録し、implementation bug と frontier limit を分けて扱う
- 実験・性能改善では、correctness evidence と performance evidence を別項目で示す
- final report には branch、commit、push の成否を短く残す
- push が失敗した、または意図的に skip した場合は、その理由を final report に明記する
- push が自然な完了条件に含まれる場合は、push の許可を取りに戻らず実行する
- closeout 前に今回の観測を既存 record の update、独立 record の create、canonical owner への
  明示変更、issue/failure/evidence のいずれかに分類する。memory は `agent-learning` owner
  から on-demand に検索し、stable preference は対象 `AGENTS.md` へ直接変更する。
- closeout 前に `agent_evaluation.md` の feedback actions を見直し、stable な失敗防止は `agent-learning` で記録し、確定した guardrail 候補は positive operational condition として昇格可否を判断する
- review-only task や no-change task では、review result と no-change rationale を completion evidence にする

そのうえで、何を変えたか、何を確認したか、何を確認していないかを短く残して完了する

## Codex-Specific Rules

- `AGENTS.md` は Codex のruntime 入口として保つ
- `.agents/skills/` を正規 skill path とする
- repo-changing task では、selected stage の subagent / specialist だけを明示し、候補 stage や未選択 reviewer を work にしない
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` は active な
  distinct unresolved claim/risk がそれぞれ必要とした場合だけ選択し、選択した別 gate
  の場合にだけ別 instance にする
- 学術文章の notation / logic reviewer と論文 draft の citation evidence reviewer は候補であり、同じ owner、context、validation route で判定できる場合は active review instance を再利用し、distinct unresolved claim の場合だけ別 instance にする
- 包括的開発では、parent が dependency order、wave plan、dependency-expanded disjoint write scope、integration order、review gate を handoff packet に載せます
- 複数 writer を要する場合は、衝突 target を先行 / 後続 wave に分けます。安全に分離できる writer は同一 wave、追加判断が要る writer は current checkout 内の後続 wave へ直列化します
- writer ごとの path / directory / object は `team_manifest.yaml` の write policy で管理します
- selected owner/design review gate が resolved または not-needed になってから `worker`
  相当の実装を始める
- tracked repo change がある task では、selected review gate (when activated)、validation、
  commit、`origin` への push を完了条件にする
- standalone local source-branch push は reversible branch transport として、
  verified remote identity/permission、named branch、commit/tree、SHA ref
  push、remote `ls-remote` readback、push 前後の local identity 不変を
  completion evidence にする。G1/G2/G3/PR lifecycle は生成・主張しない。
  packet-bound push と PR mutation は既存 sealed 要件を使い、CI fresh-clone
  fixture は通常 publication の証拠に数えない
- tracked repo change で push が自然な完了条件なら、push の許可を取りに戻らず実行する。user が明示的に停止を指定した場合や external block がある場合は、理由を evidence に残す
- planned work、review finding、validation、commit / push、shared canon sync、follow-up 判断の completion evidence を揃えて user-facing completion を返す
- `verification.txt`、`closeout_gate.md`、`user_request_contract.md` の close 条件を満たして user-facing completion を返す
- Codex 専用事情でも、再利用可能なルールは `agents/` に昇格する
- 会話文脈由来の運用は repo 正本へ昇格してから使う
