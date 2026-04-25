# code-review
<!--
@dependency-start
@dependency-end
-->


## Purpose

変更差分を correctness、設計、保守性の観点でレビューします。

## Use When

- PR 前後の変更レビュー
- doc / code / test の整合確認
- refactor での境界確認
- 規約逸脱や過剰修正の検出

## Core References

- `agents/skills/change-review.md`
- `agents/skills/python-review.md`
- `agents/skills/cpp-review.md`
- `documents/REVIEW_PROCESS.md`

## Expected Outcome

- severity つき findings が優先順で出ている
- behavior、設計境界、doc/test alignment の崩れが見えている
- `no findings` の場合でも residual risk や未確認項目が残っている

## Mandatory Checklist

- 実際の diff と changed file list を先に読んでいる
- 変更の目的に対して、実装、テスト、文書が揃っているか見ている
- backward compatibility と call site 影響を見ている
- error handling、defaults、削除影響、rename 影響を見ている
- validation が十分か、欠けているなら明示している

## Review Sequence

1. `git diff --stat` と changed files を見て、review 対象を固定します。
1. behavior が変わる箇所から順に読み、回帰点を探します。
1. API、config、doc、test の追随を確認します。
1. findings を `fix now` と `follow-up` に分け、evidence を添えて返します。
1. Python-heavy diff なら `python-review` を追加し、より厳密に閉じます。
1. C / C++ heavy diff なら `cpp-review` を追加し、より厳密に閉じます。

## Findings Format

- `severity`
- `finding`
- `required change`
- `evidence`

## Review Stance

- finding を先に出します。
- 壊れる理由、根拠不足、テスト不足、stale doc を優先して探します。
- 説明より evidence を重視します。

## Boundary

- この repo の findings-first review の正本は `change-review` です。
- Python 差分で pyright / pytest / ruff を強く見る場合は `python-review` を追加します。
- C / C++ 差分で build / header / ownership を強く見る場合は `cpp-review` を追加します。
- 実験主張の批判的評価は `critical-review` を使います。
