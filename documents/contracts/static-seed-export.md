<!--
@dependency-start
contract reference
responsibility Defines static-seed ownership, producer input/output, source-free consumer validation, and forbidden surfaces.
upstream design ../../README.md AgentCanon source tree and consumer distribution boundary
upstream design ./README.md parent-repository contract index
upstream design ./static-seed-allowlist.toml sole exact-path allowlist for default consumers
downstream design ./template-bootstrap.md default source-free bootstrap contract
downstream implementation ../../tools/agent_tools/export_static_seed.py committed-tree exporter
downstream implementation ../../tools/docs/check_bootstrap_docs.py source-free consumer structure checker
downstream design ../tools/export_static_seed.md maintainer commands and failure semantics
downstream implementation ../../tests/agent_tools/test_export_static_seed.py producer determinism and exclusion tests
downstream implementation ../../tests/tools/test_check_bootstrap_docs.py source-hidden consumer and bootstrap regression tests
@dependency-end
-->

# Static Seed Export Contract

## 目的

AgentCanon は template 保守時の供給元として、通常の consumer repository が直接所有できる
静的な Codex configuration seed を生成します。生成後の default consumer は AgentCanon checkout、
CLI、source resolver、updater、同期状態、checkout secret、network access を必要としません。

producer export と default bootstrap の境界は次の通りです。

1. AgentCanon maintainer が committed source snapshot から seed を one-way export する。
1. template maintainer が output と provenance を regular file として review・commit する。
1. clone/bootstrap/CI/runtime は取り込まれた file を直接読み、再生成や上流探索を行わない。
1. live AgentCanon integration は別の explicit opt-in contract として扱う。

## 正本

静的 seed の file set は
[`static-seed-allowlist.toml`](static-seed-allowlist.toml) の exact path 列だけです。生成入口は
[`export_static_seed.py`](../../tools/agent_tools/export_static_seed.py) だけです。allowlist の path は
source と出力で同一とし、glob、directory copy、fallback、暗黙追加を使用しません。

allowlist は現在、次の consumer-owned regular file だけを含みます。

- `.codex/config.toml`
- `.codex/agents/<role>.toml`

consumer root instruction は project-owned content です。現行 live runtime を参照する source instruction
file を seed に混ぜません。

## Consumer-static role projection

35 個の role file は、単一の `agents/model_profiles.toml` を読む materializer の
in-memory `consumer-static` mode から生成します。live mode の
`developer_instructions` と executable role fields は変更せず、static mode だけが
producer path を source-neutral な clause と閉じた obligation fragment に置き換えます。
`generated_role_view_v1`、`generated_role_profile_projection_v1`、既存の TOML/JSON
field set、`projection_digest` は維持し、static TOML のコメントは schema marker と
digest だけに限定します。

materializer は `ConsumerStaticClauseProjection` と閉じた obligation table を検証し、
prose keyword 探索を行いません。exporter と consumer checker は全 payload bytes を
case-normalize して、`agents/skills/`、`agents/model_profiles.toml`、
`tools/agent_tools/`、`../../agents/`、`../../tools/` の exact prefix を拒否します。

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
全出力 file は mode `0644` の regular file であり、symlink、gitlink、out-of-tree reference を
作りません。

## Source-free Consumer Validation

export 後または consumer migration fixture では、AgentCanon source を不可視化して次を実行します。

```bash
python3 tools/docs/check_bootstrap_docs.py \
  --root <export-or-consumer-root> \
  --static-seed-consumer
```

checker は AgentCanon module や source resolver を import せず、出力 tree だけから次を確認します。

- provenance key、repository identity、source commit object ID
- `.codex/config.toml` と全 role file が non-symlink regular file であること
- role reference が `.codex/agents/<same-role>.toml` へ閉じ、未参照 role がないこと
- live checkout、runtime tool、update/sync state が存在しないこと
- seed payload に resolver、updater、network、source path marker がないこと

## 禁止 Surface

allowlist、exporter、consumer checker は次を拒否します。

- live AgentCanon checkout、gitlink、symlink、source mirror
- `documents/runtime/shared-runtime-surfaces.toml` とその他の source manifest
- AgentCanon CLI、dispatcher、source resolver、updater、latest checker
- update/sync transaction state と source manifest
- AgentCanon 内部の tests、notes、memory、evidence、reports、issues
- hook、MCP、command、URL、network access を構成する TOML key または内容
- token、credential、private key、checkout secret を示す path または内容
- allowlist にない tracked file、重複 path、非正規相対 path、実行可能 file

## Consumer 取り込み境界

Template maintainer は export 結果を通常の tracked file として review し、consumer tree の変更として
取り込みます。取り込み後の file は template/consumer が所有し、AgentCanon source への link や
runtime import を持ちません。

この契約は自動 publish、registry、package manager、bot、background update、derived repository への
同期を定義しません。再生成は maintainer が明示的に実行する一方向操作です。

Migration order は次で固定します。

1. AgentCanon static seed producer と source-free consumer contract を確定する。
1. consumer tree から live source ownership と projection を削除し、seed を regular file 化する。
1. canonical Makefile/CI/Docker command を project-owned surface へ切り替える。
1. bootstrap と descendant fresh-clone acceptance を source-hidden 状態で実行する。

この順序の途中で互換 symlink、代替 vendored runtime、automatic updater を追加しません。
