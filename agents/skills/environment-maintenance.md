# environment-maintenance
<!--
@dependency-start
contract skill
responsibility Owns the expected Dockerfile-to-image-to-test structure for repository environments.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
upstream design ./gpu-execution.md ordinary GPU Docker execution and optional admission boundary
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

通常実行は共通入口の境界に従い、既存entrypointの設定と標準ツールの既定値を
そのまま使います。利用者への環境選択要求や、agentによる場当たり的な環境フラグ・
環境変数・設定の手動上書きを行いません。
新しいtask/session、CPU/GPUの利用、任意設定の未確認だけで環境判定や本Skillを
起動しません。環境変更が依頼範囲にある場合だけ、Required Change Fields以降の
構築・acceptanceを適用します。実失敗の限定調査から、setup・修復・未使用profileや
設定項目の補完を自動的に追加せず、通常実行の前提にも戻しません。

AgentCanon source is the exception to project-local Dev Container discovery:
its Python/Rust/LSP dependencies belong to the shared image built by
`bootstrap.sh` and `bootstrap/`. A parent project may keep its own
`.devcontainer/`, but that directory is never an AgentCanon dependency or
fallback.

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
- Dev Container、Compose、runtime pack、GitHub Actionsは project-owned image/layer を
  選択・build・runし、source/data mount、UID/GID、GPU/device、port、credential、secret、
  environment variable の配線だけを担当します。これは AgentCanon の shared toolresident
  とは別の execution plane です。project 側で image/layer を再利用しても container は
  product と toolresident を兼用しません。
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

- [CONTAINER_OPERATIONS.md](../../CONTAINER_OPERATIONS.md)
- [documents/contracts/github-first-module-and-devcontainer-policy.md](../../documents/contracts/github-first-module-and-devcontainer-policy.md)
- [documents/conventions/coding-conventions-project.md](../../documents/conventions/coding-conventions-project.md)
- project-owned `Dockerfile` / `docker/`
- `bootstrap.sh` / `bootstrap/`
- project-owned `.devcontainer/` when the parent explicitly provides one
- `.github/workflows/`
- `README.md`
- [agents/skills/dependency-design.md](dependency-design.md)
- [agents/skills/gpu-execution.md](gpu-execution.md)

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
- GPU imageはdeviceなしでbuild可能にします。GPUを必要とする標準テストは、
  [gpu-execution](gpu-execution.md)に従い、空いているGPUを指定して同じimageを
  `docker run --rm --gpus device=<selected-GPU> <image> <command...>`で起動します。
  通常実行に専用admissionやJAX/XLA設定を要求せず、排他予約が必要な場合だけ
  同skillの任意経路を選びます。
- Dockerfile、Dev Container、Compose、CI、READMEの project image target と command を同じ変更でそろえます。
- Project runners reuse the image tag selected by the current environment owner and
  runtime pack across checkouts. They perform one native local-tag presence lookup;
  a missing tag is built with the builder's normal cache, while an explicit
  build/update request uses that same cache unless the caller selected `--no-cache`.
  Ordinary runs do not create task-specific image tags, attach task lifecycle
  labels to shared images, or remove/retag the selected image. The run container
  is disposable (`docker run --rm` / equivalent); the selected image remains.
- Image selection belongs to the existing project entrypoint and runtime-pack
  configuration, not per-task manual overrides. Same Dockerfile text, source-tree
  hashes, registry provenance, and daemon preflight/snapshot comparisons are not
  substitutes for the configured runtime-pack image tag.
- 既存のrunning Dev Container内でcommandが通ることをenvironment acceptanceにしません。
  previous mutable stateを排除したimage build/runがacceptance ownerです。
- validation failureを解消するためにtest範囲やoracleを弱めません。imageに不足するcapabilityを
  Dockerfileへ戻すか、canonical commandの実責務が誤っていることをowner evidenceで修正します。

## Validation

変更した環境のownerに沿って検証します。以下のbootstrap例とlifecycle readbackは
AgentCanon tool runtimeのimage/lifecycle変更に限ります。project環境の変更は
project-owned build/runと該当profileのcanonical full testで検証し、AgentCanon
bootstrapを前提にしません。文書のみの変更は文書・参照整合の検証に限定し、
image buildや実機acceptanceを実施したとは報告しません。

```bash
./bootstrap.sh --control-parent-root <root> --runtime-root <runtime> install
./bootstrap.sh --control-parent-root <root> --runtime-root <runtime> start
./bootstrap.sh --control-parent-root <root> --runtime-root <runtime> status
```

- bootstrap container contract testと実lifecycle readbackをcompletion evidenceにします。
- 変更の影響を受けるsupported profileを検証します。未使用profileの整備を開始条件にしません。
- GPU deviceを必要とするtestはGPU runner上で実行し、対象commandが実際にGPU backendを
  使用したことを確認します。JAXのbackend確認はJAXを使用する場合だけ行います。
- focused policy testで、Dockerfile外のdependency導入とDev Container/CIのalternate
  environment constructionを拒否します。
- 文書変更はrepositoryのcanonical docs checkで検証します。

## Completion

以下は環境実装を変更した場合の終了条件であり、通常実行や文書のみの変更には適用しません。

- canonical Docker imageをbuildできる。
- buildしたimageを`docker run`し、repositoryの標準テスト一式が追加setupなしで全て成功する。
- Dev Container、Compose、CIは同じimageを使用し、起動後にenvironmentを構築しない。

## Boundary

- 起動済みDev Container内のtargeted command実行は`devcontainer-exec`が所有します。
- 実験loop自体の運用は`adaptive-improvement-loop`または`research-workflow`を使います。
- 差分レビューは`change-review`を使います。
