# environment-cleanup
<!--
@dependency-start
contract skill
responsibility Removes alternate environment construction and restores the canonical image-test structure.
upstream design ./README.md shared public skill canon
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ./dependency-design.md dependency placement owner
upstream design ./environment-maintenance.md expected environment structure owner
upstream design ./responsibility-cleanup.md responsibility-unit dispatch owner
downstream implementation ../../.agents/skills/environment-cleanup/SKILL.md runtime discovery shim
downstream implementation ./catalog.yaml public skill registry
downstream implementation ./skill-dependencies.yaml public skill dependency DAG
downstream implementation ../../.codex/config.toml host skill configuration
downstream implementation ../../tests/agent_tools/test_environment_skill_expected_structure.py expected-structure contract
@dependency-end
-->

## Purpose

Dockerfile外に分散したdependency install、venv生成、Feature、host bootstrap、
post-create lifecycleを除去し、次の期待構造へ戻します。

```text
Dockerfile -> canonical image -> docker run <canonical-full-test-command> -> pass
```

## Use When

- Docker、CI、Dev Container、Compose、dependency manifestを整理する
- container起動後のinstallやworkspace-local environmentを除去する
- host/CI/Dev Containerに分散したtoolchainをcanonical imageへ統合する
- runtime capabilityのownerとfull test routeを一本化する

## Route

1. `environment-maintenance`のExpected Structureとcanonical full test commandを固定します。
1. `dependency-design`で全dependencyをDockerfile image targetまたは明示的runtime inputへ配置します。
1. Feature、initialize/post-create/post-attach、runner setup、mounted installer等のalternate
   environment constructionを削除します。
1. Dev Container、Compose、CIを同じimage targetのbuild/runへ接続します。
1. imageをbuildし、`docker run`からrepositoryの標準テスト一式を実行します。

## Tool Commands

```bash
bash tools/docker_dependency_validator.sh
docker build -f <Dockerfile> --target <canonical-target> -t <image> .
docker run --rm <runtime-wiring> <image> <canonical-full-test-command>
```

typed manifestがDockerfile build inputとして残る場合だけ、そのvalidatorを追加実行します。

## Completion

- canonical Docker imageをbuildできる。
- buildしたimageを`docker run`し、repositoryの標準テスト一式が追加setupなしで全て成功する。
- Dev Container、Compose、CIにalternate dependency installerが残らない。

## Boundary

environment policyは`environment-maintenance`、dependency placementは`dependency-design`が所有します。
このskillはcleanup unitとvalidation routeを接続し、別のenvironment schemaを定義しません。
