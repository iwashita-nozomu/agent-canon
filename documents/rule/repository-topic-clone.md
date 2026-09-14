<!--
@dependency-start
contract policy
responsibility Defines the repository-topic clone lifecycle contract for generic topic/workspace clones.
upstream design ../design/dependency-manifest-design.md repository-topic clone intent
downstream design ../../agents/skills/repository-topic-clone.md operator-facing policy consumer
downstream design ../tools/repository_topic_clone.md CLI reference consumer
downstream implementation ../../tools/repository/workspace/repository_topic_clone.py lifecycle implementation
downstream implementation ../../tests/agent_tools/test_repository_topic_clone.py validates lifecycle and cleanup gates
@dependency-end
-->

# repository-topic clone ルール

この規約は、`<topic>` と `<repo>` で識別される generic repository-topic checkout に対する
一貫した規約です。対象は `workspace/<topic-slug>/<repo-name>` の単一 checkout と
その merge/readback cleanup です。`.gitmodules` 配下以外の依存変更や `.gitignore`、
差分サイズ判定を scope として使いません。スコープは構造、依存、差し替え可能単位で決めます。

## 適用範囲

`tools/repository/workspace/repository_topic_clone.py` が扱う repository checkout の
一意復元と cleanup はこの規約の対象です。`dependency-module-change` 系統は
gitlink/pin/projection の共有責務を担い、この文書の clone 実装責務を重複して
所有しません。

## 事前条件

- `--url`、`--repo-name`、`--workspace-root`、`--topic`、`--branch`、
  `--owner-evidence` が完全一致する状態。
- `--workspace-root` は selected repository の Git toplevel と一致し、root の regular な
  tracked `.gitignore` が `workspace/` を repository-owned boundary として ignore する状態。
- `prepare` と `merge-main` は workspace/topic directory を作る前に root、symlink、
  `.gitignore` ownership、ignore probe を検証し、検証 receipt を残した後だけ clone lifecycle
  に進みます。non-repository、nested root、missing/untracked `.gitignore`、global/info
  exclude のみの ignore は typed failure として既存 state を保持します。
- marker が同一 topic/repo/branch/url/evidence で一致し、`git status` が clean かつ
  detached/merge-conflict でないこと。
- local/remote の branch 不在時のみ fresh 作成に進める。存在する branch は
  別 special route で拒否せず、generic operation に戻して再評価する。
- `main`/`origin/main` の branch は source owner にはせず、branch 起点・merge ベースとしてのみ扱う。

### Checkout mode

`prepare` は `--checkout-mode linked-worktree|independent-clone` を必須の選択値として
受け取ります。parent または同一 repository の branch は `linked-worktree`、dependency
repository の変更は `independent-clone` を使います。どちらも同じ
`<anchor>/workspace/<topic>/<repo>` に配置し、branch ごとに topic 名を分けます。branch
hash や group 階層を path に追加しません。

linked worktree は native Git の shared refs/config と per-worktree index を使います。
writer packet と task marker は各 worktree に属し、別 worktree の状態を共有・上書きしません。
independent clone も同じ path、marker、writer packet、branch identity の検証を通ります。

mode の選択・作成は lifecycle command が行い、manual clone や手動 worktree 作成へ迂回しません。

## clone ライフサイクル

- `prepare` は必ず `workspace/<topic-slug>/<repo-name>` の computed path を返す。
- 既存 clean checkout が exact identity と一致すれば local/remote named branch を再利用する。
  computed path の occupant、URL、owner evidence、branch upstream が不一致なら typed
  collision として状態を保持する。
- requested branch が local/remote のどちらにも無い場合だけ、最新 `origin/main` から作る。
- write-capable clone の `writer-target.json` は handoff の repeated `--allowed-path` を
  materialize する。既存 packet の `allowed_paths` は検証して引き継ぎ、別の値で上書きしない。
  新規 prepare に allowed path がない場合は packet を作らない。
- merge 前に PR/PR head 更新を前倒しせず、`merge-main` は通常 merge を要求する。
- raw `git merge` / `git rebase` は writer route では使わず、integration executor が
  `repository_topic_clone.py merge-main`、`finalize-merge`、`resume-merge` を通す。
- task owner の非空 `--owner-evidence` と computed path、remote、branch identity が一致
  する限り、canonical `prepare` と `merge-main` は operation-level の追加承認なしで
  実行できます。reuse は `prepare` に含まれます。これは repo-local workspace lifecycle
  にだけ適用し、共有 checkout の raw Git mutation authority を変更しません。

  `dependency_module_change.py status` は adapter-only の read command であり、generic
  lifecycle、owner-evidence、または operation-level approval carve-out には含めません。

コマンドの引数と使用例は [CLI 参照の基本操作](../tools/repository_topic_clone.md#基本操作) を使います。

### 競合の再開

競合で停止した merge の再開・完了は `finalize-merge` またはその alias
`resume-merge` だけが行います。両方とも保存された inventory と plan を current checkout に
対して検証し、unmerged state、hunk identity、unaffected content の readback が通らなければ
commit しません。`conflict_preservation.py validate` 単体は診断用です。
操作構文は [CLI 参照の競合の再開](../tools/repository_topic_clone.md#競合の再開) を使います。

## クリーンアップ

repository-topic checkout は、変更を正規の反映先へ運ぶための一時 material です。
変更の durability は publish/integration owner が PR head、remote branch、または integration target
への反映で先に成立させます。cleanup はその durability を local branch retention の理由として
もう一度持ち直す工程ではありません。

- task owner は対象 checkout の利用が終わり、先行する publish/integration operation が完了したら、
  canonical `cleanup --apply` を直ちに実行します。タスク全体の終了、PR merge、定期掃除まで
  checkout 回収を先送りしません。「また使うかもしれない」「復旧用に残す」は保持理由にしません。
- cleanup が扱う対象は request から計算した exact clone path と、その lifecycle が所有する
  topic material だけです。別 agent / user の shared checkout、unknown branch、workspace 全体を
  探索して消しません。owner evidence、marker、URL、branch identity は削除対象の同定に使います。
- `linked-worktree` は worktree/topic path と、その request 専用の local topic branch を同じ
  closeout material として回収します。local branch を worktree から切り離して復旧用に残すことを
  既定にしません。linked-worktree の local branch cleanup に別の recoverability gate や追加の
  destructive-approval round は設けません。remote PR branch は open PR の参照先なので local cleanup
  では削除せず、merge 後の remote branch cleanup は publication owner が扱います。
- `independent-clone` の既存 cleanup admission と receipt contract はこの変更では触りません。
  clone directory の回収後は clone-local branch も material とともに消えます。
- cleanup 実行後は exact clone path が存在しないことを read back し、linked-worktree では対象
  worktree と local topic branch が残っていないことを確認します。sibling worktree / sibling branch、
  remote PR branch、無関係な refs は保持します。
- clone と topic root は同一 receipt で扱い、空になった topic root も同じ closeout で削除します。
  管理外 path への退避や別 registry で一時 material retention を延命しません。

削除の実行構文は [CLI 参照の基本操作](../tools/repository_topic_clone.md#基本操作) を使います。

## 例外/フォールバック

specialized skill の precondition mismatch は adapter だけを外し、generic operation を
続けます。generic lifecycle 自身が検出した branch/marker/evidence collision は current
state を保持する typed failure であり、manual clone、別 path、暗黙 checkout へ迂回しません。
`repository-kind post-clone decorator` は prepare/merge 後の owner check だけを持ち、
path/base/branch/merge/cleanup authority を持ちません。
repository-topic clone は依存モジュールの branch 特化パスを使わず、generic route の
一貫結果を前提とします。

## 関連正本

- [documents/rule/dependency-module-changes.md](dependency-module-changes.md): gitlink/pin/projection の所有責務
- [agents/skills/repository-topic-clone.md](../../agents/skills/repository-topic-clone.md): 実行ルート
- [documents/tools/repository_topic_clone.md](../tools/repository_topic_clone.md): CLI 参照

## Evidence And Assumption Ledger

| kind | statement | evidence / owner | status |
| --- | --- | --- | --- |
| assumption | `workspace/` は selected repository root の regular/tracked `.gitignore` が所有する repository-owned boundary です。 | `tools/repository/workspace/repository_topic_clone.py` の root/ignore gate、`tests/agent_tools/test_repository_topic_clone.py` の invalid-root regression | explicit |
| evidence | `git check-ignore -v --no-index -- workspace/.agent-canon-workspace-probe` の source path が root `.gitignore` と一致します。 | create/merge precondition; global/info exclude source は拒否 | required |
