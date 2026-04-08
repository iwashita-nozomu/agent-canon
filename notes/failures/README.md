# Failure Case Hub

このディレクトリは、再発防止のために残す failure case の置き場です。

## 使う場面

- 同じ topic で過去に失敗した試行を繰り返したくないとき
- worktree を閉じる前に、失敗の学びを `main` へ残したいとき
- benchmark、experiment、CI、Docker、workflow の失敗パターンを次回 kickoff で検索したいとき

## 各 note に最低限書くこと

- `Scope:` 何を試した失敗か
- `Failure Kind:` timeout、OOM、compile error、design dead-end など
- `Trigger:` どの条件で失敗したか
- `Why It Matters:` なぜ再発防止が必要か
- `Current Understanding:` 根本原因か、未確定仮説か
- `Safe Alternative:` 次回どう避けるか
- 関連する branch、worktree、note、result へのリンク

## ルール

- raw log や巨大 artifact はここへ直接置かず、result や report へ置いてここからリンクします。
- 「確認済みの failure」と「まだ仮説段階」を混ぜません。
- worktree を閉じる前に、次回も読む価値がある failure はここへ要約します。
- topic keyword で検索しやすい file 名を使います。

## Template

- [FAILURE_NOTE_TEMPLATE.md](/mnt/l/workspace/project_template/notes/failures/FAILURE_NOTE_TEMPLATE.md)
