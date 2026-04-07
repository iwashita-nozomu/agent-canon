# Engineering Avoidances

この note は、repo-wide に何度も読み返す avoid list を短く固定します。

## Avoid

- 正本を更新せずに runtime entrypoint だけ直す
- host-global install を repo の正本手順にする
- partial run を正式結果として扱う
- worktree scope を更新せずに編集範囲を広げる
- raw 結果だけ残して、読み方や判断を note / report に落とさない
- `notes/` に置くべき一時メモを `documents/` へ混ぜる
- validation を飛ばして commit / push だけ進める

## When To Re-Read

- 新しい worktree を切った直後
- Docker、CI、dependency を更新する前
- 実験 loop を閉じる前
- repo-wide な workflow 整理を始める前
