<!--
@dependency-start
contract policy
responsibility Defines dependency-module identity, pin, and projection policy over the generic repository topic clone lifecycle.
upstream design ./repository-topic-clone.md generic repository topic clone lifecycle
upstream design ../design/dependency-manifest-design.md dependency ownership and header graph model
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md parent pin and shared-surface ownership
downstream implementation ../../tools/agent_tools/dependency_module_change.py applies the dependency policy decorator
downstream implementation ../../tools/update_agent_canon.sh routes AgentCanon dependency updates
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
