<!--
@dependency-start
contract policy
responsibility Defines dependency-module identity, pin, and projection policy over the generic repository topic clone lifecycle.
upstream design ./repository-topic-clone.md generic repository topic clone lifecycle
upstream design ../design/dependency-manifest-design.md dependency ownership and header graph model
upstream design ../operations/BRANCH_SCOPE.md workspace dependency checkout and actual input readback
downstream implementation ../../tools/repository/workspace/dependency_module_change.py applies the dependency policy decorator
downstream design ../agent-canon/agent-canon-update-route.md routes standalone AgentCanon source updates
downstream design ../../agents/skills/dependency-module-change.md exposes the short skill route
@dependency-end
-->

# 依存モジュール変更規約

## Reader Map

この規約は `.gitmodules` identity、gitlink、pin、projection の判断を所有します。
checkout path、branch reuse、`origin/main` merge、publication evidence、cleanup は
[`repository-topic-clone.md`](repository-topic-clone.md) が所有します。AgentCanon update
はこの組合せを使う一例であり、別の checkout 手順を持ちません。

## 責務境界

- 親 repository の `.gitmodules` が module path、URL、任意 branch を所有する。
- `dependency_module_change.py` は構造化 manifest から URL と repository name を解決し、
  generic `RepositoryTopicCloneRequest` を構成する。
- `repository_topic_clone.py` が唯一の `workspace/<topic-slug>/<repo-name>` path、checkout mode、branch、
  merge、publication readback、cleanup authority を決定する。
- dependency decorator は prepare/merge 後に gitlink、pin、projection、親側 validation を
  接続し、generic lifecycle の path/base/branch/merge/cleanup を変更しない。

repository kind は checkout 後の policy decorator です。dependency skill の前提が成立しない
場合は decorator だけを外し、要求された checkout/edit/update operation を generic owner へ
戻します。dependency repository は `independent-clone` mode を使い、manual clone、別
workspace topology、operation refusal は代替 routeではありません。

## 依存 PR → exact pin → consumer 実行

branch 確認の対象・観測項目・再確認境界は
[Branch Scope と Git ワークフロー](../operations/BRANCH_SCOPE.md) に従います。
`workspace/<...>` にある依存の source 開発 clone と、consumer が実際に読む
checkout の branch / HEAD は両方確認し、manifest の pin だけで確認済みにしません。
この順序は gitlink だけでなく、consumer owner が manifest / lock 等で管理する
Git source の pin にも適用します。依存 adapter に別の pin 管理機構は追加しません。

依存の変更が consumer の実行に必要な場合は、次の順序を守ります。

1. 依存 repository の Issue と編集 scope を確定し、generic lifecycle が選ぶ
   最新 main 起点または関連 Issue の active branch で修正します。branch 名に
   対応 Issue 番号を含め、依存側の focused validation を行います。この段階の
   依存単体の開発検証は許されますが、consumer の pinned validation ではありません。
2. 依存側を commit / push して PR を公開し、PR の repository、番号、remote の
   exact head SHA と取得可能性を読み戻します。ローカル commit だけ、将来作る PR、
   PR 番号だけ、branch 名や可変 ref だけでは consumer 実行の前提を満たしません。
3. consumer owner の既存 gitlink / manifest / lock に採用する full commit SHA を
   固定し、実際に解決される checkout / build input がその pin であることを確認して
   から consumer を実行・検証します。consumer の Issue / PR に依存 PR、採用 SHA、
   pin の所有 path、実使用 path / SHA、検証結果を残します。未 commit の依存変更や
   workspace clone の偶然の HEAD を、local override / install / cache 経由で読ませません。
4. 依存 PR の head が更新されたら、現在の pin を保持するか新 SHA を採用するかを
   明示します。pin を可変 head に自動追従させません。新しい入力を採用した場合は
   その pin と使用先を再照合し、影響する consumer 検証をやり直します。merge 後に
   merge / squash commit へ pin を変更する場合も同じ扱いです。

未 merge の PR head を使うことと、merge 済み依存を使うことは区別して記録します。
merge 必須かは consumer の既存受入契約に従い、この規約だけで全 PR の merge 待ちを
追加しません。変更不要の既存 pin には新しい依存 PR を要求しません。依存同士に
変更の前提関係がある場合は、既存の dependency-analysis が定める順序で同じ手順を
適用し、他 module の未公開変更を前提にした成功を報告しません。

source-free な AgentCanon consumer には、この規約を理由に `vendor/agent-canon`、
submodule pin、root view、runtime import を新設しません。AgentCanon の source 更新・
配布は既存 owner の source / publication / runtime identity readback に従います。
以下の parent state table は、実際に対応する submodule を持つ親だけに適用します。

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
python3 tools/repository/workspace/dependency_module_change.py --root <parent-root> prepare \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file> [--allowed-path <relative-path> ...]
```

manifest identity を generic request へ写像し、exact independent checkout/branch を再利用するか、
不在 branch を最新 `origin/main` から作成します。`PrepareReceipt`、module path/URL readback、
computed checkout path の一致が完了証拠です。
owner evidence、manifest identity、computed path が一致する canonical prepare は
operation-level の追加承認なしで実行できます。この扱いは repo-local topic workspace
の lifecycle command にだけ適用し、共有 checkout の protected raw Git route には継承
されません。

### Merge main

```bash
python3 tools/repository/workspace/dependency_module_change.py --root <parent-root> merge-main \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file> [--allowed-path <relative-path> ...]
```

generic owner が `fetch origin main` と通常の `git merge --no-edit origin/main` を実行し、
ancestor proof を返します。dependency decorator はその後に pin/projection impact を確認します。
dirty state と conflict は破棄せず typed evidence として保持します。

### Cleanup

```bash
python3 tools/repository/workspace/dependency_module_change.py --root <parent-root> cleanup \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file> [--allowed-path <relative-path> ...] \
  [--candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>]] [--apply]
```

通常の cleanup は manifest から解決した computed checkout を再計算し、selected Git toplevel、
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
python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py
```

pin / projection を持つ依存では、source PR publication 後に親 repository の exact pin と
必要 projection を更新・照合してから、親 owner の targeted check を実行します。
