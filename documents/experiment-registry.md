# Experiment Registry
<!--
@dependency-start
contract reference
responsibility Documents Experiment Registry for this repository.
upstream design README.md durable document index
downstream implementation ../tools/ci/check_experiment_registry.py validates registry schema
downstream implementation ../tools/agent_tools/tool_rejection_preflight.py predicts managed execution surface guardrails
@dependency-end
-->


この文書は、`experiments/registry.toml` を使って experiment topic を集中管理する契約を定めます。
server 上でどの実験コードを正式に実行するかを、topic ごとに 1 か所へ固定するのが目的です。

## この文書の読み方

- この文書は、experiment topic の正本 entrypoint、実行 command、成果物入口を
  `experiments/registry.toml` に集約する契約を扱います。
- 主な順路は、役割、正本ファイル、branch-only topics、branch / worktree
  metadata、update rule、server 実行ルール、validation です。
- 実験 topic を追加、移動、正式実行するときに読みます。
- 境界: branch 名は補助情報であり、topic 名と registry entry が正本です。

## 役割

- experiment topic の正本 entrypoint を固定する
- smoke / formal run の canonical inner command を固定する
- `README.md`、`result/`、`report/` を固定し、topic README を通じて可視化 notebook の入口を固定する
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

`topic_readme` は、実験内容、問い、比較対象、標準コマンド、設定正本、可視化 notebook、
出力 schema、run_name 規則を辿る入口です。`result_root` は
`result/<run_name>/` だけでなく、各 run の `result/<run_name>/logs/` も含む
runtime artifact surface として扱います。

`smoke_inner_command` と `formal_inner_command` は `{run_dir}` に加えて `{config_path}` を含めます。
checked-in 設定正本は topic の `config.yaml` に置きます。managed runner は run 開始前に
`result/<run_name>/config.json` と `result/<run_name>/config_source.yaml` を書き出し、inner command はその
snapshot から今回 run の設定を復元します。必要な topic では `{config_source_path}`、
`{stdout_log_path}`、`{stderr_log_path}`、`{startup_log_path}` も registered command で参照できます。

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

新規 topic は、実験名を固定してから AgentCanon template path
`vendor/agent-canon/experiments/_template/` をコピーし、registry entry を追加します。

```bash
cp -r vendor/agent-canon/experiments/_template experiments/<topic>
python3 tools/experiments/sync_experiment_registry_context.py --topic <topic>
```

## server 実行ルール

- project `Makefile` は registry の smoke / formal command へ到達する target を持ちます。標準名は `make experiment-smoke TOPIC=<topic>` と `make experiment-formal TOPIC=<topic>` です。
- formal run は `tools/experiments/run_managed_experiment.py` を使います。
- 可能なら Make target の内側で `--use-registered-command formal` を使い、registry の formal command をそのまま実行します。
- `run_manifest.json` には registry snapshot を残し、あとで「どの topic のどの正本 command を使ったか」を辿れるようにします。
- checked-in 設定正本は topic の `config.yaml` に置きます。managed runner は `config.json` に今回 run の設定 dictionary と path map を残し、`config_source.yaml` に checked-in `config.yaml` のコピーを残します。`run_manifest.json` からも `config_path` と `config_source_path` を辿れるようにします。
- run 開始時点の再現情報は managed runner が `command.json`、`environment.json`、`source_snapshot.json` に保存します。`command.json` は placeholder 解決後の command と cwd、`environment.json` は全 environment key を記録し secret-like key の値を redaction します。`source_snapshot.json` は topic source、registry、command source、runner source、dirty source file の bytes / sha256 と git status を持ちます。
- 各 managed run は `result/<run_name>/logs/` を持ちます。top-level `run.log` は runner が管理する互換ログで、追加の stdout / stderr、tool log、diagnostic log は `logs/` 配下へ置きます。
- managed runner は標準で `logs/startup.jsonl`、`logs/stdout.log`、`logs/stderr.log` を作ります。`config.yaml` 欠落 preflight、command 起動失敗、子 process の非ゼロ終了は failed run として `run_manifest.json`、`eval_manifest.json`、`artifact_manifest.json`、対応する `logs/` artifact に残します。
- run 終了時には `artifact_manifest.json` を書き、`result/<run_name>/` 内の managed file、raw result、summary、log の relative path、bytes、sha256 を記録します。`artifact_manifest.json` 自身は digest 対象から外します。
- 可視化は `experiments/<topic>/visualize.ipynb` の Jupyter notebook を入口にします。notebook は `summary.json`、`cases.jsonl`、必要な `logs/` artifact を読んで図表化するためのもので、formal run の起動や設定正本にはしません。
- `required_eval_artifacts` と `optional_eval_artifacts` は `result/<run_name>/` から自動収集したい eval artifact pattern を表します。`summary.json` と `cases.jsonl` は managed runner の既定 required eval とし、topic 固有の追加 artifact だけを registry に書き足します。managed file と managed log (`run_manifest.json`、`eval_manifest.json`、`run.log`、`artifact_manifest.json`、`command.json`、`config_source.yaml`、`environment.json`、`source_snapshot.json`、`logs/startup.jsonl`、`logs/stdout.log`、`logs/stderr.log`) は `artifact_manifest.json` で辿ります。

## validation

```bash
python3 tools/ci/check_experiment_registry.py
make experiment-check
```

この checker は、path の存在、必須 field、command の placeholder、branch / worktree metadata の妥当性を確認します。
registered command から `{config_path}` が欠ける場合も fail します。

実験実行面の変更では、`tool_rejection_preflight.py` の
`experiment_execution_surface_guard` を patch 前の routing evidence にします。
対象は managed runner、registry checker、この registry contract、experiment
workflow、project `experiments/registry.toml` です。検証は
project `experiments/registry.toml` がある checkout では
`python3 tools/ci/check_experiment_registry.py` を実行し、
runner / registry checker behavior は
`python3 -m pytest tests/tools/test_run_managed_experiment.py -q` を標準にし、
formal run は実験計画の実行段階で扱います。
