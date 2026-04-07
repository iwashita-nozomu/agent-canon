# Experiment Operations

## 保存

- 長時間 run は JSONL などの逐次保存を前提にします。
- final summary だけに頼りません。
- timeout、signal 終了、completion 欠落も parent 側で診断できる形にします。

## ケース順

- case ordering は実験設計の一部です。
- 途中停止しても何が読めるかを先に考えます。

## `main` への持ち帰り

- raw JSONL は隔離場所に残します。
- `main` には再集計できる final JSON を持ち帰ります。
- note には source JSON と archived JSON の両方を辿れるようにします。
- 外向けに残したい図は `notes/assets/` にコピーします。
- reusable runtime は共通実装側に残し、topic 固有ロジックは `experiments/<topic>/` に残します。

## worktree の後始末

- 削除前に `notes/worktrees/` へ要約を吸い出します。
- 少なくとも用途、主要結果、分かったこと、次の案を書きます。
- 過去の note 本文は書き換えず、補足が必要な場合は追記で補います。

## 監視

- `nvidia-smi`
- `ps` / `pgrep`
- JSONL の行数
- `failure_kind`
- メモリ使用量
- 中断後の child 残骸

## よくある失敗

- partial run を正式結果として扱う
- final JSON を `main` に持ち帰らず、あとで図や集計を再生成できなくなる
- case ordering のせいで比較に必要な条件がほとんど残らない
- parent を止めたあと child worker を回収せず、次の run を汚す
- 実験コード側で env と process lifecycle を抱え込みすぎる

## 運用チェックリスト

- `scripts/setup_worktree.sh` で作られた `WORKTREE_SCOPE.md` を埋める
- `notes/worktrees/worktree_<topic>_YYYY-MM-DD.md` を action log の正本にする
- 実装を `main` に取り込む前に関連テストを実行する
- ドキュメント更新はコード変更と同時に持ち帰る
- 中断した長時間 run を再開する前に、`ps` と `nvidia-smi` で child の残骸がないことを確認する

## 関連

- [Benchmark vs Experiment](./benchmark_vs_experiment.md)
- [../../documents/coding-conventions-experiments.md](../../documents/coding-conventions-experiments.md)
