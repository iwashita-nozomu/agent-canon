<!--
@dependency-start
contract reference
responsibility template consumer向け静的seedの所有境界、生成入力、出力、禁止surfaceを定義する。
upstream design ../../README.md AgentCanon source treeとconsumer配布境界。
upstream design ./README.md 親レポ利用契約の索引。
upstream design ./static-seed-allowlist.toml template consumerへ供給する唯一のexact-path allowlist。
downstream implementation ../../tools/agent_tools/export_static_seed.py committed Git treeからseedを生成する唯一のentrypoint。
downstream design ../tools/export_static_seed.md maintainer向けcommandと失敗条件。
downstream implementation ../../tests/agent_tools/test_export_static_seed.py 決定性、禁止surface、source-hidden fixtureを検証する。
@dependency-end
-->

# Static Seed Export Contract

## 目的

AgentCanon は template 保守時の供給元として、通常の consumer repository が直接所有できる
静的な Codex configuration seed を生成します。生成後の consumer は AgentCanon checkout、
submodule、CLI、source resolver、updater、同期状態、checkout secret、network access を
必要としません。

この契約は producer 側の export だけを所有します。default template/bootstrap 契約の切替、
既存 submodule・symlink・updater の撤去、派生 repository への移行は #712 および
`iwashita-nozomu/project_template` #165–#167 が所有します。

## 正本

静的 seed の file set は
[`static-seed-allowlist.toml`](static-seed-allowlist.toml) の exact path 列だけです。
生成入口は
[`export_static_seed.py`](../../tools/agent_tools/export_static_seed.py) だけです。
allowlist の path は source と出力で同一とし、glob、directory copy、fallback、暗黙追加を
使用しません。

allowlist は現在、次の consumer-owned regular file だけを含みます。

- `.codex/config.toml`
- `.codex/agents/<role>.toml`

`AGENTS.md` / `ROOT_AGENTS.md` は現行 source tree の live AgentCanon runtime 契約を参照するため、
この seed には含めません。consumer root instruction の移行は #712 の責務です。

## 生成規則

maintainer は source commit を明示して export します。

```bash
python3 tools/agent_tools/export_static_seed.py \
  --source-root . \
  --source-ref <agent-canon-commit> \
  --output <fresh-output-directory>
```

entrypoint は network access を行わず、次の順で一つの immutable plan を作ります。

1. `source-ref` を local Git object database 内の commit に解決する。
1. 同じ commit の tree から canonical allowlist を読む。
1. allowlist の各 path が mode `100644` の tracked blob であることを確認する。
1. blob bytes を worktree ではなく commit object から読む。
1. 全 file と Codex role reference を検証してから、存在しない出力 directory へ通常 file として書く。

同一 commit と同一 allowlist から得る file bytes、path、mode、provenance は一意です。時刻、
worktree dirty state、remote state、environment-specific path、乱数は出力へ入りません。

## 出力

出力は allowlist の file と `agent-canon-static-seed.json` だけです。provenance は次の最小情報だけを
持ちます。

- schema version
- canonical source repository identity
- source commit object ID

時刻、branch、remote URL、latest 判定、更新履歴、consumer sync state は記録しません。
全出力 file は mode `0644` の regular file であり、symlink、gitlink、submodule、out-of-tree
reference は作りません。

## 禁止 surface

allowlist と exporter は次を拒否します。

- `vendor/agent-canon` を含む checkout、gitlink、submodule、symlink
- `tools/`、AgentCanon CLI、dispatcher、source resolver、updater、latest checker
- `.agent-canon/`、source manifest、sync/update state
- AgentCanon 内部の `tests/`、`notes/`、`memory/`、`evidence/`、`reports/`、`issues/`
- hook、MCP、command、URL、network access を構成する TOML key または内容
- token、credential、private key、checkout secret を示す path または内容
- allowlist にない tracked file、重複 path、非正規相対 path、実行可能 file

## Consumer 取り込み境界

`project_template` maintainer は export 結果を通常の tracked file として review し、template
repository の変更として取り込みます。取り込み後の file は template/consumer が所有し、
AgentCanon source への link や runtime import を持ちません。

この契約は自動 publish、registry、package manager、bot、background update、derived repository
への同期を定義しません。再生成は maintainer が明示的に実行する一方向操作です。
