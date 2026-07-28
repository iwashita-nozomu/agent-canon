<!--
@dependency-start
contract reference
responsibility runtime surface、profile、log archive の文書と機械可読契約の入口。
upstream design ../README.md documents 索引と正本境界。
downstream implementation ../../tools/agent_tools/surface_manifest.py shared surface checker。
@dependency-end
-->

# Runtime

この directory は AgentCanon runtime の root view、profile、validation route、log archive
を扱います。`.codex/`、`.devcontainer/`、hooks、tools の実装は各 source directory が
所有し、ここにはその責務を複製しません。

## 構成

- `SHARED_RUNTIME_SURFACES.md` と `shared-runtime-surfaces.toml`: shared surface の
  人間向け規約と機械可読 manifest。
- `runtime-profiles-and-check-matrix.json`、`.md`: profile と validation route。
- `runtime-log-archive.md`、`runtime-log-archive-migration.md`: log archive の契約。
- `log-surface-inventory.json`: runtime surface inventory。

機械可読ファイルを編集した場合は、対応する reader projection と checker の所有範囲を
確認します。
