<!--
@dependency-start
contract policy
responsibility Defines the general dependency-module change contract and source-clone lifecycle without owning editor state.
upstream design ../design/dependency-manifest-design.md dependency ownership and header graph model
upstream design ../contracts/github-first-module-and-devcontainer-policy.md canonical topic workspace and VS Code workspace boundary
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md parent pin and shared-surface ownership
downstream implementation ../../tools/agent_tools/dependency_module_change.py enforces clone lifecycle and cleanup gates
downstream implementation ../../tools/update_agent_canon.sh routes to vendor-first parent topic branch work with managed workspace fallback
downstream design ../../agents/skills/dependency-module-change.md exposes the short skill route
@dependency-end
-->

# 依存モジュール変更規約

この規約は、submodule やその他の依存 module の source を変更する作業に
共通して適用します。AgentCanon update はこの規約を使う具体例であり、
独立した例外規約ではありません。

## 責務の分離

依存 module の identity は親 repository の `.gitmodules` が持ちます。
そこには module の `path`、`url`、任意の default `branch` を置きます。`vendor/<module>` はその identity が指す pin と runtime
projection を提供し、clean な named topic branch にいるときは source owner にもなります。
親の pin/root projection が pass になる状態は、`vendor/<module>` が clean な
`main`（`DEFAULT_BRANCH`）にあり、submodule の worktree `HEAD` が staged index
gitlink (`:$PREFIX`) と一致する状態です。

source edit の owner は、clean な named topic branch の `vendor/<module>` です。
`main` は topic branch を作成する起点であり、source edit の owner にはしません。
別 topic の dirty vendor state によって親 vendor が占有されている場合のみ、
`workspace/<topic-slug>/` の standalone clone を source clone として作成/再利用します。
topic workspace
の定義、親 repository の ignore rule、devcontainer mount、VS Code workspace
運用の禁止、`.vscode/` 共有面との境界は
[`contracts/github-first-module-and-devcontainer-policy.md`](../contracts/github-first-module-and-devcontainer-policy.md)
を正本として参照します。この文書は module identity、clone の再利用、branch、
cleanup、lifecycle command の固有判断だけを持ちます。

clone名は module basenameだけ（`<module-basename>`）で、branchはclone内部の
Git identityです。同じtopicで同じmoduleの別branchを併存させず、別責務・別branch
は別topicにします。
clone の URL は `.gitmodules` の URL、Git-local marker、actual checked-out
branch と一致しなければ再利用できません。source checkout の変更はその
topic branch/PR で管理し、source publication 後の親 repository root では clean
pin と projection だけを扱います。
`prepare --branch` の task branch が remote にあれば tracking checkout、なければ
manifest branch（なければ remote HEAD）から新規 branch を作ります。

作業結果を保存する report、test result、log、PR evidence は source clone
や vendor の代替ではありません。各 results owner surface の規約に従って
保存し、source identity や cleanup の判定に混ぜません。

## AgentCanon parent state decision table

この表は、parent mode における AgentCanon vendor の owner、projection、dirty
fallback の判定表であり、`tools/update_agent_canon.sh` と各 runtime shim は
ここを正本として参照します。`cmd_latest` の更新対象 branch 引数（通常は
`main`）は topic identity ではありません。requested topic は既存の topic
owner 引数または topic environment owner を再利用し、他に明示指定がない場合
だけ `AGENT_CANON_TOPIC_SLUG` を唯一の explicit requested topic とします。

| 親 vendor 状態 | topic identity | owner / next action |
| --- | --- | --- |
| clean `main`、かつ worktree `HEAD == :$PREFIX` staged index gitlink | 不要 | parent pin/root projection pass |
| clean named topic branch | `current_branch` | current `vendor/<module>` が source owner |
| dirty、requested topic 未指定 | なし | typed stop: `NEXT_ACTION=topic_identity_required` |
| dirty、requested topic == named `current_branch` | requested topic | fallback clone を作らず `materialize_current_vendor_topic_commit_push_pr_then_resume` |
| dirty、requested topic != named `current_branch` | requested topic | `workspace/<sanitized-requested-topic>/agent-canon` fallback。`workspace/main` は生成しない |
| dirty、requested topic の sanitized identity が `main` | `main` | typed stop: `NEXT_ACTION=topic_identity_required` |
| detached、pin mismatch、merge conflict、または corrupt state | — | source/pin owner を選んだ上で typed repair/rebuild route |

dirty fallback の `current_branch` は named current branch だけを指し、detached
HEAD は topic identity として扱いません。requested topic と current branch が
一致する場合の materialize/push/PR は、現在の vendor state を別 workspace に
複製する route ではありません。

## clone を作る条件

clone を作成できるのは、owner evidence により「依存 source の変更が必要」
と確定し、正しい topic workspace と branch-specific clone が存在しない場合だけです。
`prepare --topic <topic> --module <path> --branch <branch> --owner-evidence <file>` は、現在 repoが
既存 topic workspace内ならその親 rootを再利用します。外側なら workspaceの
隣に topic rootを作り、親 remoteから親 cloneを作成し、`.gitmodules` URLから
module cloneを作成または再利用して継続 pathを返します。既存 clone の
computed path、marker、actual branch、URL が一致する場合は再利用します。
親の pin PR branch は `--parent-branch <branch>` で明示し、同じ marker/actual
branch の parent clone を再利用します。

pin-only、update-only、read-only の作業では source clone を作りません。
これらの作業は親の `.gitmodules`、vendor pin、runtime projection、または
既存の read-only checker だけを扱います。owner evidence がない
`prepare` は失敗し、近い path や vendor checkout を代用しません。

module path の basename は sibling path の名前になるため、複数 module が
同じ basename を持つ `.gitmodules` は拒否します。path、URL、branch の
identity を曖昧にしたまま clone を作ることも拒否します。

## cleanup gate

cleanup は既定で dry-run です。`--apply` による削除は、対象が topic内の
computed module clone path（または parent clone path）と完全一致し、次の条件を
すべて満たす場合だけ許可します。module cloneを削除した後、parent cloneは全module
clone削除後に同じgateで削除できます。topic rootが空なら topic rootも削除します。
未知cloneは削除しません。

- `.gitmodules` の URL と clone の `origin` URL が一致する。
- `git fetch --all --prune` が成功する。
- worktree、index、untracked files が空である。
- linked worktree が追加で登録されていない。
- fetch 後の `git rev-list --all --not --remotes` が空である。
- `AGENT_CANON_BRANCH_WORKTREE_AUTHORITY` とその reason、
  `AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval` とその
  reason が同じ command segment から渡されている。

最後の Git oracle が空なら、remote に全 state が存在するため、open PR の
有無を待つ必要はありません。remote branch に state がある open PR でも
clone は冗長になり得るため、PR/pin/root-sync 状態を cleanup の前提に
しません。

dirty、unique local commits、URL mismatch、linked worktree、unknown path、
fetch failure は削除を保留します。これは旧 topology を成功経路として認める
ことではなく、cleanup が安全条件を満たさず停止したことを意味します。
source の移送後は独立 clone、clean vendor pin projection、results owner
surface の状態だけを完成形として残します。

## lifecycle command

一般 tool の責務は次の 3 つです。

- `status --topic <topic>`: topic membershipと`.gitmodules` identityを読む。
- `prepare --topic <topic> --module <path> --branch <branch> --owner-evidence <file> [--parent-branch <branch>]`: 条件を検証してtopic parent/module cloneを作成または再利用し、`PARENT_ROOT`、`SOURCE_CLONE`、`CONTINUE_PATH` を返す。
- `cleanup --topic <topic> --module <path> --expected-clone <absolute-path>`: dry-run で
  判定し、`--apply` のときだけ cleanup gate を満たす clone を削除する。
- `cleanup --topic <topic> --parent --expected-parent <absolute-path>`: module cloneが
  無い場合だけparent cloneと空topic rootを同じgateで削除する。

## 再構築ルート（復旧）

状態破損・書込先誤り・競合解消失敗・候補一致不能などの復旧経路では、
未知diffを逆パッチ/restore で旧状態へ戻そうとしない。`origin/main` から
clean checkout を再構築し、意図した materialized topic commits を再適用して
PR を再構築する。

- まず `origin/main` から clean checkout を再構築する。
- 意図した差分のみを再適用し、`git add -> git commit -> push -> PR` で
  新しい対象 PR/branch を作る。
- readback で PR head が一致した時点で、旧 clone を削除する。
- 未 materialize 差分が残る場合は、そのまま削除せず別 branch へ
  `commit -> push` してから再構築ルートへ進む。
- link-root/check の検査対象は「親リポジトリの現在の vendor pin と
  root projection が ready かどうか」のみとする。

## AgentCanon update の具体例

AgentCanon source は、原則として consumer repository の `vendor/agent-canon` が
唯一の source checkout です。`vendor/agent-canon` の local-specific topic
branch を create/reuse し、`local commit -> 同 commit push -> PR` を行います。
常に named branch HEAD を使用し、detached HEAD は禁止します。
ただし、`vendor/agent-canon` が既に別 topic の dirty state を持つ場合のみ、
`workspace/<topic-slug>/agent-canon` の standalone clone で同じ運用（local
commit→push→PR）を行います。
その clone は、PR 作成/更新時点で `local commit == pushed commit == PR head` が
readback され、同一 PR へ materialize した証拠が得られたら削除します。
未 materialize 差分がある場合のみ clone 削除を禁止し、先に同一 PR へ
再materialize します。PR publication receipt は再構築が必要な clone の cleanup
gate として扱います。
merge/readback 後は `vendor/agent-canon` の local `main` branch を `origin/main` へ fast-forward し、
parent の gitlink を merge 済み commit に一致させます。source edit はその前段の
clean named topic branch で行い、`main` は projection の pass 状態にだけ使います。
未コミット固有差分の状態で parent の pin/update あるいは projection を進めないでください。
pin projection は、まず `git add vendor/agent-canon` で stage し、
`sync check` で staged gitlink(`:$PREFIX`)と実体 `HEAD` が一致することを確認して
から commit する順で行います。
parent projection check は、clean な `AGENT_CANON_BRANCH`（既定は `main`）にあり、
staged gitlink(`:$PREFIX`) と実体 `HEAD` が一致することを pass 条件にします。
source edit の pass 条件は別であり、clean な named topic branch にいることです。
detached HEAD、main 上の source edit、gitlink mismatch は pass にしません。

AgentCanon PR 作成・更新前の必須順序は、
`fetch origin/main の read -> current parent branch へ origin/main を merge -> 衝突解消 ->
local commit (candidate freeze) -> exact candidate review -> CAS -> review 済み candidate
push -> PR作成/更新 -> merge/readback` です。
`parent vendor` が別 topic の dirty state を持つ場合にのみ、`workspace/<topic-slug>/agent-canon`
の standalone clone を使い、すでに open PR がある場合は、その PR の remote head
branch を clone/checkout して同一順序で`origin/main` を merge し、衝突解消後に
local commit を行い、同じ branch へ push して PR head を readback します。
readback が成功したら clone は削除します。
すでにその PR が merged/closed で head 更新ができない場合は、
最新 `origin/main` から linked successor branch/PR を作成し、通常の
PR publication readback 流れへ移行し、同様に PR head readback 後に clone を削除します。
merged PR の更新は行いません。
`origin/main` だけを read するだけの CAS/確認は merge の代替にならず、
merge conflict が未解消、または `origin/main` merge 済みでない candidate は PR
禁止です。
