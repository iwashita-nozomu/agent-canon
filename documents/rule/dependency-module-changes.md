<!--
@dependency-start
contract policy
responsibility Defines dependency-module identity, pin, and projection policy over the generic repository topic clone lifecycle.
upstream design ./repository-topic-clone.md generic repository topic clone lifecycle
upstream design ../design/dependency-manifest-design.md dependency ownership and header graph model
downstream implementation ../../tools/agent_tools/dependency_module_change.py applies the dependency policy decorator
downstream design ../agent-canon/agent-canon-update-route.md routes standalone AgentCanon source updates
downstream design ../../agents/skills/dependency-module-change.md exposes the short skill route
@dependency-end
-->

# 依存モジュール変更規約

## Reader Map

この規約は `.gitmodules` identity、gitlink、pin、projection の判断を所有します。
clone path、branch reuse、`origin/main` merge、publication evidence、cleanup は
[`repository-topic-clone.md`](repository-topic-clone.md) が所有します。AgentCanon update
はこの組合せを使う一例であり、別の clone 手順を持ちません。

## 責務境界

- 親 repository の `.gitmodules` が module path、URL、任意 branch を所有する。
- `dependency_module_change.py` は構造化 manifest から URL と repository name を解決し、
  generic `RepositoryTopicCloneRequest` を構成する。
- `repository_topic_clone.py` が唯一の `workspace/<topic-slug>/<repo-name>` path、branch、
  merge、publication readback、cleanup authority を決定する。
- dependency decorator は prepare/merge 後に gitlink、pin、projection、親側 validation を
  接続し、generic lifecycle の path/base/branch/merge/cleanup を変更しない。

repository kind は clone 後の policy decorator です。dependency skill の前提が成立しない
場合は decorator だけを外し、要求された clone/edit/update operation を generic owner へ
戻します。manual clone、別 workspace topology、operation refusal は代替 routeではありません。

## AgentCanon parent state decision table

親の `vendor/agent-canon` が submodule の場合、stage-0 mode-`160000` の
exact path record が現在の gitlink pin authority です。親 `HEAD:<path>` は
比較用の readback であり、staged pin の代わりにはなりません。通常の
`git clone --recurse-submodules` が作る clean detached checkout は、source
`HEAD ==` stage-0 pin のとき update route に受け入れます。

| 親 vendor state | 判定 | 次の操作 |
| --- | --- | --- |
| stage-0 欠落・複数・誤 mode/path、unresolved index | typed hold | index を保持して修復後に再実行 |
| detached dirty、または source `HEAD !=` stage-0 pin | typed hold | branch attach や clone を行わない |
| detached exact pin、local `main` absent/equal/ancestor | accepted attach candidate | main を create/switch、ancestor は `merge --ff-only` |
| local `main` descendant/divergent、別 worktree が main を所有、topic branch | typed hold | 既存 ref/worktree を変更しない |
| remote URL、ls-remote、isolated probe object、probe cleanup の失敗 | typed readback hold | facts/details を全て出力し、frontier 前に同じ non-zero を返す。cleanup evidence は保持する |
| local `origin/main` が absent | attach prerequisite | plan は ready とし、attach の直前 fetch/readback に委譲 |
| local `origin/main` が unrelated または remote の descendant | `submodule_origin_main_mismatch` | source refs/worktree を保持し、frontier 前に non-zero を返す |

Attach candidate の `plan` は `.gitmodules` URL と valid SHA を S1/S2 の
coherent remote probe で確認します。probe は parent-owned disposable Git と
source object database の read-only alternates だけを使い、source refs、objects、
`FETCH_HEAD`、worktree は変更しません。remote main の advance 単独は hold では
ありません。plan は source `origin/main` を読むだけで fetch せず、missing は
attach prerequisite、unrelated/rewind は typed hold とします。

attach は直前に `origin/main` を fetch して readback し、HEAD、main/tracking
refs、branch config、`FETCH_HEAD`、object files、status、worktrees を capture
した narrow transaction として create/switch/`merge --ff-only` と upstream を
適用します。fetch、upstream、readback の失敗は old-value guard 付き rollback
で capture 前状態を復元し、`attach_rollback=pass|fail` を出力します。
rollback または transaction evidence cleanup が失敗した場合は typed hold とし、
transaction directory と rollback evidence を保持して復元済みとは報告しません。
route は
reset、stash、force ref update、clone fallback を使わず、materialization の
merge/write-set と collision 判定は generic owner `update_materialization` に
委譲します。

plan probe の cleanup も fail-closed です。probe removal 成功時だけ path を
空にして cleanup pass を出し、失敗時は parent-owned probe path を保持した
cleanup hold を返します。plan detail は stage-0、remote、tracking、materialization
の named facts を各 owner から直接 render し、位置引数のずれで不正な stage-0
値が remote facts に混入しないようにします。

## Operation と完了証拠

### Prepare

```bash
python3 tools/agent_tools/dependency_module_change.py --root <parent-root> prepare \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file>
```

manifest identity を generic request へ写像し、exact clone/branch を再利用するか、不在
branch を最新 `origin/main` から作成します。`PrepareReceipt`、module path/URL readback、
computed clone path の一致が完了証拠です。
owner evidence、manifest identity、computed path が一致する canonical prepare は
operation-level の追加承認なしで実行できます。この扱いは repo-local topic workspace
の lifecycle command にだけ適用し、共有 checkout の protected raw Git route には継承
されません。

### Merge main

```bash
python3 tools/agent_tools/dependency_module_change.py --root <parent-root> merge-main \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file>
```

generic owner が `fetch origin main` と通常の `git merge --no-edit origin/main` を実行し、
ancestor proof を返します。dependency decorator はその後に pin/projection impact を確認します。
dirty state と conflict は破棄せず typed evidence として保持します。

### Cleanup

```bash
python3 tools/agent_tools/dependency_module_change.py --root <parent-root> cleanup \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file> \
  [--candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>]] [--apply]
```

通常の cleanup は manifest から解決した computed clone を再計算し、selected Git toplevel、
owner evidence/marker、URL、branch、clean non-detached state、および fetch した
`origin/<branch>` の commit/tree と local `HEAD` の commit/tree の一致だけを検証します。
publication packet を作らなくても dry-run/apply でき、unknown sibling は保持し、topic directory
は空の場合だけ削除します。candidate CAS、PR lifecycle、publication readback は任意の追加
evidence ですが、いずれかを指定する場合は candidate CAS と PR lifecycle を一組で指定し、
merged state では publication readback transition、merge commit/tree、`origin/main`
containment も検証します。proof 不一致または unknown dirty/collision は typed hold として
保持します。

## Scope と failure

scope は repository structure、dependency edge、差し替え可能な責務単位、validation route
から形成します。`.gitignore`、単一 file、行数、diff 件数は owner や lifecycle route の
authority ではありません。

manifest、URL、owner evidence、branch、publication identity の不足や不一致は typed hold
として状態を保持します。adapter 固有情報が無い場合は `topic-identity-required` を返し、
caller は generic URL/repo identity を補って同じ requested operation を続けます。

## Validation

```bash
python3 -m pytest tests/agent_tools/test_dependency_module_change.py -q
python3 -m pytest tests/agent_tools/test_repository_topic_clone.py -q
python3 tools/agent_tools/check_agent_runtime_alignment.py
```

dependency source publication 後は親 repository で exact gitlink pin と必要 projection を更新し、
親 owner の targeted check を実行します。
