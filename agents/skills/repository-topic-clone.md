# repository-topic-clone

<!--
@dependency-start
contract skill
responsibility Documents the short human-facing route for repository-topic clone operations.
upstream design ../canonical/skills.md skill canon registry
upstream design ../internal-routines/design-implementation-correspondence.md design read/fingerprint/handoff route
upstream design ../../documents/rule/repository-topic-clone.md repository-topic clone policy
upstream design ../../documents/contracts/github-first-module-and-devcontainer-policy.md topic workspace boundary
downstream implementation ../../tools/agent_tools/repository_topic_clone.py lifecycle tool
downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates skill registration
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

- `python3 tools/agent_tools/repository_topic_clone.py prepare ...`
- `python3 tools/agent_tools/repository_topic_clone.py merge-main ...`
- `python3 tools/agent_tools/repository_topic_clone.py cleanup ...`

`--workspace-root` は既存 topic root を再利用し、指定 topic の
`workspace/<topic-slug>` だけを管理します。task owner の非空 `--owner-evidence` と
computed path / remote / branch identity が検証できる場合、canonical `prepare` と
`merge-main` は個別操作ごとの追加承認なしで実行します。reuse は `prepare` に含まれます。これはこの
canonical lifecycle command が workspace 管理と衝突保持を所有するためであり、raw
shared-checkout Git の承認境界を緩和するものではありません。

`prepare` と `merge-main` は selected repository root の Git toplevel、既存 symlink component、
regular/tracked root `.gitignore`、および repository-owned `workspace/` ignore probe を
clone/topic directory の作成前に検証します。検証を通った request は computed
`workspace/<topic-slug>/<repo-name>` に到達し、invalid root、nested root、missing/untracked
`.gitignore`、global/info exclude は typed failure として作成前の state を保持します。

`dependency_module_change.py status` は dependency adapter の read-only 状態確認です。
これは generic lifecycle、owner-evidence、または operation-level approval carve-out の
対象ではありません。

exact local/remote branch は同じ prepare で再利用し、不一致は
state-preserving typed collision とします。作業完了時はこの skill が cleanup を
自動的に `--apply` するのではなく、candidate CAS、PR lifecycle、必要な publication
readback、owner evidence、local/remote/PR head の一致を canonical tool に渡します。
preflight が成功した場合だけ `CleanupProof` / cleanup receipt を受け取り、失敗時は
clone と topic root を保持した typed hold を closeout に記録します。specialized adapter
が適用外でもこの generic operation は継続します。

`cleanup` は同じ selected Git toplevel と exact clone identity を検証し、candidate CAS、PR
lifecycle、publication readback の proof を満たした場合だけ `CleanupProof` を返します。
cleanup の exact-root gate は維持しつつ、既存 clone の proof-gated removal は root ignore の
後続 driftだけで止めません。`dependency_module_change.py status` と `projected_clone_path`
は read-only projection のままで directory を作成しません。
