<!--
@dependency-start
contract reference
responsibility repository structure と ownership の機械可読契約入口。
upstream design ../README.md documents 索引と正本境界。
downstream implementation ../../tools/validation/semantic/structure/repo_structure_contract.py structure checker。
@dependency-end
-->

# 構造契約

この directory は repository tree、path、mode、profile の機械可読契約を置きます。
人間向けの配置理由は `../rule/`、親レポの root 境界は `../parent-repository/` が
所有します。

## 構成

- `repo-structure-contract.toml`: AgentCanon と親レポの期待構造。

このファイルの path を変更すると checker、root view、親レポの構造確認が連動するため、
移動だけでなく参照元と検証経路を同時に更新します。
