# environment-maintenance
<!--
@dependency-start
contract skill
responsibility Owns the expected Dockerfile-to-image-to-test structure for repository environments.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
downstream implementation ./dependency-design.md dependency placement under the expected structure
downstream implementation ./environment-cleanup.md environment cleanup route
downstream implementation ./devcontainer-exec.md targeted running-container execution boundary
downstream implementation ../../tests/agent_tools/test_environment_skill_expected_structure.py expected-structure contract
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

### Non-template standard route

非テンプレート repository の standard route は、target repository Git root を current
directory として、次の command pair を exact に実行する状態から逆算します。

```text
docker build -f docker/Dockerfile -t <rootrepo> .
docker run --rm <rootrepo> testrunner.sh
```

- `<rootrepo>` は target repository Git root から決まる image name/tag であり、build と run
  は同じ値を使います。build context は `.`、Dockerfile は `docker/Dockerfile`、run command
  は `testrunner.sh` です。
- `docker/Dockerfile` は standard suite に必要な OS、language runtime、compiler、CLI、
  source、tests、`test/testrunner.sh`、`test/testlist.toml`、build/test dependency を
  image に含めます。standard route は runtime mount を必要としません。
- `test/testrunner.sh` は `test/testlist.toml` の ordered command token arrays を読み、
  repository standard full-test suite を完了させる public runner です。caller は runner
  の内部 test path や `testlist.toml` を名前指定・読み取りしません。
- parent/vendor caller は dependency/vendor の Git root へ移動してこの pair を実行し、
  repo-owned public `testrunner.sh` だけを呼び出します。target repository Git root 以外
  からの実行や internal test path の直接実行は standard route ではありません。
- standard acceptance の completion evidence は、build 成功後の exact `docker run` が
  exit code `0` になることです。host/runtime setup、dependency install、virtualenv、
  editable install、host-side test、既存 container の再利用は根拠にしません。

### Standard invariants

- `docker/Dockerfile` は standard suite の dependency、runner、test list、必要な source/tests
  を image に含めます。host は image dependency を補完しません。
- `test/testlist.toml` は `#` comment を許す TOML とし、各 `[[tests]]` entry に unique stable
  `id`、`environment`（`tooling` または `product`）、repo-relative `code_owner`、nonempty
  `responsibility_scope`、`require`（`docker` または `devcontainer`）、ordered nonempty
  token-array `command` を持たせます。

```toml
[[tests]]
id = "stable-test-id"
environment = "tooling" # or "product"
code_owner = "path/or/owner-reference"
responsibility_scope = "non-empty responsibility description or reference"
require = "docker" # or "devcontainer"
command = ["program", "--ordered", "tokens"]
```

- Docker route は `active_route=docker` として `require=docker` entry だけを順序どおり実行し、
  Dev Container route は `active_route=devcontainer` として `require=devcontainer` entry だけを
  実行します。`not_selected` iff `active_route != require`; 他の選択条件を参照せず、他 route を
  失敗させません。
- runner は各 entry に `start`、`pass`、`fail`、`not_selected` の result を出し、id、exact
  argv、environment（`tooling` または `product`）、`code_owner`、`responsibility_scope`、
  `require`、`active_route`、status、exit code を含めます。`active_route == require` の entry
  だけが selected となり、success は selected entry が1件以上あり、selected entry がすべて
  pass した場合だけです。malformed、duplicate、unsupported contract は failure にします。

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

## Required Change Fields

- target repository Git root と `<rootrepo>` image name/tag
- `docker/Dockerfile` が所有する source、tests、`test/testrunner.sh`、`test/testlist.toml`、
  standard-test dependency
- `test/testlist.toml` の各 `[[tests]]` entry にある unique stable `id`、`environment`、
  repo-relative `code_owner`、nonempty `responsibility_scope`、`require`、ordered nonempty
  token-array `command`
- Docker route と Dev Container route が選択する `require` 値、`active_route`、および
  start/pass/fail/not_selected result receipt の id、exact argv、environment、owner、scope、
  require、status、exit
- host/runtime setup、duplicate host full test、optional GPU/special check の追加範囲
- exact standard command pair と validation command、rollback

## Operating Rules

- dependencyの追加・移動・削除がある場合は、Expected Structureを固定したうえで
  `dependency-design`へ渡し、各dependencyのimage target、provider、version/lock、
  validation commandを決めます。
- standard suite に必要な dependency、runner、test list、source、tests は
  `docker/Dockerfile` の build時に導入・copy・buildします。typed manifestを使う場合も
  manifestはbuild inputであり、runtime installerのownerにはしません。
- Dev Container Feature、initialize/post-create/post-attach、Compose generator、
  CI runner setup、shell startupからpackage manager、dependency resolver、venv生成、
  editable install、global tool installを実行しません。
- post-create等を残す場合は、image-owned stateとruntime wiringのread-only確認に限定し、
  その処理がなくても `docker run --rm <rootrepo> testrunner.sh` の標準テスト一式は成功
  しなければなりません。
- local developer convenienceだけを理由にhost-global installやproject image外のbootstrapを
  canonical routeへ昇格させません。
- parent/vendor caller は target repository または vendor の Git root へ `cd` して、次の
  pair だけを実行します。

  ```text
  docker build -f docker/Dockerfile -t <rootrepo> .
  docker run --rm <rootrepo> testrunner.sh
  ```

  caller は public `testrunner.sh` だけを呼び、internal test path や `test/testlist.toml`
  を直接指定・読み取りしません。
- standard pair は image build 後の fresh `docker run` で完結し、runtime/host setup、
  dependency install、virtualenv、editable install、host-side canonical/full test、既存
  container や mutable state の再利用を acceptance evidence にしません。
- `tests/agent_tools` mount はこの契約の requirement にせず、optional runtime mount を
  一律禁止しません。optional mount の意味は repository owner が選び、runner、test list、
  source、tests、standard-test dependency の image-owned boundary を保ちます。
- optional GPU check と repository 固有の special check は standard pair の後または追加の
  evidence として実行できますが、standard pair の省略・置換・成功条件の緩和には使いません。
- Template repository はこの non-template contract の適用範囲から除外します。
- validation failureを解消するためにtest範囲やoracleを弱めません。imageに不足するcapabilityを
  Dockerfileへ戻すか、public runnerの実責務が誤っていることをowner evidenceで修正します。

## Validation

```bash
docker build -f docker/Dockerfile -t <rootrepo> .
docker run --rm <rootrepo> testrunner.sh
```

- command pair は target repository Git root を current directory として、同じ `<rootrepo>`
  image name/tag で実行します。Dockerfile、context、runner、test list、source、tests、
  standard-test dependency が image 側にあることを確認します。
- `testrunner.sh` の result receipt は各 entry の id、exact argv、environment（`tooling` または
  `product`）、`code_owner`、`responsibility_scope`、`require`、`active_route`、status、exit
  code と `start`、`pass`、`fail`、`not_selected` を含めます。`active_route != require` の
  entry は `not_selected` となり、selected entry が1件以上あり、selected entry がすべて
  pass した場合だけ standard acceptance を成功にします。
- malformed、duplicate、unsupported `require`、target repository Git root 以外からの実行、
  exact command pair からの drift は contract failure として扱います。first または aggregate
  failure semantics を保持し、failure を別の成功状態へ再分類しません。
- `docker run --rm <rootrepo> testrunner.sh` の exit code `0` が standard full-test completion
  evidence です。host/runtime setup、依存関係の再構築、host-side canonical/full test、既存
  container の結果を成功根拠にしません。
- focused policy testで、Dockerfile外のdependency導入、public runnerを迂回する internal test
  path/list 呼び出し、duplicate host full test、standard pair を置換する optional check を拒否します。
- 文書変更はrepositoryのcanonical docs checkで検証します。

### Failure semantics

- Template repository は `scope_excluded` とし、non-template standard route の成功条件を適用しません。
- `docker/Dockerfile`、`test/testrunner.sh`、`test/testlist.toml` の欠落、target repository
  Git root 以外からの実行、exact command pair からの drift は `contract_missing` / blocked
  とします。
- Dockerfile が standard-test dependency、runner、test list、source、tests を image に含めず
  host/runtime setup が必要になる場合は `image_contents_boundary_violation` / fail-closed
  とします。
- `testrunner.sh` が selected full suite を完了しない、selected entry が0件、selected entry
  が fail する、または standard run が `0` 以外になる場合は `acceptance_failed` とします。
- malformed、duplicate、unsupported `require` は contract failure とし、optional GPU/special
  check の失敗は追加 check の finding として記録します。追加 check は standard pair の
  実行を省略する理由になりません。

## Completion

- canonical Docker imageをbuildできる。
- target repository Git root から `docker build -f docker/Dockerfile -t <rootrepo> .` を成功させ、
  同じ `<rootrepo>` に対して `docker run --rm <rootrepo> testrunner.sh` を実行できます。
- Dockerfile は runner、TOML test list、必要な source/tests、standard-test dependency を含み、
  caller は public `testrunner.sh` だけを呼びます。internal test path や test list の直接指定、
  runtime/host install、duplicate host full test は completion evidence になりません。
- `test/testlist.toml` の selected entry が1件以上あり、Docker route または Dev Container route
  の対応 `require` entry がすべて pass し、全 result receipt に必要な id、argv、environment、
  owner、scope、require、`active_route`、status、exit を記録します。`active_route != require` の
  entry は `not_selected` になります。
- standard full-test run の exit code `0` と、optional GPU/special check が standard pair を
  置換せず追加 evidence として扱われることを確認できます。
- Template repository と template issue `#163` はこの non-template contract の対象外です。

## Boundary

- 起動済みDev Container内のtargeted command実行は`devcontainer-exec`が所有します。
- 実験loop自体の運用は`adaptive-improvement-loop`または`research-workflow`を使います。
- 差分レビューは`change-review`を使います。
