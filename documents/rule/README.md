<!--
@dependency-start
contract policy
responsibility Documents 文書規約正本の入口。
upstream design ../README.md documents index
upstream design ../design/README.md design canon reader route
upstream design ../repo-structure-contract.toml machine validator companion
downstream implementation ../../tools/agent_tools/check_convention_compliance.py convention validation
downstream implementation ../../tools/agent_tools/repo_structure_contract.py structure validation
@dependency-end
-->

# 文書規約

このディレクトリは、文書の filename、配置、構成を決める規約の正本です。
各規約は、読者が次の責務判断を再現できるように、owner と検証責任を明示します。

## 読者の入口

- [命名規約](naming.md): filename、identifier、artifact、運用名の決め方。
- [ディレクトリ構成規約](directory-structure.md): 文書の配置、分割、正本境界の決め方。
- [依存モジュール変更規約](dependency-module-changes.md): `.gitmodules`、独立 source clone、vendor pin projection、topic root mount、cleanup の共通契約。
- [設計正本の入口](../design/README.md): target state と実装境界を固定する設計文書。

## 所有境界

`documents/rule/` は命名・配置・構成判断の一般規約を持ちます。
`documents/design/` は個別の target state、実装境界、設計上の前提を持ちます。
machine validator の期待値は `documents/repo-structure-contract.toml` に置きます。
生成された report、log、raw evidence、generated artifact、issue は evidence または運用の owner に属し、設計正本にはしません。

規約の本文は日本語で書き、path、identifier、ToolCall、external fixed name は原表記を保ちます。
