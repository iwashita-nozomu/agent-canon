<!--
@dependency-start
contract workflow
responsibility Documents Branch Scope と Git ワークフロー for this repository.
upstream design README.md durable document index
downstream design ../../agents/canonical/CODEX_WORKFLOW.md consumes commit correctness closeout contract
downstream design ../../agents/skills/agent-canon-update.md consumes branch, commit, and PR scope split contract
downstream design ../../agents/skills/codex-task-workflow.md exposes commit correctness workflow guidance
downstream design ../../.codex/personal/skills/codex-task-workflow/SKILL.md exposes commit correctness runtime guidance
downstream design ../../agents/skills/pr-processing.md exposes PR merge scope review
downstream design ../../.codex/personal/skills/pr-processing/SKILL.md exposes PR merge scope review
@dependency-end
-->

# Branch Scope と Git ワークフロー


この文書は、branch 名、branch の責務、commit / push、merge / rebase の判断をまとめた正本です。
worktree の作成と carry-over の流れは [worktree-lifecycle.md](worktree-lifecycle.md) を参照します。

## この文書の読み方

- この文書は、branch 名、branch scope、commit/push、merge/rebase、
  削除前チェックの Git workflow を定めます。
- 主な順路は、基本方針、branch 名、Scope の固定、コミット・プッシュ、
  Conflict 解決と merge / rebase、削除前チェックです。
- branch や PR の責務を固定する前、または merge 判断時に読みます。
- 境界: worktree 作成と carry-over の詳細は [worktree-lifecycle.md](worktree-lifecycle.md) が扱います。

## 1. 基本方針

- 1 branch = 1 topic に固定します。
- topic は独立した設計単位として扱い、branch と PR の scope もこの単位に揃えます。
- branch の責務が広がったら、branch を分けるか `WORKTREE_SCOPE.md` を更新します。
- 実装コードと長時間実験の生成物は、必要に応じて branch を分けます。
- `main` は統合先であり、試行錯誤や途中生成物の置き場にはしません。

## 2. branch 名

- 通常の実装 branch は `work/<topic>-YYYYMMDD` を使います。
- 結果保存 branch は `results/<topic>` を使います。
- branch 名は目的が読める英語句で付けます。

## 3. Scope の固定

- branch を切ったら、必要に応じて対応する worktree root に `WORKTREE_SCOPE.md` を置きます。
  parent/same-repository branch の分離は `repository-topic-clone` の `linked-worktree`、
  dependency repository は `independent-clone` を使い、配置は常に
  `<anchor>/workspace/<topic>/<repo>` とします。
- `WORKTREE_SCOPE.md` には editable directories、carry-over target、action log を明記します。
- branch で experiment topic を継続的に触る場合は、`experiments/registry.toml` の `active_branch` と必要なら `scope_file` を更新します。
- branch の入口が必要な場合は `documents/notes/branches/<branch_topic>.md` に置き、scope と関連 note をそこから辿れるようにします。

## 4. コミット・プッシュ

- commit は branch の責務に収まる差分だけを含めます。

### 範囲分割契約

コミット範囲と PR 範囲は別々のレビュー単位として扱います。

- コミットは Git 上で再実行できる実行単位です。
- PR はレビュー担当者が一つの問題、設計意図、正本 owner、振る舞いまたは
  契約の差分、根拠経路として受け入れられるレビュー単位です。
- commit または PR 作成 / 更新へ進む前に、差分が複数の問題、canonical
  owner、behavior or contract delta、validation route にまたがる場合は、
  run bundle または PR body に範囲表を置きます。範囲表には差分単位、
  目的、canonical owner、編集 path、validation route、依存する差分単位を
  書きます。
- 複数の差分単位を一つの PR に載せる判断は、同じ設計意図と同じレビュー判断で
  扱える場合に限ります。独立して main に入れられる差分単位は、merge 前に別
  PR または別 commit に分けます。
- AgentCanon source 変更と parent project の tracked changes は、source merge/readback
  後も別 PR / commit として分けます。親には submodule pin や root view を作りません。

### 依存から決めるコミット計画

編集前に、今回提出するコミット列の目的、保持する契約、必要な依存、検証方法を
既存の Issue、PR body、または作業記録に固定します。直近の作業、編集順、担当者、
ファイル数や種類だけでは分割しません。単一の変更単位なら短い記述で足り、
専用の台帳、依存 DB、新しい checker は作りません。

1. 変更する契約を起点に、必要な依存を推移的に辿ります。import / call-site だけで
   なく、未変更の呼出元、公開登録、schema、設定、dependency manifest / lock、
   build / packaging、生成元と tracked 生成物、fixture、運用文書も、変更が
   影響する範囲で確認します。既存の言語 tool、依存宣言、検証経路を使い、
   changed files の一覧や過去の作業要約だけで依存が閉じたとは判断しません。
2. 各前提を、base / 祖先で充足、先行 commit で提供、同一 commit に包含、
   固定済み external input、未解決のいずれかに分類します。外部依存は既存の
   lock、commit、artifact / image digest 等で必要な identity と取得経路を
   確定します。取得する SHA 等が未固定の別 branch の変更、将来の PR、可変な
   latest、偶然の local install / cache を充足済みの前提にしません。
3. 先行変更を必要とする関係を順序付けします。同時に変えないと契約が壊れる
   変更群は一つの commit にまとめます。変更単位間の依存 graph に循環が
   あれば、その強連結成分を一単位に畳むか、各段階で契約が成立する設計へ
   改めます。単に同じファイルを触ることは、同時変更の根拠になりません。
4. 各単位の目的、owner、編集範囲、前提、維持する既存動作、検証 command と
   期待結果を確定してから編集します。未知の必須依存が残る単位は着手可能に
   せず、その依存の調査または owner への引継ぎを先に行います。独立して
   成立する単位まで止めず、無関係な Issue や改善を終了条件へ取り込みません。
5. 新しい依存や consumer が判明したら、次の編集・commit の前に影響する単位の
   範囲と順序を更新します。小さく見せるために必要な追従を後続 commit へ
   先送りしたり、分割のためだけの仮実装や互換層を追加したりしません。

複数単位では、既存の範囲表に次の列を加え、検証後に SHA と結果を埋めます。

| 単位 / SHA | 目的・保持する契約 / owner / path | 前提単位・外部依存 identity | 検証 command・期待結果・実測結果 |
| --- | --- | --- | --- |
| 計画時の単位 ID、確定後の SHA | 変更と既存 consumer への影響 | base、先行 / 同一単位、固定入力、未解決 | 対象 tree ごとの結果または未実施理由 |

例えば、既存 API を保つ新 API とそのテストを先に追加し、次に利用側を移行し、
参照がなくなってから旧 API を削除する分割は、各段階を検証できる場合に成立します。
一方、互換性のない signature / schema の変更と必要な呼出元・設定・テストの
追従は、片側だけでは壊れるなら同一 commit です。生成元と tracked 生成物も
同期が契約なら同一 commit にします。既知の失敗テストだけを先に提出し、後続の
実装で直す履歴は完成したコミット列として扱いません。

### Commit Correctness Contract

各 commit は、その祖先を含む tracked tree と固定済みの外部入力から、必要な
動作と選択済み validation が成立する単位です。後続 commit や作業中の tree で
成功しても、その commit の成功とはみなしません。任意の base へ単独で
cherry-pick できることまでは要求しません。

提出する各 commit の tree を `T_i`、宣言した外部入力を `E_i` とすると、
要求は最終 `T_n` だけでなく全ての `i` について次が成立することです。

```text
required_inputs(T_i) are available in T_i or fixed E_i
selected_validation(T_i, E_i) = pass
```

検証経路は変更契約と影響を受ける既存 consumer から選びます。runtime behavior を
変える場合は必要な build / test / smoke を含め、静的確認だけで動作を証明したとは
扱いません。文書・規約だけの変更では対応する文書・参照整合性の確認を使い、
全 commit への無関係な全 suite 実行は要求しません。

- 最終 HEAD だけでなく、提出する各 commit の正確な tree を検証します。
  staging 後の候補を先に検証する場合も、後で確定した commit の tree と一致する
  ことを読み戻します。差分が混在した working tree での成功は代用できません。
- 既存の Git safety / worktree owner に従い、隔離した checkout または候補 tree
  から、その時点の設定・lock・生成手順で検証します。作業用 tree にしかない
  未 commit / untracked source、後続 commit の fixture、由来不明の生成物に
  依存させません。tracked な生成手順と固定入力からの再生成は認めます。
  既存の user-owned tree を reset / clean / stash で変えず、検証出力は許可された
  ignored / external 領域へ出し、tracked tree が不変であることを確認します。
- 分割、並べ替え、squash、rebase、競合解決で tree / 依存 / 検証条件が変わった
  commit は再検証します。SHA だけ変わり tree と全入力が同一なら、その一致を
  示して既存証跡を対応付け直せます。PR 前には最新 main を読み直して取り込み、
  競合を解決し、統合済み HEAD の検証と remote readback を行います。
- 失敗した単位は境界を組み直すか同じ契約を保って修正します。環境不足や
  baseline の既存失敗は、対象 commit・失敗箇所・依存 owner・未確認の性質を
  記録し、pass に読み替えません。無関係な既存障害は別責務のまま残し、
  検証不能なら `need verification` として、検証済み完了とは区別します。

- commit は Git 上の runnable unit です。`git checkout <commit>` で得られる tracked tree と、明示された external runtime/source clone だけで、選択した validation route が再実行できる状態にします。
- validation が読んだ source、config、schema、fixture、文書、tool entrypoint は、その commit の tracked tree に含めます。ignored / generated runtime output は artifact、cache、log、result のどれかに分類して evidence に残します。
- code 変更では、file-level の code dependency scan と、言語 tool が対応する関数 / public entrypoint 単位の call-site evidence を commit evidence に含めます。Python では `python3 tools/analysis/code/helper_function_inventory.py --changed --all-functions --format json` を関数単位 evidence に使います。
- commit evidence には branch、commit SHA / tree、前提 commit と外部依存 identity、source clone SHA/PR readback（該当時）、validation command・対象 path・終了結果、残った dirty / untracked path の分類を含めます。
- `WORKTREE_SCOPE.md` を更新した場合は、早い段階で commit します。
- push 前に、その branch で必須の test / lint / document check を実行します。
- 初回 push と PR 作成は `python3 tools/repository/github/github_publish.py publish-pr --user-task "<current user task>" --repo <owner/name> --title "<title>" --body-file <body.md>` を使います。branch push だけなら `github_publish.py push` を使います。
- user-facing の完了報告は、今回の scope で選択した commit / push の判断と結果を既存の closeout evidence に反映してから行います。選択しなかった操作を無条件に作成・実行する完了条件にはしません。
- さらに `verification.txt` が `status=pass`、`closeout_gate.md` が `auditor_status=resolved`、`review_convergence_complete=yes`、`diff_check_agent_complete=yes`、`user_completion_report=unlocked` になり、run-local diff-check artifact が現在 tracked diff ref の read-only independent approval を示すまで完了報告を出しません。
- commit / push を選択しない task は、review-only、read-only、no-change、local-only / no-push、または user が明示的に停止した場合として、既存の closeout status を `not_applicable` にし、既存の work log / final status に判断理由を残します。選択した操作の status は `yes` になるまで完了扱いにしません。
- commit / push が sharing、handoff、remote backup、PR などの目的と既存権限・指定宛先から適切と判断できる task では、agent は追加の許可取りに戻らず実行します。
- 選択した push に失敗した場合は、完了扱いにせず、commit を保持したまま branch、commit、`github_publish.py` の `NEXT_ACTION` と失敗理由を明記して報告します。literal URL push や remote 推測の alternate route は使いません。

## 5. Conflict 解決と merge / rebase

- `main` 取り込みは、branch の目的に必要な最小限に留めます。
- 履歴を読みやすく保つため、ローカル整理には `rebase` を使って構いません。
- 統合時の安全性と文脈保持を優先する場合は `merge` を選びます。
- 別 branch と同じファイルを触っている場合は、先に `documents/notes/branches/` と `documents/notes/worktrees/` で衝突リスクを明示します。
- file 追加、削除、rename、symlink 化、type 変更、ディレクトリ再編がある branch は、[agents/skills/integration.md](../../agents/skills/integration.md) の手順で統合します。
- 構成変更がある branch は、`main` 側で file 単位に拾い直して close してはいけません。
- 構成変更がある統合では、current checkout 上の integration branch で merge commit を作り、`python3 tools/validation/ci/checks/check_merge_structure.py --source <branch> --target origin/main --compare-commit HEAD` を通します。
- integration branch が妥当なら、`main` へは `git merge --ff-only integrate/<topic>-YYYYMMDD` で持ち帰ります。

## 6. 削除前チェック

- branch の目的が `documents/notes/branches/` から辿れる
- `main` に持ち帰る note / final JSON が整理済み
- raw 結果を残す場所が決まっている
- `git worktree list` と `git branch -v` で後片付け対象が分かる
