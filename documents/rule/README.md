<!--
@dependency-start
contract policy
responsibility Routes readers to individual rule owners without redefining their clauses.
upstream design ../README.md documents index
upstream design ../design/README.md design canon reader route
upstream design ../structure/repo-structure-contract.toml machine validator companion
downstream design naming.md naming policy owner
downstream design directory-structure.md document placement and authority owner
downstream design dependency-module-changes.md dependency identity and pin owner
downstream design repository-topic-clone.md generic checkout lifecycle owner
downstream implementation ../../tools/validation/semantic/convention/check_convention_compliance.py convention validation
downstream implementation ../../tools/validation/semantic/structure/repo_structure_contract.py structure validation
@dependency-end
-->

# 文書規約

この索引は、判断対象から個別規約の正本へ案内します。
規約の条件と検証責任は、次の各 owner 文書で確認します。

## 読者の入口

| 判断対象 | 規約の正本 |
| --- | --- |
| filename、identifier、artifact、運用名 | [命名規約](naming.md) |
| 文書の配置、分割、正本と evidence の境界 | [ディレクトリ構成規約](directory-structure.md) |
| dependency の identity、gitlink、pin、projection | [依存モジュール変更規約](dependency-module-changes.md) |
| repository-topic checkout の作成、再利用、merge、cleanup | [repository-topic clone ルール](repository-topic-clone.md) |

個別の target state と実装境界は [設計正本の入口](../design/README.md) からたどります。

## 所有境界

配置と正本の区別は [ディレクトリ構成規約の正本の境界](directory-structure.md#正本の境界)、
文書 filename と本文の言語は [命名規約の文書 filename](naming.md#文書-filename) が所有します。
この索引では、それらの条件を再定義しません。
