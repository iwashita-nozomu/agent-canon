# docs-consistency-review
<!--
@dependency-start
@dependency-end
-->


## Purpose

文書間の矛盾、古い導線、canon drift を洗います。

## Use When

- 複数文書を同時に更新した
- workflow や agent 文書を整理した
- README と詳細文書の整合を確認したい

## Core References

- `documents/README.md`
- `documents/AGENTS_COORDINATION.md`
- `agents/README.md`

## Expected Outcome

- entrypoint と詳細正本の食い違いが見える
- stale path、古い command、duplicated truth が分かる
- どの文書を正本に寄せるべきか判断できる

## Comparison Surface

- `AGENTS.md`、`README.md`、`QUICK_START.md` の入口文書
- `agents/` と `documents/` の正本
- `.agents/skills/` と `.claude/skills/` の runtime shim
- script usage と文書中の command 例

## Mandatory Checklist

- 入口文書と詳細文書で command、path、branch policy が一致している
- 同じルールが複数箇所に書かれている場合、正本が明確である
- 既に無い file / path / tool への参照が残っていない
- one-off の実験や古い運用が正本として残っていない
- runtime shim と human canon の差が意図的か確認している

## Default Sequence

1. 入口文書を先に見て、そこから辿れる正本を列挙します。
1. command、path、branch policy、validation command を横並びで比較します。
1. stale reference、duplicated truth、曖昧な正本を findings 化します。
1. 直すべき場所が runtime entrypoint か canonical doc かを明示します。

## Boundary

- 1 文書だけの中身不足は `docs-completeness-review` を使います。
- Markdown 体裁だけの問題は `md-style-check` を使います。
