<!--
@dependency-start
contract workflow
responsibility Defines the generic boundary between Git branch metadata and git-annex payload operations.
upstream design BRANCH_SCOPE.md owns branch and commit scope.
upstream design ../experiments/result-log-retention-and-visualization.md owns experiment result retention.
upstream design ../runtime/private-feedback-knowledge.md owns private feedback storage.
downstream design README.md exposes the operations reader route.
@dependency-end
-->

# git-annex を使う作業の境界

この文書は、Git の branch に記録される pointer/metadata と、git-annex が保持する
実体 (payload) を分けて扱うための共通の入口です。branch の命名・worktree・commit・
push は [BRANCH_SCOPE.md](BRANCH_SCOPE.md) が所有します。実験結果の保持は
[Result Log Retention And Visualization](../experiments/result-log-retention-and-visualization.md)、
private feedback は [Private feedback and knowledge](../runtime/private-feedback-knowledge.md)
の所有です。これらの所有者が指定しない annex 操作を、この文書から自動的に開始しません。

## Reader map

- branch、worktree、commit、push の判断: [BRANCH_SCOPE.md](BRANCH_SCOPE.md)。
- 実験結果の retention: [Result Log Retention And Visualization](../experiments/result-log-retention-and-visualization.md)。
- private feedback の外部保管: [Private feedback and knowledge](../runtime/private-feedback-knowledge.md)。
- result artifact の具体的な writeout: [result-artifact-writeout](../../agents/skills/result-artifact-writeout.md)。
- 上記に該当しない annex の pointer/payload 操作: この文書。

## 操作前に固定すること

1. 対象 repository/worktree、branch、対象 path、payload の所有者、使用する remote を
   固定します。repository 固有の branch/storage policy があれば、それをこの共通文書
   より先に読みます。新規 branch は repository の既存方針に従って選び、既存の互換
   branch や明示された PR branch を後から別名へ移しません。
2. 対象が pointer/metadata だけなのか、現在の payload の存在・転送・削除まで含むのかを
   明示します。Git branch を push したことは payload が remote に転送された証拠では
   ありません。
3. 操作の結果として変わるものを分けて記録します。Git の commit/ref と payload の
   transfer/local availability は別の readback で確認します。

## pointer と payload

git-annex が管理する path は、Git tree に symlink または pointer file を記録し、実体を
annex object store に保持します。pointer が存在しても、この checkout に payload がある
とは限りません。また、locked/unlocked は annex 管理から外れることを意味しません。

- locked path は通常の annex 表現です。
- unlocked path は編集用の表現で、pointer 自体は Git に記録され、実体は annex に残ります。
  unlock は表現変更と、設定によっては内容の copy を伴う書き込みです。必要な作業だけで
 使い、常に手動で lock へ戻すという blanket rule は置きません。
- pointer と object の対応、symlink、`.git/annex/objects/` の内容を手で編集しません。
  状態が不明・payload が見つからない場合は、推測で修復せず owner に返します。

git-annex の内部 metadata を持つ `git-annex` branch は、通常の作業 branch、`main`、
`source`、`results`、`archive` の merge 対象にしません。git-annex が管理する内部 tracking
ref なので、ref 更新や metadata 操作は native git-annex に委ねます。これは通常の Git 保守や
checkout 全般を禁止する規則ではありません。

## native operation の選び方

下表のコマンドは、owner が対象 path、remote、目的を指定したときだけ使います。引数を
省略した全体操作や `--force` による確認の迂回は、共通運用の既定にしません。

| 目的 | native operation | 書き込み・確認上の注意 |
| --- | --- | --- |
| path を annex 管理に入れる | `git annex add <path>` | pointer と annex metadata を作る。remote への転送ではない。 |
| この checkout に実体を得る | `git annex get <path>` | owner が許可した remote/config と exact path が必要。 |
| local から明示した remote へ実体を転送する | `git annex copy <path> --to=<remote>` | payload transfer と Git metadata の commit/push を別々に readback する。 |
| 明示した remote から local に実体を得る | `git annex copy <path> --from=<remote>` | payload transfer と Git metadata の commit/push を別々に readback する。 |
| 編集可能な表現にする | `git annex unlock <path>` | 表現変更を commit する書き込みで、copy による容量増加があり得る。 |
| commit、pull、push、内容同期をまとめて行う | `git annex sync` | read-only ではない。既定で local change を commit し、pull/push する。内容転送は設定・option に依存する。 |
| local payload を解放する | `git annex drop <path>` | native の安全な copy 検証に失敗したら保持する。`--force` で確認を迂回しない。 |

特に `git annex sync` を状態確認の代わりに実行しません。sync は commit と remote 更新を
伴い得るため、内容を同期するかどうかも設定や option に依存します。単なる調査には
read-only の status/info/whereis 等を使い、必要な場合だけその出力を記録します。

## failure semantics

- git-annex、remote、設定、または owner の許可が不足している場合は停止し、手動 copy や
  別の host 設定へ切り替えません。
- pointer はあるが payload がない場合は「metadata は存在、payload は未確認」として保持し、
  `get`/`copy` を自動実行しません。
- `drop` が必要な copy を検証できない場合は成功扱いにせず、payload を保持します。
- `sync` が成功しても、Git metadata の更新と payload transfer の成否を同一視しません。
- path が locked/unlocked のどちらであるかを、手動 symlink 編集や一律 lock/unlock の根拠に
  しません。native operation の readback と owner の retention policy を優先します。

この repository の既存 annex route を使う場合は、明示された `--annex-repo`、対象 result
directory、retention decision、checksum/readback をその route の owner に渡します。共通文書
はその CLI/API や archive policy を置き換えません。

## 参照

- [git-annex](https://git-annex.branchable.com/)
- [git-annex copy](https://git-annex.branchable.com/git-annex-copy/)
- [git-annex sync](https://git-annex.branchable.com/git-annex-sync/)
- [git-annex unlock](https://git-annex.branchable.com/git-annex-unlock/)
- [git-annex drop](https://git-annex.branchable.com/git-annex-drop/)
- [git-annex internals](https://git-annex.branchable.com/internals/)
