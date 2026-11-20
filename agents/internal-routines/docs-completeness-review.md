# docs-completeness-review
<!--
@dependency-start
contract agent-runtime
responsibility Documents docs-completeness-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

文書が存在するだけでなく、読者が作業や判断に必要な情報を欠かさず持っているかをレビューします。

## Use When

- README、設計文書、workflow 文書の不足確認
- 読者の理解や判断に必要な情報の欠落確認
- 実装変更後に docs が追随しているかの確認

## Core References

- [documents/conventions/coding-conventions-project.md](../../documents/conventions/coding-conventions-project.md)
- [documents/README.md](../../documents/README.md)
- [agents/internal-routines/docs-consistency-review.md](docs-consistency-review.md)
- [agents/skills/md-style-check.md](../skills/md-style-check.md)

## Review criteria

文書の目的と想定読者から、理解や判断に必要な情報が揃っているかを確かめます。
説明文書は判断の根拠と参照先、手順書は実際の操作に必要な入力と結果を確認します。
欠落は読者への影響と、補うべき正本を示します。

## Boundary

- Markdown の体裁だけを見るなら `md-style-check` を使います。
- 文書間の矛盾や stale route を潰すなら `docs-consistency-review` を使います。
