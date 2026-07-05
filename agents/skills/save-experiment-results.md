# save-experiment-results
<!--
@dependency-start
contract skill
responsibility Documents Save Experiment Results for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design experiment-lifecycle.md experiment lifecycle workflow
upstream design result-artifact-writeout.md durable raw/result/report artifact writeout
upstream design ../../documents/experiment-report-style.md experiment report artifact policy
downstream implementation ../../.agents/skills/save-experiment-results/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/experiments/publish_result_branch.py publishes formal result branches
@dependency-end
-->

## Reader Map

- Purpose: save experiment outputs as durable, reproducible artifacts with a
  branch-safe retention route.
- Use when: experiment results, run directories, reports, or result branches
  need to be preserved after a run or reviewed before publication.
- Section path: Purpose and Use When define the entry; Required Contract fixes
  raw/report/manifest shape; Branch-Safe Retention defines source branch versus
  result branch behavior; Closeout Tokens names evidence.
- Boundary: this skill saves existing experiment results. Starting or changing
  experiments belongs to `experiment-lifecycle`; interpreting reports belongs
  to `report-writing`.

## Purpose

実験結果を chat-only summary や source branch のついでではなく、あとから再利用できる
raw artifact、reader report、manifest、result branch として保存します。
保存先と branch 操作を先に固定し、結果の上書き、source change の隠蔽、失敗 run の
破棄を防ぎます。

## Use When

- user が実験結果の保存、保存 skill、result branch、formal retention、publish、
  run artifact の保全を求める
- `experiments/<topic>/result/<run_name>/` を source checkout から保存する
- raw result と `experiments/report/<run_name>.md` を同じ source run に結び付ける
- failed、skipped、blocked、partial run を routing evidence として残す
- 保存済み result を overwrite せず、unique run_name か append-only 証跡にする

## Required Contract

1. 結果保存の前に retention plan を書く:
   - `topic`
   - `run_name`
   - `result_dir`
   - `source_branch`
   - `source_commit`
   - `source_dirty_state`
   - `result_branch`
   - `remote_publish`
   - `overwrite_policy`
   - `report_path`
1. 正本 source は既存の `experiments/<topic>/result/<run_name>/` です。
   result directory が無い場合は結果を作ったことにせず、`experiment-lifecycle`
   へ戻して run plan を作ります。
1. Raw machine-readable artifact を先に保存し、その同じ raw result から
   summary/report を作ります。標準 artifact は `run_manifest.json`、
   `eval_manifest.json`、`artifact_manifest.json`、`command.json`、
   `environment.json`、`source_snapshot.json`、`config.json`、
   `config_source.yaml`、`run.log`、`logs/startup.jsonl`、`logs/stdout.log`、
   `logs/stderr.log`、`summary.json`、`cases.jsonl`、case artifacts、
   `visualize_executed.ipynb` です。
1. 欠けている標準 artifact は limitation として manifest / report に記録します。
   欠落を report prose で埋めたり、別 run の artifact で混ぜたりしません。
1. Failed、skipped、blocked、partial run も保存対象です。`status`、`exit_code`、
   blocker、partial artifact list、次 action を manifest に残します。
1. 同じ `run_name` の detailed result を上書きしません。再実行は新しい
   `run_name`、または append-only manifest entry として扱います。cleanup が必要な
   場合は、削除対象、理由、owner、代替保存先を retention plan に書きます。
1. Reader-facing report を作る場合は `report-writing` を使い、観測、解釈、
   limitation、next action、artifact list を分けます。Markdown 正本 report は
   `experiments/report/<run_name>.md` です。

## Branch-Safe Retention

1. Source branch / PR は code、config、protocol、report generator 変更を運びます。
   Raw experiment result を source branch や `main` に混ぜて保存しません。
1. Formal result retention は専用 branch に出します:

```bash
python3 tools/experiments/publish_result_branch.py \
  --result-dir experiments/<topic>/result/<run_name> \
  --branch experiment-results/<topic>
```

Remote 保全が run plan に含まれる場合だけ `--push` を付けます。

1. Result branch を作成または更新する前に、run bundle、manifest、PR body、または
   report に `branch_creation_reason=<reason>` と `result_branch=<branch>` を
   記録します。理由は result retention であり、source diff の隔離ではありません。
1. Result branch には result/report artifacts だけを置きます。code、config、
   protocol、skill、tool、workflow の変更を result branch に隠しません。
1. Formal result は clean な canonical source checkout、通常は `main`、または
   merged / approved source PR commit から作ります。source checkout が dirty の
   run は保存対象ですが、`source_dirty_state` と affected paths を manifest に残し、
   `experiment_formal_status=not_formal_dirty_source` とします。formal success
   evidence にするには source diff を commit / PR route に通し、その commit から
   rerun します。
1. Source PR を直した後は、古い result branch を成功 evidence として使い回しません。
   protocol、config、code、metric、report generator が変わった場合は、再実行するか
   `experiment_formal_status=not_formal_stale_source` として保持だけにします。

## Closeout Tokens

Record these in the run bundle, manifest, PR body, or final handoff:

```text
experiment_result_save=complete
experiment_topic=<topic>
experiment_run_name=<run_name>
experiment_result_dir=<path>
experiment_result_branch=<branch-or-not_published>
experiment_source_commit=<sha>
experiment_source_dirty_state=<clean|dirty_with_paths>
experiment_formal_status=<formal|not_formal_dirty_source|not_formal_stale_source|not_formal_partial>
experiment_raw_manifest=<path>
experiment_report=<path-or-not_requested>
experiment_overwrite_policy=<unique-run-name|append-only|cleanup-with-record>
```
