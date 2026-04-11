# Testing Method Memory

## Purpose

- nasty case と regression case を実装前に固定する
- correctness と performance の証拠を混ぜない

## Stable Methods

- code-changing task では test_designer を実装前に通す
- fix-now review finding に対応する regression case を同じ pass で入れる
- spot run と正式 evidence を区別する
