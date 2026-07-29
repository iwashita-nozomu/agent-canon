<!--
@dependency-start
contract skill
responsibility Defines and validates the declarative mounted devcontainer dependency design packet.
upstream design ../../documents/design/devcontainer/parent-dependency-manifest-followup.md parent follow-up contract
upstream design ../../CONTAINER_OPERATIONS.md product image and mounted tool ownership boundary
upstream implementation ../../tools/agent_tools/devcontainer_dependencies.py typed parser, merge, plan, and installer
downstream implementation environment-maintenance.md consumes the approved dependency design packet
downstream implementation ../../tools/docker_dependency_validator.sh validates the plan without installation
@dependency-end
-->

# Dependency Design

AgentCanon の mounted developer/agent tools を変更するときは、先にこの
skill で依存 design packet を閉じます。Docker product image/build/runtime、
parent の workspace Python installer、AgentCanon の mounted tooling を同じ
責務として扱いません。

## Tool Commands

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-design --format text
python3 tools/agent_tools/devcontainer_dependencies.py validate --workspace . --vendor-root . --format text
python3 tools/agent_tools/devcontainer_dependencies.py dry-run --workspace . --vendor-root . --format json
bash tools/docker_dependency_validator.sh
```

## Design packet

次を owner、replaceable unit、実装機構、validation route として記録します。

- fixed shell bootstrap が python3 + tomllib/tomli + python3-packaging、
  Node/npm 22.14.0 の arch-specific SHA256、ninja-build だけを確立すること
- parent manifest を先、vendor manifest を後に読み、standalone は自身を
  一度だけ読むこと
- record の closed method、必須 scalar、method-specific security fields、
  method-compatible typed verification、failure policy を定義すること
- duplicate merge の parent-value retention、compatible union、provider
  ambiguity、missing dependency、cycle の failure semantics
- full-plan validation と topological order が derived side effect より先に
  あること、fingerprint と owner-specific live verification の両方が pass
  した成功 receipt のみが rerun resume を可能にすること
- parent Python installer、AgentCanon build/cache/projection、parent final
  post-create の順序と ownership

Manifest を読むときは `tools/agent_tools/devcontainer_dependencies.py` の
`load_manifest`、`merge_records`、`build_plan` を正本として使います。manifest
文字列を eval せず、verification kind と method-specific field を closed
schema として検証します。
`--workspace .` は parent root を検査し、`vendor/agent-canon/` があれば
parent manifest を先、vendor manifest を後に読む。standalone AgentCanon では
同じコマンドが自身の manifest を一度だけ読むため、packet に `--vendor-root .`
を付けて二重読み込みにしません。

## Environment maintenance handoff

この packet が pass した後にだけ `environment-maintenance` を起動します。
環境変更の提案には manifest path、record inventory、merge/order evidence、
security fields、targeted validation を引き継ぎます。Docker build や実際の
package/network install はこの design route の validation に含めません。
