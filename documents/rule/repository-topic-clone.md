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
  `--owner-evidence` を指定します。`--owner-evidence` は非空ファイルを要求し、その digest は
  lifecycle metadata として記録しますが、ファイル自体は操作 authority になりません。
- `--workspace-root` は selected repository の Git toplevel と一致し、root の regular な
  tracked `.gitignore` が `workspace/` を repository-owned boundary として ignore する状態。
- `prepare` と `merge-main` は workspace/topic directory を作る前に root、symlink、
  `.gitignore` ownership、ignore probe を検証し、検証 receipt を残した後だけ clone lifecycle
  に進みます。non-repository、nested root、missing/untracked `.gitignore`、global/info
  exclude のみの ignore は typed failure として既存 state を保持します。
- marker が同一 topic/repo/branch/url で一致すること。branch mutation、merge、cleanup は
  `git status` が clean かつ detached / merge-conflict でないこと。既存 exact target の
  metadata-only refresh は clone lifecycle の identity 検証 route に従います。
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
新規worktreeの公開rootはanchorのアクセスmodeを引き継ぎます。準備中のscratchの
private modeを公開checkoutへ固定し、設定済みtool residentの読取を妨げません。
writer packet と task marker は各 worktree に属し、別 worktree の状態を共有・上書きしません。
reserved packet 用の `info/exclude` entry は Git の common directory に属し、
linked worktree 間で共有されます。
これは ignore rule の共有であり、worktree ごとの writer packet 自体は共有しません。
同じcheckoutを再prepareする明示的なallowed pathsは、その親packetの更新として反映します。
省略時は既存のscopeを保持し、branch・remote・rootのidentity確認は継続します。
independent clone も同じ path、marker、writer packet、branch identity の検証を通ります。

mode の選択・作成は lifecycle command が行い、manual clone や手動 worktree 作成へ迂回しません。

## clone ライフサイクル

- `prepare` は必ず `workspace/<topic-slug>/<repo-name>` の computed path を返す。
- 既存 checkout の identity は computed path と実際の Git facts から照合します。remote URL、actual branch、
  checkout mode を確認し、`linked-worktree` は selected workspace と同じ Git common dir に登録されていることも
  検証します。canonical marker があれば repository/topic/URL/branch と facts の一致を要求し、partial/mismatch は
  hold します。marker がないこと自体は collision ではなく、current request が指定した exact path と Git facts が
  一致すれば `prepare` が canonical marker を materialize できます。owner-evidence digest は marker がある場合の
  lifecycle metadata であり、承認・identity・current task/handoff authority の代替ではありません。
- clean な exact checkout は local/remote named branch を再利用します。existing writer-target packet があれば検証し、
  current `--allowed-path` があればその scope を materialize し、省略時は検証済み scope を引き継ぎます。
  packet/marker の metadata-only 更新は source/index を変更せず、dirty status を clean と扱いません。
  未知の Git facts、packet の symlink/不整合、escaped path は引き続き hold します。
  legacy module marker の互換性は従来どおり exact digest を要求します。
- source/index に触れない既存 target metadata 更新は、`prepare` の通常の identity 検証前に行います。
  この操作が更新するのは task marker、Git が選択した common-directory
  `info/exclude` の reserved packet entry、および ignored writer packet だけです。
  checkout、Git index、packet 以外の tracked / untracked / ignored worktree file を編集・移動・削除せず、
  dirty state を clean と報告しません。dirty content の所有権を割り当てる操作でもありません。
  新規 checkout、branch 変更、`merge-main` は従来どおり clean state を要求します。
- requested branch が local/remote のどちらにも無い場合だけ、最新 `origin/main` から作る。
- write-capable clone の `writer-target.json` は handoff の repeated `--allowed-path` を
  materialize する。既存 packet は検証し、`--allowed-path` 省略時は既存 scope を引き継ぎます。
  明示入力時の更新は current handoff scope のみ反映します。新規 prepare に allowed path がない場合は
  packet を作りません。source discovery の `prepare` は scope を推測せずに実行でき、実際の writer scope が
  決まった後に同じ identity を使って再prepareし、current `--allowed-path` を packet にします。
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

- task owner は作業用 clone が不要になり、以下の安全条件が成立した時点で既存の
  cleanup authority に従って削除します。調査・検証・依存更新などの利用終了時に判断し、
  タスク全体の完了、PR merge、定期掃除まで先送りしません。具体的な次工程がない
  「また使うかもしれない」だけの保持はしません。失敗・中断した作業でも、必要な
  診断資料を保全し、安全条件を満たした clone は同じ扱いにします。
- tool 起動前に task owner が exact path の所有と利用終了を確認し、必要な内容を削除対象外へ保存・復元可能にします。別の agent、
  process、container mount、実行時の依存解決先が使用中、または所有・使用状態が不明なら
  保持します。未回収の変更、保持が必要な local-only refs/commits、stash、untracked/ignored
  成果物、submodule/annex content が削除対象内にしかない場合も保持し、必要な内容と
  復元方法を clone 外で確認してから再判定します。clean な `git status` や経過時間だけで
  削除可能とは判定しません。既存 tool の proof を、この利用・保全確認の代わりにしません。
  CLI の status preflight は ignored file を列挙せず、linked worktree の local head は superproject の
  commit/tree の保持だけを示します。どちらも ignored file、submodule の per-worktree Git metadata/object、
  annex-only content の保存・復元可能性を証明しません。これらの保持判断は既存 task owner の前提条件です。
- 削除後は exact path の不存在を確認し、linked-worktree では worktree list からの消失も
  確認します。既存 task/Issue の結果に削除 path と復元先、または保持 path・理由・解除条件を
  記録し、closeout では未解決の保持対象だけを引き継ぎます。新しい台帳は作りません。
  clone の削除は remote branch、clone 外の local refs、無関係な checkout、workspace 全体の
  削除を認可しません。
- `cleanup` は selected Git toplevel と computed clone identity を検証してから proof preflight
  を開始します。既存 clone の proof-gated removal は root `.gitignore` の後続 drift だけでは
  停止せず、ignore ownership の create preconditionと cleanup の exact-root gateを分離します。
- linked-worktree cleanup は proof preflight 後、exact path に対して `git worktree remove --force` を一度実行します。
  force は native worktree removal の一様な実行方法であり、dirty / untracked / unknown Git state を許可するものでは
  ありません。これらは先行する identity/clean preflight で hold します。caller が上記の保持前提を満たさず
  `--apply` を呼んだ場合、この command は Git の ignored / submodule-object 状態から内容を救出しません。
  local branch は保持し、削除後に path の不存在と `git worktree list` からの消失を readback します。
- marker は canonical `repository-topic-clone.*` namespace の全項目が一致する状態を優先します。
  canonical marker が完全に欠ける既存 dependency clone に限り、legacy
  `agent-canon.topic.*` の topic、role=`module`、module basename、normalized URL、branch、
  placement=`workspace-continuation`、owner-evidence SHA がすべて一致する場合だけ read-only
  compatibility として ready を認めます。partial/mismatch/unknown role・placement は typed
  hold とし、dry-run は Git config marker を書き換えません。
- cleanup は上記の利用終了・内容保全確認後、または closeout の残存確認時に canonical tool を呼び、request から計算した
  exact clone path、actual Git URL、branch、checkout mode、clean non-detached state を検証します。
  canonical marker がある場合は identity と current owner-evidence digest の一致を要求し、marker の partial/mismatch は
  hold します。marker がない場合も identity は current request と実際の Git facts から照合します。
  owner-evidence digest は marker がある場合の
  lifecycle consistency metadata であり、Git identity や whole-tree retention proof の代替ではありません。
  linked-worktree の `linked-superproject-head` evidence は保持された local branch と共有 Git common objects から
  superproject の commit/tree を再取得できることだけを示し、remote branch を要求しません。ignored file や submodule
  object の再取得保証ではありません。`independent-clone` は fetch した `origin/<branch>` の
  commit/tree と local `HEAD` の commit/tree が一致する external recoverability proof を要求します。
  通常の cleanup は publication packet を作らず、proof が一致しないものは削除しません。
- candidate CAS、PR lifecycle、publication readback は任意の追加 evidence です。いずれかを
  渡す場合は candidate CAS と PR lifecycle を一組で渡し、publication readback を渡した merged
  state では strict publication readback、merge tree、`origin/main` containment を含む coherent
  transition を検証します。integration 後は canonical publication readback transition、merge
  commit/tree、`origin/main` containment を追加検証します。
- clone と topic root は同一 receipt で扱う。管理外 path へ退避しない。
- preflight が通った `--apply` だけが `CleanupProof` / cleanup receipt を返して computed
  clone と空の topic root を削除します。proof 不足、衝突、unknown dirty/staged/untracked
  state は typed hold として保持し、manual deletion へ迂回しません。

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
