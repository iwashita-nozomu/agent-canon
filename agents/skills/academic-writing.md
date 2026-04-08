# academic-writing

## Purpose

論文、thesis chapter、scholarly note、proposal のような学術文章を、claim と notation と logic を分離 review しながら書くための skill です。

## Use When

- 学術論文や chapter を新規作成する
- claim-heavy な survey、method note、appendix を書く
- 記号、略語、technical term、仮定、根拠の接続が reader の理解を左右する
- 一般の guide より、論理の欠落や定義順の破綻が問題になる

## Core References

- `documents/academic-writing-workflow.md`
- `documents/long-form-writing-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/skills/literature-survey.md`
- `agents/skills/logic-gap-review.md`
- `agents/skills/notation-definition-review.md`

## Mandatory Checklist

- `claim contract` で central contribution、gap、reader、non-goal を先に固定する
- `evidence map` で claim と support を section 単位で結ぶ
- `notation ledger` を作り、symbol / term / abbreviation / unit / index を管理する
- `paragraph claim map` を作り、各 paragraph の inferential role を固定する
- Codex では、可能なら parent session を `/collab` の `Plan` mode に切り替える
- runtime が `/agent` を提供する場合は inventory を確認し、使えない場合は `.codex/agents/*.toml` を見る
- run bundle を先に作り、`notation_definition_reviewer` と `logic_gap_reviewer` を explicit に有効化する
- draft 後に reverse outline を取る
- `document_flow_reviewer` を必ず通す
- 別 reviewer で `notation-definition-review` を必ず通す
- 別 reviewer で `logic-gap-review` を必ず通す
- 別 reviewer で `docs-completeness-review` を必ず通す
- empirical claim や report なら `critical-review`、必要なら `report-review` を追加する

## Default Sequence

1. `claim contract` を短く書く
1. `evidence map` と `notation ledger` を作る
1. `section contract` と `paragraph claim map` を作る
1. run bundle を作る
1. reader order で draft する
1. reverse outline を取る
1. `document_flow_reviewer` を通す
1. `notation_definition_reviewer` に `notation-definition-review` を通す
1. `logic_gap_reviewer` に `logic-gap-review` を通す
1. 別 reviewer に `docs-completeness-review` を通す
1. higher-order revision を終えてから line edit に入る
1. `make docs-check` で閉じる

## Standard Command

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "academic writing task" \
  --owner "codex" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer \
  --enable researcher \
  --enable research_reviewer \
  --enable notation_definition_reviewer \
  --enable logic_gap_reviewer
```

## Boundary

- 一般の README、workflow、migration 文書なら `long-form-writing` を使います
- 文献調査自体が主タスクなら `literature-survey` を先に使います
- experiment report の evidence traceability は `report-review` を優先します
