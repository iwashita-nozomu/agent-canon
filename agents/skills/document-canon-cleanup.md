# document-canon-cleanup
<!--
@dependency-start
responsibility Documents document-canon cleanup workflow for this repository.
upstream design README.md shared skill canon
upstream design ../canonical/CODEX_WORKFLOW.md shared workflow contract
downstream implementation ../../.agents/skills/document-canon-cleanup/SKILL.md exposes runtime skill
downstream implementation ../../tools/agent_tools/noncanonical_document_inventory.py finds non-canonical document candidates
@dependency-end
-->


## Purpose

正本でない文書、generated evidence、runtime mirror、重複見出し、stale 名称の文書を機械的に棚卸しし、どの正本を編集すべきかを先に固定します。

## Use When

- 文書整理を行う
- root view、runtime mirror、generated report、eval result、closed issue record が正本文書と混ざって見える
- ある文書を編集してよいか、正本へ戻すべきか判断したい
- README、workflow、skill、tool docs の重複や stale path を探したい

## Core Tool

```bash
python3 tools/agent_tools/noncanonical_document_inventory.py \
  --root . \
  --json-out reports/noncanonical-documents.json \
  --markdown-out reports/noncanonical-documents.md
```

`--fail-on-findings` は gate 用です。通常の整理 pass では、まず report を出して分類を読みます。

## Classification Rules

- `runtime_mirror`: `.claude/skills/*/SKILL.md` のような生成 mirror。正本は `.agents/skills/*/SKILL.md`。
- `accumulated_eval_result`: `agents/evals/results/` の蓄積結果。正本 policy ではなく evidence。
- `generated_report`: `reports/` 配下。再生成または evidence として扱い、source policy にしません。
- `closed_issue_record`: `issues/closed/` 配下。履歴 record として保持し、新 scope は新 issue にします。
- `missing_dependency_manifest`: 文書として残すなら dependency header を足し、artifact なら source tree 外へ移します。
- `duplicate_heading_candidate`: H1 が重複する active 文書。merge、retitle、または両方が必要な理由を明記します。
- `stale_name_candidate`: path 名が backup / copy / legacy / old / snapshot / stale を示す候補。現行正本か確認します。

## Cleanup Sequence

1. `noncanonical_document_inventory.py` を実行し、JSON と Markdown report を作ります。
1. Findings を class ごとに分けます。
1. `runtime_mirror` は正本を編集し、`python3 tools/docs/mirror_skill_shims.py --target .claude/skills --prune` で再生成します。
1. `accumulated_eval_result`、`generated_report`、`closed_issue_record` は原則編集しません。必要なら generator、eval manifest、issue の open record、または正本文書を編集します。
1. `missing_dependency_manifest` は文書として残すか、artifact として移すかを決めます。残す場合は nearest canonical anchor への `upstream` を足します。
1. `duplicate_heading_candidate` は正本候補へ統合するか、reader が区別できる H1 に変更します。
1. 変更後に再実行して、意図した finding だけが残ることを確認します。

## Closeout Checks

```bash
python3 tools/agent_tools/noncanonical_document_inventory.py --root .
python3 tools/docs/mirror_skill_shims.py --target .claude/skills --prune --check
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
python3 tools/agent_tools/check_convention_compliance.py
```

残す finding は、生成 evidence や runtime mirror のように「非正本だが必要」なものだけにします。
