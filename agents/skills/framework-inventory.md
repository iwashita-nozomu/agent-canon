# Framework Inventory

## Purpose

既存 framework、library、runtime、design docs を topic keyword で洗い、再利用境界を先に固定します。

## Use This For

- 数理主導の実装前に、既存 extension point と近い API を洗いたいとき
- 既存 helper、runner、test pattern を再利用できるか確認したいとき
- 同じ責務の別 module や mini-runner を増やしたくないとき
- docs、notes、code、tests の正本を 1 枚の inventory にまとめたいとき

## Quick Path

1. topic keyword を 3-8 個に絞る
1. `documents/`、`notes/`、`references/` を先に洗って正本と過去判断を拾う
1. `python/`、必要なら `external/`、`include/`、`src/` を洗って再利用候補を拾う
1. `Closest reusable surface`、`Extend here`、`Do not duplicate`、`Tests to mirror`、`Next references` の 5 枚に圧縮する

## Output Shape

- `Closest reusable surface`
  - いちばん近い API、helper、test、design doc
- `Extend here`
  - 新設せず拡張で済む候補
- `Do not duplicate`
  - 増やしてはいけない別名 module、mini-runner、重複 helper
- `Tests to mirror`
  - 既存の使い方や failure case を持つ test
- `Next references`
  - formulation や design に渡す前に追加で読む file

## Must Read Before Working

- `AGENTS.md`
- `notes/guardrails/engineering_avoidances.md`
- `notes/failures/README.md`
- 対象 topic に近い `documents/design/` の正本
- 対象 topic に近い `notes/knowledge/`、`notes/themes/`

## Inputs

- topic
- topic keywords
- target module or runtime
- 想定する change surface

## Outputs

- existing framework inventory
- nearest reusable API、helper、test pattern
- extend / reuse / no-fit decision
- 次に読む design doc、note、reference の一覧

## Mandatory Checklist

- `documents/`、`documents/design/`、`notes/knowledge/`、`notes/guardrails/`、`notes/failures/`、`notes/themes/`、`notes/branches/`、`notes/worktrees/`、`notes/experiments/`、`references/` を topic keyword で検索する
- `python/jax_util/`、`python/experiment_runner/`、`external/experiment_runner/python/experiment_runner/`、`python/tests/`、`include/`、`src/` を topic keyword で検索する
- 最も近い公開 API、helper、test pattern、design doc を列挙する
- 新設ではなく拡張で済む候補を先に列挙する
- 責務重複、命名衝突、mini-runner 追加の禁止を明示する

## Default Commands

- `rg -n "<keyword>" documents documents/design notes references`
- `rg -n "<keyword>" python/jax_util python/experiment_runner external/experiment_runner/python/experiment_runner python/tests include src`
- `rg --files python/jax_util python/experiment_runner python/tests`
- `git log -- <path>`

## Boundary

- canonical な数理の置き方は `agents/skills/mathematical-formulation.md` を使います。
- 数理的妥当性の独立レビューは `agents/skills/mathematical-validity-review.md` を使います。
- repo-wide な棚卸し全般は `agents/skills/project-review.md` を使います。

## Implementation Surface

- shared canon only
