# environment-maintenance
<!--
@dependency-start
contract skill
responsibility Owns the expected Dockerfile-to-image-to-test structure for repository environments.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
upstream design ./gpu-execution.md canonical Docker device injection and exact GPU environment forwarding
downstream implementation ./dependency-design.md dependency placement under the expected structure
downstream implementation ./environment-cleanup.md environment cleanup route
downstream implementation ./devcontainer-exec.md targeted running-container execution boundary
downstream implementation ../../tests/agent_tools/test_environment_skill_expected_structure.py expected-structure contract
downstream implementation ../../tests/agent_tools/test_gpu_execution_docker_all_contract.py GPU wiring documentation regression contract
@dependency-end
-->

## Reader Map

- Purpose: Docker、CI、dependency、Dev Container の変更を、同じ canonical image
  から実行と検証が完結する構造へそろえます。
- Use When: runtime image、dependency、CI、Dev Container、Compose、container profile、
  environment compatibility guidance を変更するときに使います。
- Section path: Expected Structure を判断の起点にし、Required Change Fields、
  Operating Rules、Validation、Completion の順で閉じます。
- Boundary: source、data、model、credential、GPU driver/device などの runtime input は
  image 外に置けますが、標準環境の構築には使いません。

## Expected Structure

環境設計は次の完成状態から逆算します。

```text
Dockerfile -> canonical image -> docker run <canonical-full-test-command> -> pass
```

- Dockerfile の canonical target が、repository の標準実行・開発・検証commandに
  必要なOS package、language runtime、compiler、CLI、Python/Node等のdependency、
  shell/runtime設定を所有します。
- buildしたimageは、Feature、initialize、post-create、post-attach、host interpreter、
  mounted installer、workspace venv、previous container stateに依存せず、
  `docker run`からrepositoryの標準テスト一式を完了します。
- Dev Container、Compose、runtime pack、GitHub Actionsは同じimageを選択・build・runし、
  source/data mount、UID/GID、GPU/device、port、credential、secret、environment variable
  の配線だけを担当します。
- optional workflow capabilityが追加imageを必要とする場合も、そのworkflowが選ぶ
  Dockerfile/OCI image targetとして完成させます。container起動後のinstallへ逃がしません。

provider、manifest、Feature、lifecycle hook、Compose generatorなどの実装機構を選ぶ前に、
この期待構造とcanonical full test commandを確定します。

## Purpose

code requirementが必要とする環境capabilityをcanonical imageへ配置し、local、Dev Container、
CIで同じimageとtest commandを再利用できる状態にします。

## Use When

- Dockerfileやcontainer image targetを更新する
- dependency/runtime/toolchainを追加・更新・削除する
- CI、Dev Container、Compose、runtime packを変更する
- host/container/CIの責務分担を修正する
- Dockerfile外のinstallerやmutable environmentを除去する

## Core References

- `CONTAINER_OPERATIONS.md`
- `documents/contracts/github-first-module-and-devcontainer-policy.md`
- `documents/conventions/coding-conventions-project.md`
- project-owned `Dockerfile` / `docker/`
- `.devcontainer/`
- `.github/workflows/`
- `README.md`
- `agents/skills/dependency-design.md`
- `agents/skills/gpu-execution.md`

## Required Change Fields

- canonical image targetとprofile
- profileごとのcanonical full test command
- imageへ含めるruntime/build/test dependency
- image外に残すsource/data/model/credential/device等のruntime input
- Dev Container、Compose、CIが参照する同一image target
- Dockerfile外installerを削除する変更面
- validation commandとrollback

## Operating Rules

- dependencyの追加・移動・削除がある場合は、Expected Structureを固定したうえで
  `dependency-design`へ渡し、各dependencyのimage target、provider、version/lock、
  validation commandを決めます。
- 標準commandに必要なdependencyはDockerfile build時に導入します。
  typed manifestを使う場合もmanifestはbuild inputであり、runtime installerのownerにはしません。
- Dev Container Feature、initialize/post-create/post-attach、Compose generator、
  CI runner setup、shell startupからpackage manager、dependency resolver、venv生成、
  editable install、global tool installを実行しません。
- post-create等を残す場合は、image-owned stateとruntime wiringのread-only確認に限定し、
  その処理がなくても`docker run`の標準テスト一式は成功しなければなりません。
- local developer convenienceだけを理由にhost-global installやproject image外のbootstrapを
  canonical routeへ昇格させません。
- GPU imageはdeviceなしでbuild可能にします。GPU backend/deviceを必要とする標準テストは、
  GPU runner上で`gpu-execution`のadmission後に同じimageを
  `run_gpu_container.sh --image <image> -- <command...>`で起動します。callerはinjection方式を
  選ばず、同skillのwrapperがDocker daemonのexact CDI inventoryから個別CDIまたは
  `--gpus all`を内部選択し、full UUID visibilityと6個のexact environment値を同じrun argvへ
  渡します。
- Dockerfile、Dev Container、Compose、CI、READMEのimage targetとcommandを同じ変更でそろえます。
- 既存のrunning Dev Container内でcommandが通ることをenvironment acceptanceにしません。
  previous mutable stateを排除したimage build/runがacceptance ownerです。
- validation failureを解消するためにtest範囲やoracleを弱めません。imageに不足するcapabilityを
  Dockerfileへ戻すか、canonical commandの実責務が誤っていることをowner evidenceで修正します。

## Validation

```bash
python3 tools/ci/container_config.py
docker build -f <Dockerfile> --target <canonical-target> -t <image> .
docker run --rm <runtime-wiring> <image> <canonical-full-test-command>
```

- `container_config.py` はDockerfile、Dev Container、Compose、CIの静的なowner/target境界を検査します。
  completion evidenceは後続のimage buildと`docker run`による標準テスト一式です。
- supported profileごとに上記を実行します。
- GPU deviceを必要とするtestはGPU runner上で`gpu-execution`のcontainer smokeを実行し、
  container内のfresh JAX importとGPU backendを確認します。
- focused policy testで、Dockerfile外のdependency導入とDev Container/CIのalternate
  environment constructionを拒否します。
- 文書変更はrepositoryのcanonical docs checkで検証します。

## Completion

- canonical Docker imageをbuildできる。
- buildしたimageを`docker run`し、repositoryの標準テスト一式が追加setupなしで全て成功する。
- Dev Container、Compose、CIは同じimageを使用し、起動後にenvironmentを構築しない。

## Boundary

- 起動済みDev Container内のtargeted command実行は`devcontainer-exec`が所有します。
- 実験loop自体の運用は`adaptive-improvement-loop`または`research-workflow`を使います。
- 差分レビューは`change-review`を使います。
