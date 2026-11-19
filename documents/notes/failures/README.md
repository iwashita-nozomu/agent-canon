# Failure Case Hub
<!--
@dependency-start
contract reference
responsibility Documents Failure Case Hub for this repository.
upstream design ../README.md notes lifecycle index
@dependency-end
-->


このディレクトリは、再発防止のために残す failure case の置き場です。

## 使う場面

- 同じ topic で過去に失敗した試行を繰り返したくないとき
- worktree を閉じる前に、失敗の学びを `main` へ残したいとき
- benchmark、experiment、CI、Docker、workflow の失敗パターンを次回 kickoff で検索したいとき

## 記録する内容

観測結果、確認した原因、判断の根拠を記録します。再現情報は既存の検証結果や
実行記録を参照します。

## ルール

- raw log や巨大 artifact はここへ直接置かず、result や report へ置いてここからリンクします。
- 「確認済みの failure」と「まだ仮説段階」を混ぜません。
- worktree を閉じる前に、次回も読む価値がある failure はここへ要約します。
- topic keyword で検索しやすい file 名を使います。

## Template

- [FAILURE_NOTE_TEMPLATE.md](FAILURE_NOTE_TEMPLATE.md)
