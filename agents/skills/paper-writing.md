# paper-writing
<!--
@dependency-start
responsibility Documents paper-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

論文 draft、thesis chapter、scholarly paper section を、section contract と citation/evidence trace を先に固定しながら複数 subagent で起こす skill です。

## Use When

- 投稿論文や thesis chapter の draft を作る
- abstract、introduction、related work、method、results、discussion を持つ paper-like 文書を書く
- citation、figure、table、appendix、result の参照関係を author 1 人の勘に任せたくない
- academic-writing より一段 paper-specific な section discipline が欲しい

## Core References

- `agents/workflows/paper-writing-workflow.md`
- `agents/workflows/academic-writing-workflow.md`
- `agents/workflows/long-form-writing-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/skills/academic-writing.md`

## Mandatory Checklist

- `paper intent brief` と `claim contract` を先に固定する
- `section contract` を `abstract`, `introduction`, `related work`, `method`, `results`, `discussion`, `limitations`, `conclusion` の粒度で決める
- `citation and evidence matrix` を作り、主要 claim がどの citation / figure / table / derivation / appendix に支えられるかを書く
- `notation ledger` と `paragraph claim map` を作る
- run bundle を先に作り、`citation_evidence_reviewer`、`notation_definition_reviewer`、`logic_gap_reviewer`、`document_flow_reviewer` を explicit に有効化する
- draft 後に reverse outline を取り、review 前に section role の重複を潰す
- `document_flow_reviewer`、citation review、notation review、logic-gap review、別 reviewer の docs completeness review を必ず通す

## Default Sequence

1. `paper intent brief` と `claim contract` を書く
1. `section contract` を書く
1. `citation and evidence matrix` と `notation ledger` を作る
1. `paragraph claim map` を作る
1. run bundle を作る
1. reader order で draft する
1. reverse outline を取る
1. `document_flow_reviewer` を通す
1. `citation_evidence_reviewer` に citation review を通す
1. `notation_definition_reviewer` に notation review を通す
1. `logic_gap_reviewer` に logic-gap review を通す
1. 別 reviewer に docs completeness review を通す
1. higher-order revision を終えてから line edit に入る
1. `make docs-check` で閉じる

## Standard Command

```bash
python3 tools/agent_tools/doc_start.py \
  --task "paper writing task" \
  --kind paper \
  --owner "codex" \
  --workspace-root "$PWD"
```

## Boundary

- paper-like でない学術文章や method note は `academic-writing` を使います
- 文献探索自体が主タスクなら `literature-survey` を先に使います
- rebuttal や report の evidence traceability を主に見たいなら report review を追加します
