<!--
@dependency-start
contract reference
responsibility Documents deterministic static-seed export and source-free consumer validation commands.
upstream implementation ../../tools/agent_tools/export_static_seed.py owns producer export.
upstream implementation ../../tools/docs/check_bootstrap_docs.py owns source-free consumer validation.
upstream design ../contracts/static-seed-export.md owns seed content and consumer boundaries.
upstream design ../contracts/static-seed-allowlist.toml owns the sole exact-path allowlist.
downstream implementation ../../tests/agent_tools/test_export_static_seed.py exercises producer export.
downstream implementation ../../tests/tools/test_check_bootstrap_docs.py exercises source-hidden consumer validation.
@dependency-end
-->

# Static Seed Commands

## Export

一つの AgentCanon commit から default template consumer 向け static seed を生成します。出力先は
存在していない directory を指定します。

```bash
python3 tools/agent_tools/export_static_seed.py \
  --source-root . \
  --source-ref "$(git rev-parse HEAD)" \
  --output /tmp/agent-canon-static-seed
```

command は local Git object database だけを読み、fetch、clone、HTTP、SSH、secret を使用しません。
allowlist と payload は同じ commit から読みます。worktree file を直接 copy しないため、未 commit の
変更は出力へ混入しません。

成功時は `AGENT_CANON_STATIC_SEED=exported`、失敗時は
`AGENT_CANON_STATIC_SEED=fail` を出力します。allowlist 外の file、symlink、gitlink、実行可能 file、
runtime/updater surface、network/secret marker、未解決 Codex role reference は、出力を作る前に
失敗します。

## Validate a Source-free Consumer

export 結果または consumer migration fixture から AgentCanon source を隠した状態で実行します。

```bash
python3 tools/docs/check_bootstrap_docs.py \
  --root /tmp/agent-canon-static-seed \
  --static-seed-consumer
```

この経路は source module を import せず、provenance、regular file、role reference closure、禁止 runtime
surface の不在だけを consumer tree から検証します。成功時は
`Static seed consumer check passed` を出力します。

focused validation:

```bash
python3 -m unittest tests.agent_tools.test_export_static_seed -v
python3 -m unittest tests.tools.test_check_bootstrap_docs -v
```
