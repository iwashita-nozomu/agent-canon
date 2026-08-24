<!--
@dependency-start
contract reference
responsibility runtime surface、profile、log archive の文書と機械可読契約の入口。
upstream design ../README.md documents 索引と正本境界。
@dependency-end
-->

# Runtime

この directory は AgentCanon の shared bootstrap runtime、profile、validation route、log
archive を扱います。親の root view、submodule、`.devcontainer/` projection は現行の
runtime surface ではありません。hooks、tools の実装は各 source directory が所有し、ここ
にはその責務を複製しません。

## 構成

- `bootstrap-runtime.md`: shared tool runtime の人間向け規約。
- `runtime-profiles-and-check-matrix.json`、`.md`: profile と validation route。
- `runtime-log-archive.md`、`runtime-log-archive-migration.md`: log archive の契約。
- `log-surface-inventory.json`: runtime surface inventory。

機械可読ファイルを編集した場合は、対応する runtime checker の所有範囲を確認します。
Private feedback and reusable knowledge are defined in
[`private-feedback-knowledge.md`](private-feedback-knowledge.md). Their body
and receipts belong to the private `agent-canon-log` remote, not this source
checkout.
