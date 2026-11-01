<!--
@dependency-start
contract workflow
responsibility Documents Branch Scope と Git ワークフロー for this repository.
upstream design README.md durable document index
upstream design ../../agents/canonical/CODEX_COMPLETION.md selected completion route
upstream design ../rule/repository-topic-clone.md checkout lifecycle and writer scope
downstream design ../../agents/canonical/CODEX_WORKFLOW.md consumes commit correctness closeout contract
downstream design ../../agents/skills/agent-canon-update.md consumes branch, commit, and PR scope split contract
downstream design ../../agents/skills/codex-task-workflow.md exposes commit correctness workflow guidance
downstream design ../../.codex/personal/skills/codex-task-workflow/SKILL.md exposes commit correctness runtime guidance
downstream design ../../agents/skills/pr-processing.md exposes PR merge scope review
downstream design ../../.codex/personal/skills/pr-processing/SKILL.md exposes PR merge scope review
downstream design ../rule/dependency-module-changes.md consumes workspace dependency checkout readback
@dependency-end
-->

# Branch Scope と Git ワークフロー


この文書は、branch 名、branch の責務、commit / push、merge / rebase の判断をまとめた正本です。
checkout の作成・再利用は [repository-topic clone ルール](../rule/repository-topic-clone.md)、
legacy scope / action log の carry-over は [worktree-lifecycle.md](worktree-lifecycle.md) を参照します。

## この文書の読み方

- この文書は、branch 名、branch scope、commit/push、merge/rebase、
  削除前チェックの Git workflow を定めます。
- 主な順路は、基本方針、branch 名、Scope の固定、コミット・プッシュ、
  Conflict 解決と merge / rebase、削除前チェックです。
- branch や PR の責務を固定する前、または merge 判断時に読みます。
- checkout lifecycle、legacy cleanup、task completion はそれぞれの正本に従い、
  この文書では branch / commit / PR の責務と Git 状態保全を扱います。

## 1. 基本方針

- 1 branch = 1 topic に固定します。
- topic は独立した設計単位として扱い、branch と PR の scope もこの単位に揃えます。
- branch の責務が広がったら、追加編集前に branch の分割または current handoff の
  write scope 更新を判断します。writer packet の更新は既存 checkout lifecycle に従います。
- 実装コードと長時間実験の生成物は、必要に応じて branch を分けます。
- `main` は統合先であり、試行錯誤や途中生成物の置き場にはしません。実験 repository では、再利用する
  model/helper、共有 execution・regression infrastructure、完了済み `summary.md` と
  archive reference を保持し、topic-only / disposable diagnostic code は置きません。
  この実験用の制限は通常の product code を `main` に置くことを禁じません。

### Experiment topic branch scope

作業前に、branch の起点（base ref と exact commit）、目的・研究課題、意図する差分を、
既存の branch README / plan / task record に固定します。最初の起点は保持し、main 更新後の
比較基準は別に記録します。進行・handoff・再開でもこの文脈を引き継ぎ、実際の diff と
evidence を目的に照合します。既知の合意で進められる事項は再確認せず、未決の重大な方向変更
だけを利用者へ確認します。このための新しい manifest、schema、専用台帳は作りません。

実験 branch の code/config はその topic に限り、完了済み別 topic の code を持ち込みません。
論文と選択済み report の完成は研究実験 branch の完了に含めます。
project の既存 manuscript owner/path に、単独で読める
arXiv 水準の論文原稿 source を保持します。実際の研究課題、関連研究、方法、根拠・結果、
限界、再現手順を揃え、未観測・未検証の内容はそのまま区別します。既存原稿を更新し、
各 run ごとの新規論文や arXiv 投稿を要求しません。
report の構成・図・執筆手順は [report-writing](../../agents/skills/report-writing.md)、
論文の執筆は [paper-writing](../../agents/skills/paper-writing.md) の既存 owner に従います。

`main` には簡潔な完了済み `summary.md` と、論文・結果・archive の安定した参照を残します。
topic code や branch の削除前に、原稿 source と参照先が保持され、取得できることを確認します。
閉じた verification / diagnosis は active experiment と別の scope として扱います。
raw log、archive、summary の扱いは
[Result Log Retention And Visualization](../experiments/result-log-retention-and-visualization.md#experiment-archive-and-summary-retention)
に従います。

### Git 状態の保全と整合性

「知らない差分」「自分の変更ではない」「別途指示されていない」は、Git の
不整合を調べず放置する理由になりません。既存状態を保護しながら、担当作業に
必要な整合性を保つことは作業の一部です。差分の所有者と、Git 状態を確認して
安全に継続・修復・引継ぎする責務を混同しません。

整合性は clean と同義ではありません。staged / unstaged / untracked の既存差分や
pin 用の detached HEAD は、それだけでは異常ではありません。一方、競合 marker
や unmerged index がなくても、merge 等の操作が完了したとは限りません。

1. 開始・再開、Git 状態変更後、publication / handoff の既存確認境界で、対象
   checkout の branch / HEAD、staged / unstaged / untracked、未解決 index、
   merge / rebase / cherry-pick / revert / am 等の途中状態を読みます。
   `git status`、`git diff`、`git diff --cached`、`git ls-files --unmerged` を使い、
   必要な差分と既存の Issue / PR / 作業記録から由来と今回の影響を確認します。
   operation の管理 path は `git rev-parse --git-path <name>` で解決し、linked
   worktree の `.git` を通常 directory と決めつけません。未知を健全と推定せず、
   関係と処置を判断できたところで調査を止めます。通常 command ごとの再走査、
   全 repository の監査、新しい checker / 台帳は要求しません。
2. 既存差分は task-owned、他者・別作業、由来未確認を区別し、内容と stage 状態、
   未公開 commit / ref を無断で失わせたり今回の提出へ混入させたりしません。
   同じ file の混在 hunk も対象です。clean に見せるための reset / restore /
   clean / stash、`git add -A`、一括 commit、force push、管理 file / lock の
   手動削除は禁止です。必要な操作自体の権限は既存 owner に従います。
3. 自分の操作で生じた不整合、または由来・正しい復旧先・権限が確認できた担当
   範囲の不整合は、既存 Git / integration owner で修復して読み戻します。
   追加の指示待ちにしません。継続中の別 writer があれば同じ状態へ書き重ねず、
   既存の協調 owner へ戻します。未知の変更の採否、他者の途中操作の continue /
   abort、履歴の巻戻しを推測で行いません。安全に分離できる独立作業は既存
   checkout owner で続け、元 checkout の未解決状態を分離先の clean で隠しません。
4. commit / push / PR / handoff の前に、保持対象と実際の残差分、対象 branch、
   自分が開始した Git 操作の終了、提出する index / commit tree と検証対象、
   公開した場合の remote head / PR head を照合します。自分が開始した途中操作を
   残して通常完了としません。最新 main の取込み・競合解決は既存の開始時・PR前
   の手順に従い、履歴だけを合わせた疑似 merge にしません。意図的な local-only /
   未 push 状態は区別し、全 ref の同期や無関係な変更の commit は要求しません。

残った各差分・途中状態には、確認済みで保持する理由、修復結果、または未解決の
引継ぎに必要な事実を現在の会話で伝えます。修復できない場合は、repository /
path / branch / HEAD、観測した状態、実在する保全先、影響して止めた操作、欠けた
権限・判断・環境、次の owner / action を明記します。owner が未確認ならその旨と
確認先を伝えます。説明だけで修復済みとは扱わず、影響しない作業まで停止しません。
GitHub 上の readback は利用者の未観測の local checkout の健全性を証明しません。

保持対象を勝手に変えないことと、認可された操作を完結させることの両方が必要です。
単なる差分ゼロ判定では前者を、記録して放置するだけでは後者を保証できません。
Git 状態維持を理由に、無関係な製品修正・全 branch 掃除・他 Issue の完了まで
終了条件に広げません。実際の競合解決・checkout 分離・削除は既存 owner に委譲し、
この節は新しい mutation 権限や Git 実装を作りません。

## 2. branch 名

- 通常の実装 branch の命名は `work/<topic>-YYYYMMDD` を基本とし、選択した owner の
  命名条件を優先します。AgentCanon source 変更は
  [agent-canon-update](../../agents/skills/agent-canon-update.md) の Issue-qualified topic branch を使います。
- 結果保存 branch は `results/<topic>` を使います。
- branch 名は目的が読める英語句で付けます。

Git branch の metadata と大容量 payload を annex で扱う場合は、操作前に repository 固有の
branch/storage owner と対象 path・remote を固定します。pointer/metadata の commit・push は
payload の転送証明ではありません。locked/unlocked、payload の有無、内容の transfer/drop は
別の状態として readback し、共通の操作境界は [annex.md](annex.md) に従います。実験結果や
private feedback の archive は、それぞれの owner 文書に従い、branch workflow と混ぜません。

## 3. Scope の固定

- current handoff に branch の目的、dependency-expanded write scope、必要な carry-over 先を
  固定します。分離が必要な場合の mode・配置・writer packet は
  [checkout lifecycle](../rule/repository-topic-clone.md#clone-ライフサイクル) に従います。
- `WORKTREE_SCOPE.md` は新しい task の権限源にしません。既存 file の扱いは
  [legacy scope の確認](worktree-lifecycle.md#legacy-scope-の確認) に従います。
- branch で experiment topic を継続的に触る場合は、`experiments/registry.toml` の
  `active_branch` を更新します。既存の `scope_file` は legacy evidence として扱います。
- branch の入口が必要な場合は `documents/notes/branches/<branch_topic>.md` に置き、scope と関連 note をそこから辿れるようにします。

### Workspace と依存 checkout の確認

作業開始・再開、checkout の変更、integration、実行・検証、publication / handoff の
既存の branch 確認境界では、対象 repository だけでなく、作業 workspace 内の
依存クローンも確認します。確認対象の発見は `workspace/<...>` の実在内容から
行い、既存の `workspace/<repo>` や canonical な `workspace/<topic>/<repo>` を
親の `.gitignore` や親だけの `git status` を理由に除外しません。これは既存
checkout の観測であり、新規作成時の canonical 配置を変更する規定ではありません。

依存宣言と実際の build / import / 実行時の解決先を辿り、対象となる Git root を
確定します。`.git` directory だけでなく `.git` file を持つ worktree / submodule、
local path override、workspace 外に解決される使用中の clone も取り落としません。
同じ repository の複数 clone は path ごとに区別します。無関係と確認できた
workspace の repository は更新対象にせず、全 toolchain の無制限走査も要求しません。

対象に必要な次の事実を現在の context で確認します。観測結果を管理する台帳や
`checkout_identity` schema は追加しません。

| 観測 | 確認内容 |
| --- | --- |
| clone identity | resolved path、Git root、remote の owner/repository、branch または detached、actual `HEAD` の full SHA |
| local state | staged / unstaged / untracked の有無と、今回の入力に関係する差分。親 repository の状態で代用しない |
| 宣言した依存 | 選択した consumer tree / index の gitlink、manifest / lock 等の依存宣言（pin があればその値）、その所有 path、対応する依存 PR と採用 SHA（変更時） |
| 実際の入力 | build / import / 実行設定が読む checkout path と SHA、local override の有無。cache / install / 生成物を読む場合は宣言した依存由来であること |

依存の source 開発 clone と、consumer が読む checkout は別々に扱います。
開発 clone の新しい HEAD だけを見て consumer の更新済みとは判断せず、consumer が
pin を持つ場合はその入力を宣言 pin と照合します。pin 用の clean detached checkout
は正常であり、branch attach や全依存の最新 main 化を要求しません。依存側の修正に
着手する場合は、その repository の最新 main 起点、または関連 Issue の active branch
を使い、branch 名には対応する Issue 番号を含めます。未知の dirty state は保持します。

依存変更を要する実行で、consumer の既存契約が exact pin を要求する場合は
[依存モジュール変更規約](../rule/dependency-module-changes.md) の PR → exact pin →
consumer 実行の順序に従います。pin と実際の入力が不一致、dirty な依存入力、
または由来を確認できない場合は、その入力を使う実行・検証を止め、具体的な
path / SHA / 未確認事項を残します。黙って branch を切り替えたり、reset / clean /
stash、別 clone や cache で不一致を隠したりしません。依存しない作業まで止めません。
pin を要求しない consumer には既存の依存宣言と解決機構を使い、実際の入力を
記録します。この手順を満たすための pin や SHA 一致 guard は新設しません。

directory、branch、HEAD、依存 PR の revision、pin、local override / mount 等の
入力解決先が変わったら、影響する対象を次の操作前に再確認します。同じ境界の
観測を共有でき、状態が変わっていない通常 command ごとの重複確認は不要です。

## 4. コミット・プッシュ

- commit は branch の責務に収まる差分だけを含めます。
- 公開・統合が認可された作業は、小さく一貫した独立検証可能な単位ごとに、変更保証に
  必要な検証、commit、push、既存の受入条件を満たす merge と readback を完了して次へ進みます。
  必要な依存を含む atomic unit と既存の構造変更 merge 要件を保ち、無関係な並行単位の
  完了を待たずに届けます。

### 範囲分割契約

コミットは意味のある差分、PR は一つの変更意図をレビューできる範囲で区切ります。
修正方針、必要な利用側の変更、旧実装の削除は編集前に現在の会話で確認します。
範囲表、単位/SHA表、commit別の検証表、作業台帳の作成・更新は要求しません。

AgentCanon source と parent project の tracked changes は、それぞれの責務と
公開先に従って別の commit / PR で扱います。

### 依存から決めるコミット計画

1. 変更する契約と完成状態を起点に、実装、必要な呼出元、公開登録、設定、生成物、
   テスト・文書の変更範囲を確認します。無関係な調査は加えません。
2. 必要な API、既存機能、宣言済みの依存と取得経路を確認し、何をどう修正・削除するか
   を決めます。利用側と提供側を一緒に変える必要があれば同じ変更単位にまとめます。
3. 決めた単位を依存順に実装します。小さな commit のための互換層、一時 API、
   検証用の仮実装は追加しません。
4. 移行先と利用側の変更を揃え、旧実装・参照・専用補助の削除漏れを見直します。
5. 完成した移行の最終状態をまとめて検証します。中間の編集や commit ごとの
   build / test / smoke、個別の検証記録は要求しません。

### Commit Correctness Contract

検証結果は、実際に確認した最終 source と入力に対する結果として扱います。
最終 HEAD の成功を未検証の中間 commit の成功とは説明しません。
各中間 tree の実行証跡を揃えるための再実行や履歴の作り直しは不要です。

- 変更契約に必要な build / test / smoke と文書チェックを、移行と削除確認の後に
  まとめて実行します。結果、未実施、失敗を区別して報告します。
- 検証に必要な source、設定、schema、fixture、生成手順は提出する変更と
  宣言済みの依存に揃えます。作業用 checkout だけにある入力へ依存させません。
- 検証後に実装や競合解消で内容が変わった場合は、その変更が影響する検証を
  最終状態で行います。SHA の変化だけを理由に検証を繰り返しません。
- PR の公開・取り込みでは最新 main と実際に統合し、完成した差分と remote の
  source を確認します。未知のユーザー状態は reset / clean / stash で失わせません。
- commit別の依存調査報告、関数一覧、証跡表、進捗記録を通常作業へ追加しません。
- 初回 push と PR 作成は `python3 tools/repository/github/github_publish.py publish-pr --user-task "<current user task>" --repo <owner/name> --title "<title>" --body-file <body.md>` を使います。branch push だけなら `github_publish.py push` を使います。
- 選択した commit / push の実行結果は会話で報告します。実行していない操作や
  未確認の内容を完了とは説明しません。
- 共有・引継ぎ・PR 公開が既存の権限と目的に含まれる場合は、追加の許可取りへ
  戻らず進めます。push 失敗時は commit を保持し、失敗した操作と次の対応を報告します。

## 5. Conflict 解決と merge / rebase

- `main` 取り込みは、branch の目的に必要な最小限に留めます。
- ローカル履歴整理の `rebase` は既存 owner が認可された route で判断します。
  repository-topic writer は raw `git merge` / `git rebase` を実行せず、最新 main の取込みを
  [merge-main / finalize-merge](../rule/repository-topic-clone.md#clone-ライフサイクル) の integration executor へ渡します。
- 統合時の安全性と文脈保持を優先する場合は `merge` を選びます。
- 意図的に削除・置換したファイルの modify/delete 競合は削除を採用します。旧 branch の
  編集に必要な変更があれば移行先へ反映し、旧ファイルを復活させません。
- 別 branch と同じファイルを触っている場合は、現在の会話で衝突箇所を確認します。
  過去の branch / worktree note は必要な場合だけ参照します。
- file 追加、削除、rename、symlink 化、type 変更、ディレクトリ再編がある branch は、[agents/skills/integration.md](../../agents/skills/integration.md) の手順で統合します。
- 構成変更がある branch は、`main` 側で file 単位に拾い直して close してはいけません。
  統合後は削除したファイルと旧呼び出しが復活していないことを確認します。
- 以下は source branch を base へ統合する integration owner の手順です。
  topic branch への最新 main 取込みとは区別し、writer の raw Git mutation 権限を追加しません。
- 構成変更がある統合では、current checkout 上の integration branch で merge commit を作り、`tools/bin/agent-canon check-merge-structure --source <branch> --target origin/main --compare-commit HEAD` を通します。
- integration branch が妥当なら、`main` へは `git merge --ff-only integrate/<topic>-YYYYMMDD` で持ち帰ります。

## 6. 削除前チェック

作業用 checkout の利用終了時は [checkout cleanup](../rule/repository-topic-clone.md#クリーンアップ)、
legacy branch / worktree の削除判断は [legacy cleanup](worktree-lifecycle.md#cleanup-前の確認) に従います。
branch の目的、持ち帰る知見・結果と保存先を既存 task / Issue / note から辿れるようにし、
削除対象の exact ref/path を確認します。checkout の回収と branch の削除は別の authority です。
