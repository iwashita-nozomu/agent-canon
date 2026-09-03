# AgentCanon Bootstrap And Tool Runtime
<!--
@dependency-start
contract design
responsibility Defines the host bootstrap, shared AgentCanon tool runtime, external artifact boundary, skill installation, eval publication, and migration contract.
upstream design ../../README.md standalone AgentCanon source entrypoint and user journey
upstream design ../runtime/runtime-log-archive.md agent-canon-log publication and append-only archive policy
upstream design ../../agents/skills/agent-canon-update.md AgentCanon source and parent integration workflow
upstream implementation ../../tools/runtime/container/devcontainer_dependencies.py reusable dependency planning and image installation logic
upstream implementation ../../tools/runtime/archive/runtime_log_archive_git.py existing archive publication owner
downstream implementation ../../bootstrap.sh host bootstrap entrypoint
downstream implementation ../../bootstrap/container/image/Dockerfile shared Python and Rust tool image
downstream implementation ../../tools/runtime/container/bootstrap_runtime.py resident container lifecycle and mount registry
downstream implementation ../../tools/runtime/artifacts/runtime_artifacts.py external runtime artifact boundary
downstream implementation ../../tools/runtime/dispatch/tool_dispatch.py catalog-namespaced Python and Rust dispatcher
downstream implementation ../../tests/bootstrap/test_bootstrap_runtime.py bootstrap lifecycle and compatibility tests
@dependency-end
-->

この文書は `iwashita-nozomu/agent-canon#841` の実装正本です。
`iwashita-nozomu/agent-canon#821` は prebuilt artifact の build / distribution
だけを所有し、この文書は local bootstrap、tool runtime、skill、eval、cleanup を
所有します。Template の source-free 化は下流の別 PR とし、AgentCanon merge 後に
実施します。

## Reader Map

- Host は Skill、`AGENTS.md`、workflow shell、Git、GitHub、Docker、Codex 起動を所有する。
- 共有 tool container は AgentCanon の Python / Rust / LSP tool だけを実行する。
- project build / test / experiment / GPU は project-owned execution environment が所有する。
- runtime lifecycle state は bootstrap-owned で ignored な `<install-root>/.runtime/` に置く。
  一般の eval、report、SQLite、log、analysis、archive artifact は source tree 外に置く。
- public command の互換性、resource lifecycle、eval publication、skill discovery を
  完了条件に含める。

## Responsibility Boundary

```text
Host
  bootstrap.sh
  AGENTS.md / Skills / workflow shell
  Git / GitHub / Docker / Codex adapters
            |
            v
Shared AgentCanon Tool Container (maximum one)
  Rust CLI / Python tools / LSP / static analysis
            |
            +-- external runtime root
            +-- allowlisted repository mounts

Project Execution Environment
  project Dockerfile / testrunner / product dependencies
```

Tool container に Docker socket、SSH agent、GitHub token、host `$HOME` を mount
しません。Host adapter は operation allowlist から選び、任意 shell を実行しません。
secret value、authorization header、credential path を stdout、receipt、eval、log に
記録しません。

## Runtime And Cache Roots

Bootstrap は `--control-parent-root` を必須とし、install root の ignored
`.runtime/` を persistent runtime として使います。これは bootstrap が所有する
唯一の source-local state で、完全に再構築可能です。`--runtime-root` は旧 default
の migration input としてのみ解釈し、新しい state の配置を変更しません。一般の
eval/report/SQLite/log/analysis artifact は source tree 外の declared runtime root
に残し、`$HOME/.local`、`$HOME/.cache`、その他の source-tree fallback は使いません。
外部 private log checkout は常に `<install-root-parent>/agent-canon-log` であり、
control-plane root は認可だけを担います。

control-plane root は installation に一つだけで、project root ではありません。
複数 project は同じ `mounts.toml` に target として登録し、同じ container ID
と image digest を使います。新しい control root から二個目を作らず、
Docker label readback で既存 owner を検出し、`shared_runtime_owned_elsewhere` と
既存 control root の明示指定を返します。

```text
<install-root>/.runtime/
  current-generation
  rollback-generation
  lifecycle.lock
  mounts.toml
  codex-home/
  tasks/<task-id>/{tmp,locks,reports,logs,receipts}
  container-runtime/  # 01777 exchange only; no control state or credentials
  source-sync/source-sync.json  # host-written, resident read-only view
  spool/

<install-root>/.runtime/cache/{cargo,pycache,semantic-index,tool-metadata}/
```

Bootstrap lifecycle codeだけが固定された `.runtime/` surfaces を直接管理します。
`tools/runtime/artifacts/runtime_artifacts.py` は source-local artifact を例外なく拒否し、
分析 tool は source read-only、telemetry は external root、mutation tool は明示 target
capability を受けた場合だけ source を変更します。

## Top-Level Bootstrap

唯一の入口は repository top-level `bootstrap.sh` です。

```bash
./bootstrap.sh --control-parent-root <path> install
./bootstrap.sh --control-parent-root <path> update
./bootstrap.sh --control-parent-root <path> start
./bootstrap.sh --control-parent-root <path> status
./bootstrap.sh --control-parent-root <path> target add --root <project-a> --mode read-only
./bootstrap.sh --control-parent-root <path> target add --root <project-b> --mode read-only
./bootstrap.sh --control-parent-root <path> tool run <catalog-id> -- <args...>
./bootstrap.sh --control-parent-root <path> template export --root <registered-source> --profile <profile> --output <runtime-relative-directory>
./bootstrap.sh --control-parent-root <path> codex prepare
./bootstrap.sh --control-parent-root <path> codex --project-root <path>
./bootstrap.sh --control-parent-root <path> eval collect --root <path> --run-id <id>
./bootstrap.sh --control-parent-root <path> eval sync --run-id <id>
./bootstrap.sh --control-parent-root <path> stop
./bootstrap.sh --control-parent-root <path> rollback
./bootstrap.sh --control-parent-root <path> gc
./bootstrap.sh --control-parent-root <path> uninstall
```

コマンドを実行する cwd は runtime の選択に使わず、cwd に関する warning は出しません。
経路は `cwd -> bootstrap.sh -> install root -> control root ->
<install-root>/.runtime/ -> resident container` です。`install` は検証済み image と
resident を作り、`update` は同じ resident を current checkout へ更新し、`status` は
`.runtime/` の active image と resident health を読み返します。`sync` は
`replacement.lock` を一度だけ取得し、`git -C <install-root> pull --ff-only origin main`
の成功後に source-sync state と env-key image を選び、必要な場合だけ resident、
global links、timer を更新します。Git は detached/shallow checkout を含め、pull が
受理した結果だけを信頼します。
`gc --dry-run` は
`.runtime/` の準備・作成・chmod をせずに同じ identity/ownership read を行い、`gc` は
replacement lock の下で stale な owned Docker resource だけを exact ID/reference で
削除します。resident controller の既存 `runtime.gc/state GC` も継続して呼び出し、host
Docker の結果と一つの receipt に結合します。

Bootstrap はホストの Python / Cargo install へ fallback しません。Host
`bootstrap/host/lifecycle/entrypoint.sh` は Docker/Git の argv adapter だけを実行し、image を
build/pull して resident container を起動した後、`docker exec` 経由で
`bootstrap_runtime.py` を実行します。Docker が無い場合は Host Python を import せず
typed `runtime_unavailable` を返します。

container-side controller は Docker lifecycle を所有しません。Host shell が固定
Docker transaction を完了してから controller を起動します。これにより container
は Docker socket、host `$HOME`、Git credential、network を持たずに
TOML/JSON/state/tool/check/eval を実行できます。Target は controller が
`mounts.tsv` の strict allowlist として出力し、Host shell が scope と destination を
検証して resident replacement の mount に反映します。

## Bootstrap Manifest

`bootstrap/host/manifest.toml` は image、container、runtime、skill、archive lease を
一つの lifecycle record へ結合します。`agent-canon-log` の branch、retention、
legacy import policy は log repository が所有し、Bootstrap は local spool、archive
checkout lease、publication receipt だけを所有します。

```toml
[container]
name_template = "agent-canon-tools"
max_instances = 1
cpus = 2
memory_bytes = 4294967296
pids_limit = 512
max_parallel_tasks = 2
task_timeout_seconds = 1800
termination_grace_seconds = 10
task_state_quota_bytes = 1073741824
task_log_quota_bytes = 104857600
runtime_quota_bytes = 2147483648
cache_quota_bytes = 4294967296
archive_lease_quota_bytes = 2147483648
idle_stop_seconds = 3600
max_image_generations = 2
network = "none"
labels = ["io.agent-canon.runtime=shared-v1", "io.agent-canon.control-root-digest"]

[skills]
strategy = "managed-links"
target = "runtime-root/codex-home/skills"

[archive]
remote = "git@github.com:iwashita-nozomu/agent-canon-log.git"
```

`tools/runtime/container/bootstrap_runtime.py` は container-side controller であり、Docker CLI/daemon の版、daemon
mode、buildx、context、host architecture、rootless/rootful、UID/GID を事前
検証しません。`DockerAdapter.run` の Docker command failure はその exit code と
stderr を結果に残します。`bootstrap/container/image/Dockerfile` と
`bootstrap/container/lifecycle/entrypoint.sh` の container process identity と UID/GID
mapping は Host/caller の責務であり、`tests/tools/test_bootstrap_container_contract.py`
で契約化しています。AgentCanon は user 作成、`--user` 指定、UID/GID readback を行いません。
container name と label
は同じ effective UID に対する共有 runtime を1個に制限します。環境 image は
`ghcr.io/iwashita-nozomu/agent-canon:env-<key>` で選び、key は
`bootstrap/container/image/environment_key.sh` が Dockerfile とその
`source=` bind inputs の Git tree identity から導出します。

`bootstrap/host/manifest.toml` は current、rollback、in-use、pre-existing、gc-eligible を区別します。
target add/remove が成功すると resident state owner は同じ
`agent-canon.rollback-plan.v1` を `rollback_generation` の image identity と
target mount snapshot から更新します。従って target だけが変わった世代も
Host rollback の一つの plan で復元でき、成功後は反対方向の plan を再生成して
同一 image の世代を切り替えられます。
runtime/cache/archive は 80% high-water mark で GC を開始し、completed かつ
unpinned な task/lease/cache を LRU で削除します。active、current、rollback、
unpublished spool は削除しません。image は current/rollback の2世代、container は
1個だけです。60分 idle で container を stop し、inspect absence と保持 state を
readback します。`docker system prune` は使用せず、manifest-owned exact ID
だけを削除します。pre-existing resource は削除対象外です。

## Container Image

`bootstrap/container/image/Dockerfile` は旧developer-containerの dependency planning / Python / Rust build 部分だけを再利用します。editor、post-create、GPU、
Compose、workspace lifecycle は移植せず、旧developer-container surfaceは削除します。

Image は digest-pinned Ubuntu 24.04 の一つの output image です。bootstrap package
transaction は一度だけ apt update を行い、manifest-owned dependency を同じ
dependency layer へ導入してから asset / materializer layer を作ります。
build-essential、curl、pipx、npm、`rustup-init` と
Cargo build の後、npm/pipx/build provider と cache を同じ layer で purge します。
runtime は Node runtime、Python 3.12、jq/tree、clangd、AgentCanon binary、pipx
venv launchers、dependency plan/receipts を保持しますが、npm executable や build
provider は保持しません。Docker cache mount は使用しません。

dependency plan / receipts は manifest の declared records と観測した Rust source
digest、exact Cargo.lock digest、binary digest/version を build provenance として
保存します。Rust source digest は手動の manifest expectation ではありません。
CI が image を build/load/run し、entrypoint health を検証します。canonical
install/sync/update は env key image を再利用し、source-only 更新では
source-mounted tool compile だけを writable cache に行います。Dockerfile または
その bind input が変わったときだけ新しい環境 image を作ります。

`bootstrap/container/image/Dockerfile` は次を必須にします。

```text
--read-only
--cap-drop=ALL
--security-opt=no-new-privileges
--network=none
--cpus=2
--memory=4g
--pids-limit=512
tmpfs /tmp
```

Python / Rust dependency は image に一度だけ入れ、project / task ごとの image、
container、venv、Cargo toolchain、volume を作りません。

Resident は AgentCanon source checkout を `/opt/agent-canon/source` に read-only
で、runtime state volume の cache を `/var/lib/agent-canon/cache` に writable
で mount します。source-mounted `tools/**/Cargo.toml` を走査する compile route
が必要な Rust tool だけを cache/bin に更新し、source-only 更新では environment
image を再構築しません。

## Mount Registry And Generation Transaction

allowlist に登録した exact root だけを mount します。`agent-canondevelop` parent
root は既定登録できますが、home / workspace 全体は登録しません。

target 追加は external `lifecycle.lock` の下で次の一 transaction とします。

```text
acquire lock
  -> state = maintenance_pending / task admission closed
  -> active_task_count == 0 readback
  -> canonical realpath / symlink / mode / collision validation
  -> old generation stop / absence readback
  -> candidate generation start
  -> health check
  -> exact mount readback
  -> current-generation atomic switch
  -> state = ready / task admission open
```

task launch も同じ `lifecycle.lock` の下で generation、task id、slot を予約し、
active count を increment してから lock を離します。`maintenance_pending`、
`quiescing`、`runtime_unavailable` では新規 task admission を拒否します。
target add は admission を閉じた後に active task が0になるまで待つか、
timeout で `mount_update_blocked` を返します。pointer/container/readback が完了する
まで admission を再開しません。

old stop が失敗した場合は pointer を変更せず `old_generation_stop_failed`
で停止します。candidate が health/readback に失敗した場合は candidate を
quarantineし、記録済み old manifest から old generation を再起動します。その
readback まで pointer は old のままです。old restart も失敗した場合は
`runtime_unavailable` とし、container absence、old/candidate quarantine、pointer の
三者を receipt に固定します。atomic switch 後に old stop は行いません。
active task がある場合は `mount_update_blocked` とし、container を変更しません。
これにより、candidate と old は同時に実行中になりません。

task ごとの cwd、TMPDIR、lock、report、log、receipt を分離します。timeout は30分、
cancel は SIGTERM 後10秒で SIGKILL とし、stale process / lock を task receipt と
照合して回収します。

rootless/rootful daemon の分岐や Docker capability preflight は持ちません。
Host-only state/lock/archive/Codex home は 0700 runtime root に残し、container
へは `container-runtime/` だけを rw bind します。この exchange は sticky
01777 とし、sanitized target registry と task I/O だけを置き、credential、Git
state、control manifest は置きません。container process identity は Host/caller
環境が決めます。

## Command Compatibility And Catalog Cutover

既存 Rust first-class command は維持します。

```bash
agent-canon docs check ...
agent-canon semantic-index ...
agent-canon structured-analysis ...
```

Python tool は flat executable を増やさず、次の namespace を使います。

```bash
agent-canon tool run <catalog-id> -- <args...>
```

catalog schema v2 は public Python / Rust command に対して次を型付きで持ちます。

```text
id, typed argv, runtime, execution_plane, cwd policy, env policy,
stdin/stdout/stderr policy, exit/signal policy, side_effect_policy, output_root
```

`tools/runtime/dispatch/tool_dispatch.py` は `tool-container` と
`read-only`、`external-artifact`、`explicit-target-write` を列挙値にします。
shell command string を dispatcher authority にしません。

public command inventory は command id、現行 entrypoint、help digest、parity fixture を
versioned fixture として固定します。Rust clap tree と public Python catalog から取得した
inventory に差分がある間は catalog v2 cutover を禁止します。

`tools/fixtures/tool_dispatch/public-command-parity.json` は public Python / Rust command の旧 direct route と新 dispatcher route の
argv、cwd、stdout、stderr、exit code、signal、written paths の parity fixture を
作ります。`tools/fixtures/tool_dispatch/public-command-parity.json` が通らない entry は旧 route を維持し、cutover しません。全 internal
Python file を自動的に public catalog 化しません。

## Shell/Container Adapter Registry

Bootstrap v1 の Host adapter operation は次の enum だけです。

```text
docker.image.ensure
docker.image.inspect
docker.image.remove-owned
docker.container.create
docker.container.start
docker.container.stop
docker.container.remove-owned
docker.container.inspect
git.target.head
git.target.status
git.archive.clone
git.archive.fetch
git.archive.commit
git.archive.push
git.archive.readback
embedding.https.request
```

Issue/PR/comment など GitHub 操作は Bootstrap の authority に含めず、Host workflow
の GitHub owner が実行します。上記の Docker/Git 操作は Host shell が実行し、
`tools/runtime/container/bootstrap_runtime.py` は Docker argv を発行しません。Host
entrypoint はこの Python module を resident container の `docker exec` で起動し、
shell fragment ではなく固定された Docker argv と exact path を扱います。
receipt は operation、digest、byte count、exitだけを
保存し、secret、header、raw embedding payload を保存しません。
redaction test に canary secret を渡し、stdout/stderr/receipt/eval/spool の byte scan で
非流出を `tests/bootstrap/test_bootstrap_runtime.py` で確認します。

resident container は `network=none` を維持します。local embedding は container
内で実行し、remote embedding は `embedding.https.request` だけを使います。
呼び出しは `AGENT_CANON_EMBEDDING_ALLOWED_ENDPOINTS` の明示許可を必須とし、allowlisted HTTPS
endpoint/provider/model、data-egress purpose、source content digest、item/byte count を
receipt に残します。endpoint への raw `curl`、arbitrary URL、redirect、container
network は許可しません。

container/Host 間は runtime root 内の task-scoped request/response directory を使い、
schema、owner UID、mode 0600、nonce、deadline、request digest を照合します。
`embedding.rs` の remote-provider raw `curl` は request envelope 書込みと
response digest readback へ置換し、Host adapter が HTTPS を実行します。
stale/replayed/mismatched response は受理しません。

## Mutation Capability

`tools/runtime/container/bootstrap_runtime.py` は分析を read-only mount で実行します。docs / memory / materializer など
意図的な mutation は target root、allowed paths、purpose、authority、before/after、
receipt を `tools/runtime/container/bootstrap_runtime.py` で必須にします。runtime output を source mutation として扱いません。

`RuntimeArtifactBoundary` は implicit output が source root 内なら拒否し、external
rootへ atomic writeします。`__pycache__`、Cargo target、SQLite、event spool、eval、
dashboard、report、tmp、cache を対象にします。archive transaction の spool/control
だけは `runtime_spool_boundary` という別 capability で、external runtime または
bootstrap が所有する正確な `<source>/.runtime` の `locks/` と `spool/` に限定して
許可します。source の
他の子、別 runtime root、symlink、`.runtime/archive/` は引き続き拒否し、archive/report
出力は明示的な external archive clone に限定します。

## Skill Installation

Bootstrap の `codex prepare` は global `$CODEX_HOME` を変更せず、明示 runtime
root 内の `codex-home/` に skills、agents、hooks、config の verified
manifest-managed link を作ります。resident は image 内の canonical source を
検証しますが、container-control の host projection root を使って link target を
live AgentCanon checkout の `<install-root>/.codex/...` にします。従って host
Codex が読む config は `CODEX_HOME/config.toml`、skills/agents はそれぞれの
runtime-local surface から live checkout を参照します。加えて、control root に `$HOME` を明示した
install/update は `~/.agents/skills` を AgentCanon checkout 内の ignored な
`~/.codex/personal/skills` へディレクトリ単位でリンクし、`~/.codex/agents/<role>.toml` と
`~/.codex/config.toml` は個別に管理します。最後のリンク先は AgentCanon checkout
内の ignored な personal source で、既存の regular config は bytes と mode を保持
して移行し、uninstall で regular file に戻します。hooks、認証、session、history、
cache、plugin、rule、MCP、TUI/trust はこの投影に含めません。skills は個別列挙・digest・
expected-target readback を行わず、旧farmをディレクトリlinkへ置換します。uninstall は
その AgentCanon-owned directory link だけを削除します。Host shell が global link を
所有し、resident Python はこの投影を書きません。

`bootstrap.sh ... codex --project-root <path>` は process-local にこの isolated
`CODEX_HOME` を指定して project root で Codex を起動します。Template に
`.codex`、symlink、vendor source を materialize しません。AgentCanon clone から
Codex を起動することも要求しません。install/update 後は現在 session が
自動更新されないことを表示し、launcher が開く新 session で skill/agent/hook/config
inventory と link target を readback します。

`tools/runtime/container/bootstrap_runtime.py` は isolated Codex homeのskill/agent surfaceを cross-repository
discovery entry とし、project-local `AGENTS.md` は親 repository の責務のままと
する Codex discovery model を前提にします。

## Eval Collection And agent-canon-log

既存 producer、`run_accumulated_agent_evals.py`、`runtime_log_paths.py`、
`runtime_log_archive_git.py` を再利用し、第二 publisher を作りません。

`eval collect` は tool container で producer を実行し、外部 runtime root に
`agent_canon.eval_collection.v1` receiptを作ります。run id、task id、source repository、
source HEAD、AgentCanon commit/tool digest、family status、metrics、timestamp、
`source_tree_unchanged` を必須にします。

`eval sync` はresidentで collection と世代を検証して body-free な TSV requestだけを
external spoolへ書き、Host shell adapterが target mount を実パスへ解決して既存の
archive ownerへ渡します。residentからは network、credentials、archive checkoutへ
到達できません。network / archive unavailable時はspoolとfailure receiptを保持し、
source treeを汚しません。non-force push後にremote ref/tree/blob digestをreadbackして
finalizeします。`exec` 成功後の private feedback sync も同じく resident は request
だけを作り、Host shellが credentialed adapterを一度だけ実行します。

`sync` は候補 checkout、remote-ref照合、local build、source rollback、二つ目のlockを
持ちません。image取得に失敗した場合は旧residentを停止せず、resident更新に失敗した
場合もGitは戻しません。rollbackは既存resident state ownerのrollbackだけを対象にします。

local bare remoteを使い、collect -> spool -> clone -> commit -> push -> fetch ->
ref/tree/blob readback -> duplicate no-op / conflict failureをE2E testします。

## Tracked Reports Migration

既存 `reports/` は generated runtime report、durable design evidence、canonical sourceを
分類します。runtime-generatedだけをarchiveし、file SHA256、archive commit、remote
blob readback後に別changeで削除します。design evidenceはcanonical documentかimmutable
archive referenceへ置換します。

全eval、hook、behavior、dashboard writerをexternal rootへ切り替えるまでtracked report
removalを開始しません。失敗時はsource fileとspoolを保持します。

## User Journey

正常系:

```text
bootstrap install
  -> start
  -> target add (zero active tasks; generation restart)
  -> status
  -> codex prepare
  -> codex launcher / isolated CODEX_HOME readback
  -> agent-canon tool run
  -> eval collect
  -> eval sync
  -> stop
  -> gc
  -> uninstall
```

README / QUICK_START は target collision、skill collision、Docker unavailable、runtime
unhealthy、archive publish failure、rollback、session restart、cleanup readbackを説明し、
`tests/bootstrap/test_bootstrap_runtime.py` のfresh fixtureで同じcommand列を検証します。

## Operation To State To Evidence

| Operation | Resulting state | Completion evidence |
| --- | --- | --- |
| `install` | verified image/manifest generation | image digest, manifest fingerprint |
| `update` | current checkout reconciled in existing v2 lifecycle | ordinary Docker result and existing state/container readback |
| `start` | exactly one healthy container | inspect, limits, mounts, generation |
| `target add` | new mount generation active | lock, zero tasks, health, mount readback |
| `tool run` | typed catalog dispatch | `tools/runtime/dispatch/tool_dispatch.py` receipt |
| `template export` | external template bundle exported | container-plane receipt and bundle provenance |
| `codex prepare` | isolated managed surfaces active | collision result, link/digest/readback |
| `eval collect` | external eval bundle complete | producer matrix, source unchanged |
| `eval sync` | archive commit published | branch/commit/ref/tree/blob readback |
| `rollback` | previous verified generation active | current/rollback pointer readback |
| `stop` | container absent, state retained | inspect absence |
| `gc` | exact stale owned Docker state absent; resident state/cache/lease GC complete | exact IDs/refs, foreign resources and active/rollback identities retained |
| `uninstall` | owned runtime/skills absent | absence readback; user roots unchanged |

## Side-Effect Map (`tools/runtime/container/bootstrap_runtime.py`)

| Surface (`tools/runtime/container/bootstrap_runtime.py`) | Owner | Allowed write |
| --- | --- | --- |
| AgentCanon source | explicit mutation operation | allowed target only |
| runtime root | Bootstrap | task state, receipts, spool, archive lease |
| cache root | Bootstrap | bounded dependency/tool cache |
| runtime-root `codex-home` | Bootstrap Codex manifest | managed links only |
| Docker | Host adapter | manifest-owned image/container only |
| target/archive Git | Host adapter | typed registry operation only |
| GitHub Issue/PR | Host workflow owner | Bootstrap authority なし |
| agent-canon-log | log repository policy | append-only branch/tree |
| project execution | project owner | AgentCanon does not execute it |

## Implementation Write Set

新規:

```text
bootstrap.sh
bootstrap/host/manifest.toml
bootstrap/container/image/Dockerfile
bootstrap/container/lifecycle/entrypoint.sh
bootstrap/container/image/dependencies.toml
bootstrap/lib/*.sh
tools/runtime/container/bootstrap_runtime.py
tools/runtime/artifacts/runtime_artifacts.py
tools/runtime/dispatch/tool_dispatch.py
documents/runtime/bootstrap-runtime.md
tests/bootstrap/*
tests/agent_tools/test_runtime_artifacts.py
```

変更:

```text
README.md
CONTAINER_OPERATIONS.md
agents/USER_GUIDE_JA.md
agents/skills/agent-canon-update.md
agents/skills/catalog.yaml
tools/catalog.yaml
tools/bin/agent-canon
tools/runtime/container/devcontainer_dependencies.py
tools/runtime/archive/runtime_log_paths.py
tools/runtime/archive/runtime_log_archive_git.py
eval/producers/run_accumulated_agent_evals.py
eval/checkers/eval_accumulation_check.py
eval producer / dashboard / hook writers
tools/runtime/dispatch/agent-canon/src/main.rs
rust graph / semantic / structured-analysis output resolvers
documents/runtime/runtime-log-archive.md
documents/runtime/runtime-profiles-and-check-matrix.md
eval/definitions/skill_workflow_prompt_eval.toml
```

削除はBootstrap parity完了後:

```text
.devcontainer/**
AgentCanon devcontainer validator / workflow routing
source-local runtime default docs/tests
```

## Validation

- shell syntax、Python compile/type/static checks、Rust build/test。
- runtime path、archive、eval producer、catalog dispatcherのfocused unit tests。
- one image build、one resident containerでblack-box / concurrency / resource tests。
- two independent project fixtureを一つのcontrol rootへ登録し、container ID/image digest
  が同一でcontainerが1個だけであるE2E。第二control rootからの作成は拒否。
- task launch と target add を barrier で競合させ、maintenance admission close 後に
  task reservation が増えず、active zero/readback 前に old stop しない concurrency test。
- `tests/bootstrap/test_bootstrap_runtime.py` でsource read-only mountとsource tree before/after byte/status一致。
- public CLI parity matrix。
- local bare `agent-canon-log` publication E2E。
- install/start/status/codex/tool/eval/stop/gc/uninstall fresh journey。
- container/image/lock/tmp cleanup、system prune不使用。

## Evidence And Assumption Ledger

| Kind | Statement | Evidence / disposition |
| --- | --- | --- |
| evidence | lifecycle and cleanup behavior | `tests/bootstrap/test_bootstrap_runtime.py` |
| evidence | image and typed entrypoint | `tests/tools/test_bootstrap_container_contract.py` |
| evidence | catalog parity | `tools/fixtures/tool_dispatch/public-command-parity.json` |
| evidence | eval archive publication | `tests/agent_tools/test_runtime_log_archive_git.py` |
| boundary | Docker build/runtime capability | Docker CLI/daemon is a host capability; AgentCanon reports Docker exit/stderr and does not preflight host architecture or UID/GID |
| assumption | remote embedding authority | `AGENT_CANON_EMBEDDING_ALLOWED_ENDPOINTS` is explicit and empty by default |

## Reviewer Finding Closure

Design and implementation findings are tracked in repository-qualified
`iwashita-nozomu/agent-canon#841`; validation rechecks only evidence invalidated by the current diff.
