# Engineering Avoidances

この note は、repo-wide に何度も読み返す avoid list を短く固定します。

## Avoid

- 会話だけを根拠に実装、設計変更、文書改訂へ進める
- `documents/`、`notes/`、`references/` の context sweep をせずに着手する
- `python/`、`tests/`、`src/`、`include/`、`lib/`、`tools/`、`scripts/` の reuse sweep をせずに新しい file や module を増やす
- 最初の update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言しない
- repo-changing task で run bundle と explicit stage activation を省略する
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` を同じ instance で兼務する
- 学術文章で `notation_definition_reviewer` や `logic_gap_reviewer` を立てずに author 自己判断だけで閉じる
- review feedback を反映せずに次段へ handoff する
- 正本を更新せずに runtime entrypoint だけ直す
- host-global install を repo の正本手順にする
- agent helper、CI、review、validation、container runner、experiment helper を root `scripts/` に置く
- partial run を正式結果として扱う
- spot run、debug run、smoke run を比較表、method 採否、正式 report、review evidence に使う
- correctness evidence と performance evidence を混同する
- raw failure count だけを見て、environment noise、case mix、failure kind を分離せずに解釈する
- success case だけを集計して、failure case、worst case、trade-off を落とす
- ordered difficulty 軸を飛び飛びに測って frontier や failure onset を結論する
- code change、protocol change、XLA / runtime flag change を 1 つの iteration に混ぜる
- 実験 script 側で runner、scheduler、GPU slot 管理、timeout cleanup、pid registry、monitoring loop を重複実装する
- 実験 script 側で `CUDA_VISIBLE_DEVICES`、`JAX_PLATFORMS`、`XLA_*` を場当たり的に組み立てる
- protocol にない ad hoc output path、手作業 rename、partial-run resume protocol を増やす
- user request が generic path の usable smoke を求めているのに、specialized path の tuning だけで完了扱いにする
- scope で禁止された runner 変更、function fusion、別経路追加を、性能改善のために横滑りで入れる
- user request clause にない実装 slice を「ついで」として入れる
- worktree scope を更新せずに編集範囲を広げる
- raw 結果だけ残して、読み方や判断を note / report に落とさない
- `notes/` に置くべき一時メモを `documents/` へ混ぜる
- validation を飛ばして commit / push だけ進める
- required review、validation、commit / push を省略して完了扱いにする

## Source

- 2026-04-10 に `/mnt/git/agent-canon.git`、`/mnt/git/experiment_runner.git`、`/mnt/git/jax_util.git`、`/mnt/git/server_develop.git`、`/mnt/git/template.git` と対応する `/mnt/l/workspace/*` の `documents/`、`notes/`、worktree logs を検索して抽出しました。

## When To Re-Read

- 新しい worktree を切った直後
- Docker、CI、dependency を更新する前
- 実験 loop を閉じる前
- repo-wide な workflow 整理を始める前
