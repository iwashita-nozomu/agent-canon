# document-canon-cleanup
<!--
@dependency-start
contract skill
responsibility Documents document-canon cleanup workflow for this repository.
upstream design README.md shared skill canon
upstream design ../canonical/CODEX_WORKFLOW.md shared workflow contract
downstream implementation ../../.codex/personal/skills/document-canon-cleanup/SKILL.md exposes runtime skill
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/structured_analysis.rs canonical document inventory implementation
@dependency-end
-->


## Purpose

文書の正本、generated evidence、root view、重複見出し、stale 名称の境界を
確認します。編集対象と正本が既に分かっている範囲は直接確認し、候補や
所有者が曖昧な範囲だけ inventory で調べます。

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
- `github_issue_record`: repository-qualified GitHub Issue URL/number。GitHubを正本とし、source treeに履歴mirrorを作りません。
- `missing_dependency_manifest`: 文書として残すなら dependency header を足し、artifact なら source tree 外へ移します。
- `duplicate_heading_candidate`: H1 が重複する active 文書。merge、retitle、または両方が必要な理由を明記します。
- `stale_name_candidate`: path 名が backup / copy / legacy / old / snapshot / stale を示す候補。現行正本か確認します。

## Cleanup Route

Use `agent-canon structured-analysis document-inventory` when the candidate set
or source/evidence/generated boundary is unresolved, or when the request asks for
an inventory report. Classify only the findings in that selected scope. Leave
accumulated evaluation results, generated reports, and closed Issue records with
their source owners; if one must change, update its generator, manifest, open
Issue record, or canonical document instead. Resolve a missing dependency header
or duplicate heading only when present in the changed surface. Re-run inventory
only when the cleanup changes the inventory result or the selected validation
requires that readback.

## Selected Checks

Choose the check that establishes the changed property. These commands are
examples for their respective owners, not a required sequence for every document
edit.

```bash
agent-canon structured-analysis document-inventory --root .
bash tools/analysis/dependencies/run_repo_dependency_review.sh --fail-missing
python3 tools/validation/semantic/convention/check_convention_compliance.py
```

残す finding は、生成 evidence のように「非正本だが必要」なものだけにします。
