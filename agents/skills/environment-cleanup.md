# environment-cleanup
<!--
@dependency-start
contract skill
responsibility Removes alternate environment construction and superseded environments through existing owners.
upstream design ./README.md shared public skill canon
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ./dependency-design.md dependency placement owner
upstream design ./environment-maintenance.md expected environment structure owner
upstream design ./responsibility-cleanup.md responsibility-unit dispatch owner
downstream implementation ../../.codex/personal/skills/environment-cleanup/SKILL.md runtime discovery shim
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

環境の再構築・置換では、旧環境の実体と専用資源の削除まで同じ作業で閉じます。

## Use When

- Docker、CI、Dev Container、Compose、dependency manifestを整理する
- container起動後のinstallやworkspace-local environmentを除去する
- host/CI/Dev Containerに分散したtoolchainをcanonical imageへ統合する
- runtime capabilityのownerとfull test routeを一本化する
- 環境を再構築・置換し、旧環境を廃棄する

## Route

対象が alternate installer や lifecycle setup の削除なら、その実在する owner と
affected consumers を確認し、変更した construction path の除去を read back します。
dependency の配置が変わる場合だけ `dependency-design` を使い、image target や
command を変える場合だけその consumer を `environment-maintenance` の同じ contract
へ移行します。canonical image を置換・再構築する作業では、その image を build して
`docker run` から repository 標準テストを実行し、廃棄は[Rebuild cleanup](#rebuild-cleanup)
の exact-target route で完了します。

## Rebuild cleanup

再構築・置換時は、対象環境の既存build/run・停止・削除経路で次を実施します。
通常実行には適用せず、廃棄のためだけにdependency設計や全profile検証をやり直しません。

1. 既存の設定・管理情報から、置換する旧環境と新環境のexact ID/path、専用資源、
   共有資源、必要データの移行先を特定します。imageはtag書換え前のIDも保持し、
   新環境が再利用する同一image・共有layer等を旧環境の専用資源と混同しません。
   対象外の環境まで棚卸ししません。
1. 必要データを移行し、使用中の処理・参照を切り替えるか安全に停止してから、
   旧container/image、専用volume/network、venv/install tree、旧登録・リンクなど、
   対象に実在する旧環境の実体と専用資源を削除します。共有資源・利用者データ・
   他者所有物を巻き込む一括pruneやdirectory丸ごとの削除は行いません。
1. 停止、改名、別directoryへの退避、backup/rollback用の温存を削除扱いにせず、
   後続taskやGC待ちへ先送りしません。復旧は正本から再構築し、旧環境の実体を残しません。
   失敗した候補環境のtask専用残骸も同じcleanupで削除します。
1. 対象のexact ID/pathと旧参照・登録を読み戻し、不在を確認します。新環境の正常稼働や
   tagの切替だけでは削除証拠になりません。削除失敗・残存・権限不足は再構築未完了とし、
   対象、実行結果、原因、次操作を既存task/Issueへ記録して該当ownerで解消します。
   記録だけで完了にせず、新しいchecker・schema・cleanup wrapperも追加しません。

## Tool Commands

Run only commands that prove the changed placement or image contract. The
dependency validator applies when dependency placement changes; image build and
full-test execution apply to an image replacement. Typed manifest validation
applies only when that manifest remains a build input.

```bash
bash tools/validation/dependencies/docker_dependency_validator.sh
docker build -f <Dockerfile> --target <canonical-target> -t <image> .
docker run --rm <runtime-wiring> <image> <canonical-full-test-command>
```

typed manifestがDockerfile build inputとして残る場合だけ、そのvalidatorを追加実行します。

## Completion

For an image replacement, the canonical image builds and its configured
`docker run` test command passes without extra setup. For a narrower cleanup,
read back the affected alternate construction paths and run the selected
validation. Any rebuild or replacement also requires exact old-environment and
exclusive-resource deletion and absence readback as described above.

## Boundary

environment policyは`environment-maintenance`、dependency placementは`dependency-design`が所有します。
このskillはcleanup unitとvalidation routeを接続し、別のenvironment schemaを定義しません。
