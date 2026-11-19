<!--
@dependency-start
contract template
responsibility Provides the canonical structure for a design document.
upstream design ../../documents/design/README.md design-document ownership and reader route.
upstream design ../../documents/rule/README.md repository document filename and language rules.
upstream design ../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses and sparse projection traces.
downstream implementation README.md implements the approved boundary.
@dependency-end
-->

# <Design title>

<設計の目的と、確定した設計の概要。>

## 責務と公開境界

<各構成要素の役割、公開される振舞い、依存関係。>

## 設計判断と根拠

<確定した判断、必要な定義、判断を支える根拠。>

## 参照

<仕様、既存の実装、検証結果へのリンク。>

Docstring の意味と対応は、既存の
[Docstring Semantic Contract](../../documents/conventions/DOCSTRING_GUIDE.md#canonical-template-skeleton)
と、該当する設計・実装への参照で示します。
