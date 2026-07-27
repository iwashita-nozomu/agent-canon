<!--
@dependency-start
contract policy
responsibility Defines the general dependency-module change contract and source-clone lifecycle without owning editor state.
upstream design ../design/dependency-manifest-design.md dependency ownership and header graph model
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md parent pin and shared-surface ownership
downstream implementation ../../tools/agent_tools/dependency_module_change.py enforces clone lifecycle and cleanup gates
downstream implementation ../../tools/update_agent_canon.sh refuses parent vendor source mutation
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
projection を提供する場所であり、source branch として直接編集しません。

依存 source を変更する場合の唯一の source edit surface は、task/context/lifecycle
境界として新規または既存の topic workspace に置く clone です。topic workspace
は親 repository root直下の `workspace/<topic-slug>` で決まり、中には親 repository cloneと必要な
dependency source cloneだけを同列に置きます。clone名は module basenameだけ
（`<module-basename>`）で、branchはclone内部のGit identityです。同じtopicで
同じmoduleの別branchを併存させず、別責務・別branchは別topicにします。
clone の URL は `.gitmodules` の URL、Git-local marker、actual checked-out
branch と一致しなければ再利用できません。source clone の変更はその
branch/PR で管理し、親 repository では clean pin と projection だけを扱います。
`prepare --branch` の task branch が remote にあれば tracking checkout、なければ
manifest branch（なければ remote HEAD）から新規 branch を作ります。

host layout は `<parent-repo-root>/workspace/<topic-slug>/<clone-basename>` です。
devcontainer は topic workspace root（選択 repo root の親）を一度だけ
`/workspace` へ bind mountし、個別 cloneや親 repositoryの二重 mountを作りません。
container env の `AGENT_CANON_WORKSPACE_ROOT` は `/workspace` 固定です。host
tool は未指定なら選択 repository の親 directoryから導出し、選択 repository
rootを越える検索・編集はこの tool の責務外です。

mount target と選択 repo の作業 directory は別の devcontainer 契約です。
通常の runtime pack の既存 `workdir` schema は変更せず、
`.devcontainer/generate-runtime-compose.sh` だけが選択 clone の親である topic
root (`..`) を一度だけ source にし、選択 repo の working directory を
`/workspace/<clone-basename>` に materialize します。build context は repo (`..`)
のままです。通常 Docker/CI runner の `/workspace` 意味はこの devcontainer
契約から変更しません。

作業結果を保存する report、test result、log、PR evidence は source clone
や vendor の代替ではありません。各 results owner surface の規約に従って
保存し、source identity や cleanup の判定に混ぜません。

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

## AgentCanon update の具体例

AgentCanon source を変更するときは、parent の `vendor/agent-canon` を
source branch として扱いません。owner evidence を確認し、必要なら
`dependency_module_change.py prepare --topic <topic> --module vendor/agent-canon --branch <branch> --owner-evidence <file>` で
`workspace/<topic-slug>/<module-basename>` を再利用または作成し、その独立
clone で source branch/PR を進めます。parent mode の
`tools/update_agent_canon.sh merge-main-into-current*` は vendor checkout
を変更する旧経路ではなく、この source-clone route を案内して停止します。
standalone AgentCanon source checkout の source mode は維持します。
