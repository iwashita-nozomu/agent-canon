<!--
@dependency-start
contract skill
responsibility Places dependencies under the canonical Dockerfile-image-test structure.
upstream design ../../CONTAINER_OPERATIONS.md container ownership boundary
upstream design ./environment-maintenance.md expected environment structure owner
downstream implementation environment-maintenance.md consumes the dependency placement decision
downstream implementation ../../tools/agent_tools/devcontainer_dependencies.py optional typed build-input manifest validator
downstream implementation ../../tools/docker_dependency_validator.sh validates dependency placement
downstream implementation ../../tests/agent_tools/test_environment_skill_expected_structure.py expected-structure contract
@dependency-end
-->

# Dependency Design

## Expected Structure

dependency designは次の完成状態を成立させるplacement decisionです。

```text
Dockerfile -> canonical image -> docker run <canonical-full-test-command> -> pass
```

標準実行・開発・検証commandが必要とするdependencyは、対応するDockerfile image targetが
所有します。Dev Container、Compose、CI、post-create、host setup、mounted workspaceは
dependency installerになりません。

## Workflow

1. supported profile、canonical image target、canonical full test commandを固定します。
1. commandが必要とするOS package、language runtime、compiler、library、CLI、
   test/build/docs toolを列挙します。
1. 各dependencyを次のいずれか一つへ配置します。
   - 標準commandに必要: canonical Dockerfile target
   - optional workflowに必要: workflowが明示選択するDockerfile/OCI image target
   - source/data/model/credential/GPU driver/device: runtime external input
1. image-owned dependencyはprovider、exact version/immutable revision、lock/checksum、
   build stage、runtime verificationを定義します。
1. Dev Container、Compose、CI、lifecycle hookが同dependencyを再導入しないことを確認します。
1. `environment-maintenance`へimage target、test command、dependency placement、
   runtime input、validationを渡します。

## Placement Packet

次を一つのdecisionとして記録します。

- dependencyのrequirement ownerとconsumer command
- canonical image target
- providerとexact version/immutable revision
- lock、checksum、またはpackage-manager identity
- Dockerfile build stageとruntime path
- canonical full test command
- external runtime inputとimage dependencyの区別
- Dev Container、Compose、CIが参照するimage target
- rollback

typed `.devcontainer/dependencies.toml` 等のmanifestを使う場合は、Dockerfile build時に読む
declarative inputとして扱います。manifest engine、receipt、provider closureはimage buildを
再現可能にする補助機構であり、mounted lifecycleやcontainer初回起動のinstall ownerにはしません。

## Rejected Structures

- Dev Container Featureが標準tool/dependencyを追加する
- initialize/post-create/post-attachがpackage install、venv生成、editable installを行う
- CI runnerがcanonical image外に別のtest environmentを構築する
- host Python/Node等でComposeやenvironmentを生成しないとimageを起動できない
- running containerの既存stateを標準テスト成功の前提にする
- source/data/credential mountをdependency installationへ流用する

## Tool Commands

manifestをbuild inputとして使う場合だけ、typed validationを実行します。

```bash
python3 tools/agent_tools/devcontainer_dependencies.py validate --workspace . --vendor-root . --format text
python3 tools/agent_tools/devcontainer_dependencies.py dry-run --workspace . --vendor-root . --format json
bash tools/docker_dependency_validator.sh
docker build -f <Dockerfile> --target <canonical-target> -t <image> .
docker run --rm <runtime-wiring> <image> <canonical-full-test-command>
```

## Environment Maintenance Handoff

placement packetがpassしたら`environment-maintenance`へ渡します。handoff後もcompletion ownerは
canonical imageの`docker run`によるrepository標準テスト一式であり、manifest validationや
package inventoryだけをcompletion evidenceにしません。
