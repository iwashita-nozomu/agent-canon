<!--
@dependency-start
contract reference
responsibility Documents the deterministic static-seed export command and its failure semantics.
upstream implementation ../../tools/agent_tools/export_static_seed.py owns the command.
upstream design ../contracts/static-seed-export.md owns seed content and consumer boundaries.
upstream design ../contracts/static-seed-allowlist.toml owns the sole exact-path allowlist.
downstream implementation ../../tests/agent_tools/test_export_static_seed.py exercises the command.
@dependency-end
-->

# export_static_seed.py

この command は一つの AgentCanon commit から template consumer 向け static seed を生成します。
出力先は存在していない directory を指定します。

```bash
python3 tools/agent_tools/export_static_seed.py \
  --source-root . \
  --source-ref "$(git rev-parse HEAD)" \
  --output /tmp/agent-canon-static-seed
```

command は local Git object database だけを読み、fetch、clone、submodule、HTTP、SSH、secret を
使用しません。allowlist と payload は同じ commit から読みます。worktree file を直接 copy
しないため、未 commit の変更は出力へ混入しません。

成功時は `AGENT_CANON_STATIC_SEED=exported`、失敗時は
`AGENT_CANON_STATIC_SEED=fail` を出力します。allowlist 外の file、symlink、gitlink、実行可能
file、runtime/updater surface、network/secret marker、未解決 Codex role reference は、出力を
作る前に失敗します。

focused validation:

```bash
python3 -m unittest tests.agent_tools.test_export_static_seed -v
```
