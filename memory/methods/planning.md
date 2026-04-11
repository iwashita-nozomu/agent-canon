# Planning Method Memory

## Purpose

- execution order、gate、handoff を固定する
- chunk 完了と task completion を混同しない

## Stable Methods

- repo-changing task では run bundle、contract、schedule、work_log を先に作る
- planned work unit と clause coverage を先に固定する
- user-facing completion は全 planned work unit、review、validation、closeout、commit、push まで待つ
