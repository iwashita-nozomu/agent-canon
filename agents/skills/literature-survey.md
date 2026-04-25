# literature-survey
<!--
@dependency-start
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

文献調査、先行研究整理、関連資料比較を、検索、選定、反証候補の抽出まで含めて扱います。

## Use When

- 研究や設計の前提になる外部資料を集めたい
- survey、代表論文、比較論文、仕様資料を整理したい
- ある主張を支える資料と弱める資料の両方を見たい
- baseline、評価指標、failure mode の根拠を文献ベースで決めたい
- `references/` や `notes/` に残す索引を作りたい

## Core References

- `agents/workflows/research-workflow.md`
- `agents/workflows/workflow-references.md`
- `references/README.md`
- 必要なら対象 topic の既存 `notes/themes/*.md`
- 必要なら対象 topic の既存 `notes/experiments/*.md`

## Mandatory Checklist

- primary source、survey、benchmark comparison を優先します
- peer-reviewed、preprint、vendor doc、blog を区別して記録します
- 支持資料だけでなく、限定条件や反証候補も集めます
- query、探索日、採用理由、除外理由を残します
- task に近い problem setting、data regime、hardware regime を区別します
- source から直接言えることと、自分の解釈を分けます
- 最終的に使う主張ごとに source を辿れるようにします

## Canonical Flow

1. 問いを 1 文で固定する
1. inclusion / exclusion を決める
1. query pack を作る
1. survey、代表論文、比較論文、公式資料を優先して集める
1. 支持資料と反証候補を分ける
1. 各 source について、setting、claim、limitations、使える点を短く抜く
1. baseline、metric、failure mode、artifact policy に効く source を抜き出す
1. `Known`、`Contested`、`Open` に整理する
1. `references/` か `notes/` に残す

## Deliverable Shape

- `Question`
- `Scope`
- `Search Log`
- `Primary Sources`
- `Contrary Or Narrowing Sources`
- `Known`
- `Contested`
- `Open`
- `Implications For Implementation Or Experiment`

## Boundary

- 研究全体の outer loop は `research-workflow` を使います
- 実験結果の批判的評価は critical review を使います
- reader-facing な report の確認は report review を使います
- repo-wide な workflow や review policy の外部根拠索引は `agents/workflows/workflow-references.md` に残します
