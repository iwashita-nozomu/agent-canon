# docs-consistency-review
<!--
@dependency-start
contract agent-runtime
responsibility Documents docs-consistency-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

文書間の矛盾、古い導線、canon drift を洗います。

## Use When

- 複数文書を同時に更新した
- workflow や agent 文書を整理した
- README と詳細文書の整合を確認したい

## Core References

- [documents/README.md](../../documents/README.md)
- [documents/codex/AGENTS_COORDINATION.md](../../documents/codex/AGENTS_COORDINATION.md)
- [agents/README.md](../README.md)

## Expected Outcome

- entrypoint と詳細正本の食い違いが見える
- stale path、古い command、duplicated truth が分かる
- どの文書を正本に寄せるべきか判断できる

## Review criteria

変更や報告されたずれから、関係する入口、正本、生成ビュー、実際のコマンドを選びます。
矛盾や古い参照があれば、相違点と修正する正本を示します。

## Boundary

- 1 文書だけの中身不足は `docs-completeness-review` を使います。
- Markdown 体裁だけの問題は `md-style-check` を使います。
