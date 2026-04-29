# Experiment Registry
<!--
@dependency-start
upstream design README.md durable document index
downstream implementation ../tools/ci/check_experiment_registry.py validates registry schema
@dependency-end
-->


この文書は、`experiments/registry.toml` を使って experiment topic を集中管理する契約を定めます。
server 上でどの実験コードを正式に実行するかを、topic ごとに 1 か所へ固定するのが目的です。

## 役割

- experiment topic の正本 entrypoint を固定する
- smoke / formal run の canonical inner command を固定する
- `result/` と `report/` の正本 path を固定する
- branch / worktree と実験 topic の対応を補助 metadata として残す

branch 名は補助情報です。主キーにはしません。
durable な正本は常に topic 名です。

## 正本ファイル

- `experiments/registry.toml`

この file では、少なくとも次を topic ごとに持ちます。

- `name`
- `status`
- `topic_dir`
- `topic_readme`
- `canonical_entrypoint`
- `result_root`
- `report_root`
- `default_variant`
- `smoke_inner_command`
- `formal_inner_command`
- 必要なら `required_eval_artifacts`
- 必要なら `optional_eval_artifacts`

## branch-only topics

main に実験実装を残さず、隔離 branch だけで保持する実験は
`[[branch_topics]]` に登録します。

`[[branch_topics]]` は branch 管理用の index であり、main tree 上に
`topic_dir` や `canonical_entrypoint` を要求しません。main に残すのは、
実験名、保存 branch、主要 note、必要なら branch 内 entrypoint や result root
だけです。これにより、main は実験 framework と registry だけを持ち、
branch 固有の探索コード、notebook、生成結果を持ちません。

少なくとも次を持ちます。

- `name`
- `status`
- `remote_branch`
- `primary_note`
- 必要なら `source_commit`
- 必要なら `branch_note`
- 必要なら `branch_entrypoint`
- 必要なら `result_root`

## branch / worktree metadata

必要な場合だけ次を持てます。

- `active_branch`
- `active_worktree`
- `scope_file`
- `branch_note`

これらは「今どこで触っているか」を補助する metadata であり、実験 topic の identity ではありません。

## update rule

- 新しい topic を追加したら、`experiments/registry.toml` に entry を追加します。
- topic の canonical entrypoint を変えたら、registry を同じ変更で更新します。
- formal run のコマンドを変えたら、registry と topic README を同じ変更で更新します。
- 実験 topic を隔離 branch / worktree で扱う場合だけ、`active_branch` や `scope_file` を更新します。
- branch を閉じたら、stale な `active_branch` や `active_worktree` を整理します。
- branch にだけ残す実験は、main から implementation tree を削除し、
  `[[branch_topics]]` だけで辿れるようにします。

手で編集してもよいですが、通常は次を使います。

```bash
python3 tools/experiments/create_experiment_topic.py <topic>
python3 tools/experiments/sync_experiment_registry_context.py --topic <topic>
```

## server 実行ルール

- formal run は `tools/experiments/run_managed_experiment.py` を使います。
- 可能なら `--use-registered-command formal` を使い、registry の formal command をそのまま実行します。
- `run_manifest.json` には registry snapshot を残し、あとで「どの topic のどの正本 command を使ったか」を辿れるようにします。
- `required_eval_artifacts` と `optional_eval_artifacts` は `result/<run_name>/` から自動収集したい eval artifact pattern を表します。`summary.json` と `cases.jsonl` は managed runner の既定 required eval とし、topic 固有の追加 artifact だけを registry に書き足します。top-level managed file (`run_manifest.json`、`eval_manifest.json`、`run.log`) は reserved で、pattern に指定してはいけません。

## validation

```bash
python3 tools/ci/check_experiment_registry.py
make experiment-check
```

この checker は、path の存在、必須 field、command の placeholder、branch / worktree metadata の妥当性を確認します。
