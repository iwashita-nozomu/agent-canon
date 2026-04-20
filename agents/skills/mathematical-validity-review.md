# Mathematical Validity Review

## Purpose

定式化、導出、exactness claim、比較境界が数理的に本当に成立しているかを独立にレビューします。

## Use This For

- 数理主導の algorithm change や新しい formulation の review
- hidden assumption、dimension mismatch、well-posedness の欠落確認
- exact line と approximation line の混同検出
- 実装前に「何が proven で何が heuristic か」を切り分けたいとき

## Inputs

- formulation draft
- notation ledger
- derivation or proof sketch
- baseline and comparison targets

## Outputs

- severity 付き findings
- required change
- `accepted`, `contested`, `open` の仕分け

## Review Stance

- 人ではなく定式化と主張に対して厳しく振る舞います。
- 「この式が成り立たない条件は何か」を先に探します。
- hidden assumption、未定義記号、比較境界のごまかしを優先して探します。
- 実装都合の heuristic を exact claim として通しません。
- 証明できていない箇所は、弱い主張に落とすか open question として残します。

## Findings Format

- `severity`
  - `high`、`medium`、`low`
- `claim`
  - 問題のある主張や式を短く特定する
- `why contested`
  - どの仮定が欠けているか、どこで境界が混ざっているか
- `required change`
  - claim を弱める、記号を定義する、条件を追加する、baseline 境界を書き直す
- `outcome`
  - `accepted`、`contested`、`open`

## Good Review Outcome

- `accepted`
  - 正当化に必要な条件が揃い、reader-facing claim をそのまま維持できる
- `contested`
  - 定式化や主張を今のまま reader-facing に出せない
- `open`
  - 実装は進められるが、未証明点を隠さず残す必要がある

## Mandatory Checklist

- 記号、shape、domain、index range が一貫している
- objective と constraint が well-posed に書かれている
- existence、uniqueness、differentiability、convexity などの必要条件が暗黙になっていない
- exact claim、relaxation、近似、数値解法依存の部分が分離されている
- baseline との差が formulation の差として説明されている
- algorithm step が formulation から正当に導かれているか、heuristic なら明示されている
- failure mode、counterexample 候補、open assumption が列挙されている

## Review Outcomes

- `accepted`
  - 数理主張を current scope で維持してよい
- `contested`
  - claim を弱めるか formulation を修正する必要がある
- `open`
  - 実装は進められるが、reader-facing には open question として残す必要がある

## Boundary

- evidence や benchmark の批判的評価は `agents/skills/critical-review.md` を使います。
- 実装差分や API 境界のレビューは `agents/skills/change-review.md` を使います。
- canonical な定式化の作成自体は `agents/skills/mathematical-formulation.md` を使います。

## Implementation Surface

- shared canon only
