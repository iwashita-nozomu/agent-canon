<!--
@dependency-start
contract skill
responsibility Places dependencies under the canonical Dockerfile-image-test structure.
upstream design ../../CONTAINER_OPERATIONS.md container ownership boundary
upstream design ./environment-maintenance.md expected environment structure owner
downstream implementation environment-maintenance.md consumes the dependency placement decision
downstream implementation ../../tools/runtime/container/devcontainer_dependencies.py optional typed build-input manifest validator
downstream implementation ../../tools/validation/dependencies/docker_dependency_validator.sh validates dependency placement
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

## Decision Route

For each requirement, identify only the commands and profiles it can affect.
Place dependencies needed by standard commands in the canonical Dockerfile
target; place optional capabilities in an image target selected by that
workflow; keep source, data, model, credential, driver, and device inputs
external. For image-owned dependencies, choose the provider, version or
immutable revision, lock/checksum, build stage, and runtime evidence. Check
Dev Container, Compose, CI, or lifecycle hooks for duplicate installation only
where they can reach that dependency. Keep the configured canonical full test
command as completion evidence when the selected change alters that image or
command. If implementation is in scope, pass the applicable placement decision
to `environment-maintenance`; otherwise return the decision to its caller.

## Placement Packet

次のうち、対象 dependency の判断に必要な情報を既存の decision record に残します。

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

Select only commands that establish the chosen placement or changed image
contract. Manifest validation applies when the typed build-input manifest is
used; image build and full-test execution apply when the canonical image or
command changes. These commands are not a fixed sequence for every decision.

```bash
python3 tools/runtime/container/devcontainer_dependencies.py validate --workspace . --vendor-root . --format text
python3 tools/runtime/container/devcontainer_dependencies.py dry-run --workspace . --vendor-root . --format json
bash tools/validation/dependencies/docker_dependency_validator.sh
docker build -f <Dockerfile> --target <canonical-target> -t <image> .
docker run --rm <runtime-wiring> <image> <canonical-full-test-command>
```

## Environment Maintenance Handoff

実装が作業範囲にある場合は、決定した placement を`environment-maintenance`へ渡します。
canonical image を変更する作業の completion owner は image の`docker run`による
repository標準テスト一式であり、manifest validationやpackage inventoryだけをcompletion
evidenceにしません。
