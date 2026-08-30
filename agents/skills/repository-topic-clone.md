# repository-topic-clone

<!--
@dependency-start
contract skill
responsibility Documents the short human-facing route for repository-topic clone operations.
upstream design ../canonical/skills.md skill canon registry
upstream design ../internal-routines/design-implementation-correspondence.md design read/fingerprint/handoff route
upstream design ../../documents/rule/repository-topic-clone.md repository-topic clone policy
upstream design ../../documents/contracts/github-first-module-and-devcontainer-policy.md topic workspace boundary
downstream implementation ../../tools/repository/workspace/repository_topic_clone.py lifecycle tool
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates skill registration
@dependency-end
-->

## 目的

repository-topic clone の lifecycle、normal merge、receipted cleanup を
`workspace/<topic-slug>/<repo-name>` の責務境界で扱います。

## 使用 route

依存 module ではなく repository-topic clone を扱う場合、この skill は
`repository_topic_clone.py` を起点にし、`.gitmodules` の gitlink/pin/projection
判断は `dependency-module-change` へ委譲し重複しません。
scope は structure、dependency、差し替え可能な責務単位から形成し、`.gitignore`、
file size、diff size で owner route を固定しません。

## 使う command

- `python3 tools/repository/workspace/repository_topic_clone.py prepare ...`
- `python3 tools/repository/workspace/repository_topic_clone.py merge-main ...`
- `python3 tools/repository/workspace/repository_topic_clone.py finalize-merge ...`
- `python3 tools/repository/workspace/repository_topic_clone.py cleanup ...`

`prepare` の write-capable clone は repeated `--allowed-path <relative-path>` を handoff
から forward します。既存の `.agent-canon/writer-target.json` がある場合はその
`allowed_paths` を検証して引き継ぎ、別の値で上書きしません。新規の write-capable
prepare に allowed path を渡さない場合は target packet を materialize しません。

`--workspace-root` は既存 topic root を再利用し、指定 topic の
`workspace/<topic-slug>` だけを管理します。task owner の非空 `--owner-evidence` と
computed path / remote / branch identity が検証できる場合、canonical `prepare` と
`merge-main` は個別操作ごとの追加承認なしで実行します。reuse は `prepare` に含まれます。これはこの
canonical lifecycle command が workspace 管理と衝突保持を所有するためであり、raw
shared-checkout Git の承認境界を緩和するものではありません。

競合で停止した merge の再開・完了は `finalize-merge` またはその alias
`resume-merge` だけが行います。両方とも保存された inventory と plan を current clone に
対して検証し、unmerged state、hunk identity、unaffected content の readback が通らなければ
commit しません。`conflict_preservation.py validate` 単体は診断用です。

`prepare` と `merge-main` は selected repository root の Git toplevel、既存 symlink component、
regular/tracked root `.gitignore`、および repository-owned `workspace/` ignore probe を
clone/topic directory の作成前に検証します。検証を通った request は computed
`workspace/<topic-slug>/<repo-name>` に到達し、invalid root、nested root、missing/untracked
`.gitignore`、global/info exclude は typed failure として作成前の state を保持します。

`dependency_module_change.py status` は dependency adapter の read-only 状態確認です。
これは generic lifecycle、owner-evidence、または operation-level approval carve-out の
対象ではありません。

exact local/remote branch は同じ prepare で再利用し、不一致は
state-preserving typed collision とします。作業完了時はこの skill が computed clone path を
canonical tool に渡し、selected Git toplevel、owner evidence/marker、URL、branch、clean
non-detached state、および fetch した `origin/<branch>` の commit/tree と local head/tree の
一致を preflight します。通常の closeout は workspace packet artifact を作らず、preflight が
成功した場合だけ `CleanupProof` / cleanup receipt を受け取ります。失敗時は clone と topic
root を保持した typed hold にします。specialized adapter が適用外でもこの generic operation
は継続します。

marker は canonical `repository-topic-clone.*` namespace を優先します。canonical marker が
完全に欠ける既存 dependency clone だけは、legacy `agent-canon.topic.*` の topic、
role=`module`、module basename、normalized URL、branch、placement=`workspace-continuation`、
owner-evidence SHA が全て一致する場合に限り read-only compatibility として扱います。
partial/mismatch/unknown role・placement は typed hold で、cleanup dry-run は Git config marker
を書き換えません。

candidate CAS、PR lifecycle、publication readback は任意の追加 evidence です。いずれかを
渡す場合だけ candidate CAS と PR lifecycle の coherent set を検証し、merged state では
strict publication readback、merge tree、`origin/main` containment を追加確認します。
publication evidence は proof を enrich しますが、通常の cleanup のために materialize しません。
cleanup の exact-root gate は維持しつつ、既存 clone の proof-gated removal は root ignore の
後続 driftだけで止めません。`dependency_module_change.py status` と `projected_clone_path`
は read-only projection のままで directory を作成しません。
