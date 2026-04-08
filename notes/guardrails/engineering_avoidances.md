# Engineering Avoidances

この note は、repo-wide に何度も読み返す avoid list を短く固定します。

## Avoid

- 会話だけを根拠に実装、設計変更、文書改訂へ進める
- `documents/`、`notes/`、`references/` の context sweep をせずに着手する
- `python/`、`tests/`、`src/`、`include/`、`lib/`、`scripts/` の reuse sweep をせずに新しい file や module を増やす
- 最初の update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言しない
- repo-changing task で run bundle と explicit stage activation を省略する
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` を同じ instance で兼務する
- 学術文章で `notation_definition_reviewer` や `logic_gap_reviewer` を立てずに author 自己判断だけで閉じる
- review feedback を反映せずに次段へ handoff する
- 正本を更新せずに runtime entrypoint だけ直す
- host-global install を repo の正本手順にする
- partial run を正式結果として扱う
- worktree scope を更新せずに編集範囲を広げる
- raw 結果だけ残して、読み方や判断を note / report に落とさない
- `notes/` に置くべき一時メモを `documents/` へ混ぜる
- validation を飛ばして commit / push だけ進める
- required review、validation、commit / push を省略して完了扱いにする

## When To Re-Read

- 新しい worktree を切った直後
- Docker、CI、dependency を更新する前
- 実験 loop を閉じる前
- repo-wide な workflow 整理を始める前
