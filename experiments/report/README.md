# Experiment Reports

`experiments/report/` には 1 回の run に対応する report を置きます。
report 名は `run_name` とそろえ、`experiments/<topic>/result/<run_name>/` と 1 対 1 で辿れるようにします。

最低限、次を report 側で辿れるようにします。

- `Question:`
- `Comparison Target:`
- exact command
- `result/<run_name>/` の path
- `run_manifest.json`
- `summary.json`
- `cases.jsonl`

cross-run の要約や campaign 全体の知見は `notes/experiments/` へ移します。
