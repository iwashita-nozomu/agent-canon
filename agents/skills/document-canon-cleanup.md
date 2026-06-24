# document-canon-cleanup
<!--
@dependency-start
contract skill
responsibility Documents document-canon cleanup workflow for this repository.
upstream design README.md shared skill canon
upstream design ../canonical/CODEX_WORKFLOW.md shared workflow contract
downstream implementation ../../.agents/skills/document-canon-cleanup/SKILL.md exposes runtime skill
downstream implementation ../../rust/agent-canon/src/structured_analysis.rs canonical document inventory implementation
@dependency-end
-->


## Purpose

補助文書、generated evidence、root view、重複見出し、stale 名称の文書を機械的に棚卸しし、どの文書を編集すべきかを先に固定します。

## Use When

- 文書整理を行う
- root view、generated report、eval result、closed issue record が正本文書と混ざって見える
- ある文書を編集してよいか、正本へ戻すべきか判断したい
- README、workflow、skill、tool docs の重複や stale path を探したい

## Core Tool

```bash
agent-canon structured-analysis document-inventory \
  --root . \
  --json-out reports/noncanonical-documents.json \
  --markdown-out reports/noncanonical-documents.md
```

Old Python document-inventory entrypoints have been retired. Update any caller
that still names one to the Rust command before returning to the original task.

`--fail-on-findings` は gate 用です。通常の整理 pass では、まず report を出して分類を読みます。

## Classification Rules

- `accumulated_eval_result`: `.agent-canon/log-archive/eval-results/` の蓄積結果。正本 policy ではなく evidence。
- `generated_report`: `reports/` 配下。再生成または evidence として扱い、source policy にしません。
- `closed_issue_record`: `issues/closed/` 配下。履歴 record として保持し、新 scope は新 issue にします。
- `missing_dependency_manifest`: 文書として残すなら dependency header を足し、artifact なら source tree 外へ移します。
- `duplicate_heading_candidate`: H1 が重複する active 文書。merge、retitle、または両方が必要な理由を明記します。
- `stale_name_candidate`: path 名が backup / copy / legacy / old / snapshot / stale を示す候補。現行正本か確認します。

## Cleanup Sequence

1. `agent-canon structured-analysis document-inventory` を実行し、JSON と Markdown report を作ります。
1. Findings を class ごとに分けます。
1. `accumulated_eval_result`、`generated_report`、`closed_issue_record` は原則編集しません。必要なら generator、eval manifest、issue の open record、または正本文書を編集します。
1. `missing_dependency_manifest` は文書として残すか、artifact として移すかを決めます。残す場合は nearest canonical anchor への `upstream` を足します。
1. `duplicate_heading_candidate` は正本候補へ統合するか、reader が区別できる H1 に変更します。
1. 変更後に再実行して、意図した finding だけが残ることを確認します。

## Closeout Checks

```bash
agent-canon structured-analysis document-inventory --root .
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
python3 tools/agent_tools/check_convention_compliance.py
```

残す finding は、生成 evidence のように「非正本だが必要」なものだけにします。
