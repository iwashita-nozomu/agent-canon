# AgentCanon Bootstrap And Tool Runtime
<!--
@dependency-start
contract design
responsibility Defines the host bootstrap, shared AgentCanon tool runtime, external artifact boundary, skill installation, eval publication, and migration contract.
upstream design ../../README.md standalone AgentCanon source entrypoint and user journey
upstream design ../runtime/runtime-log-archive.md agent-canon-log publication and append-only archive policy
upstream design ../../agents/skills/agent-canon-update.md AgentCanon source and parent integration workflow
upstream implementation ../../tools/agent_tools/devcontainer_dependencies.py reusable dependency planning and image installation logic
upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py existing archive publication owner
downstream implementation ../../bootstrap.sh host bootstrap entrypoint
downstream implementation ../../bootstrap/container/Dockerfile shared Python and Rust tool image
downstream implementation ../../tools/agent_tools/bootstrap_runtime.py resident container lifecycle and mount registry
downstream implementation ../../tools/agent_tools/runtime_artifacts.py external runtime artifact boundary
downstream implementation ../../tools/agent_tools/tool_dispatch.py catalog-namespaced Python and Rust dispatcher
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
- runtime、cache、eval、report、archive clone は AgentCanon source tree 外に置く。
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

implicit な Host-global 既定値は持ちません。Bootstrap は `--control-parent-root` と
`--runtime-root` を必須とし、runtime root が宣言された control-plane owner
repository の
realpath 配下にある場合だけ実行します。symlink で外へ逃がす指定も
拒否します。`$HOME/.local`、`$HOME/.cache`、AgentCanon source tree を
fallback にしません。

control-plane root は installation に一つだけで、project root ではありません。
複数 project は同じ `mounts.toml` に target として登録し、同じ container ID
と image digest を使います。新しい control root から二個目を作らず、
Docker label readback で既存 owner を検出し、`shared_runtime_owned_elsewhere` と
既存 control root の明示指定を返します。

```text
<control-parent-root>/workspace/agent-canon-runtime/<installation-id>/
  current-generation
  rollback-generation
  lifecycle.lock
  mounts.toml
  codex-home/
  tasks/<task-id>/{tmp,locks,reports,logs,receipts}
  container-runtime/  # 01777 exchange only; no control state or credentials
  spool/
  archive/agent-canon-log/

<runtime-root>/cache/{cargo,pycache,semantic-index,tool-metadata}/
```

AgentCanon source内を runtime default にしません。`tools/agent_tools/runtime_artifacts.py` により分析 tool は source read-only、telemetry は external root、
mutation tool は明示 target capability を受けた場合だけ source を変更します。

## Top-Level Bootstrap

唯一の入口は repository top-level `bootstrap.sh` です。

```bash
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> install
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> start
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> status
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> target add --root <project-a> --mode read-only
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> target add --root <project-b> --mode read-only
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> exec --root <path> -- <existing-command...>
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> tool run <catalog-id> -- <args...>
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> codex prepare
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> codex --project-root <path>
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> eval collect --root <path> --run-id <id>
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> eval sync --run-id <id>
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> stop
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> rollback
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> gc
./bootstrap.sh --control-parent-root <path> --runtime-root <path>/workspace/agent-canon-runtime/<id> uninstall
```

Bootstrap は Docker が無い場合に Host Python / Cargo install へ fallback せず、
typed `runtime_unavailable` を返します。

## Bootstrap Manifest

`bootstrap/manifest.toml` は image、container、runtime、skill、archive lease を
一つの lifecycle record へ結合します。`agent-canon-log` の branch、retention、
legacy import policy は log repository が所有し、Bootstrap は local spool、archive
checkout lease、publication receipt だけを所有します。

```toml
[container]
name_template = "agent-canon-tools-<effective-uid>"
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
labels = ["io.agent-canon.runtime=shared-v1", "io.agent-canon.owner-uid", "io.agent-canon.control-root-digest"]

[skills]
strategy = "managed-links"
target = "runtime-root/codex-home/skills"

[archive]
remote = "git@github.com:iwashita-nozomu/agent-canon-log.git"
```

Bootstrap は Host の effective UID や Docker daemon が rootless かどうかを判定しません。
container process だけを manifest の非root UID/GID で実行し、Host UIDが0の
場合は安全な非root既定UID/GIDを使います。container name
と label は同じ effective UID に対する共有 runtime を1個に制限し、
control-root digest と manifest digest が一致しない adopt を拒否します。

`bootstrap/manifest.toml` は current、rollback、in-use、pre-existing、gc-eligible を区別します。
runtime/cache/archive は 80% high-water mark で GC を開始し、completed かつ
unpinned な task/lease/cache を LRU で削除します。active、current、rollback、
unpublished spool は削除しません。image は current/rollback の2世代、container は
1個だけです。60分 idle で container を stop し、inspect absence と保持 state を
readback します。`docker system prune` は使用せず、manifest-owned exact ID
だけを削除します。pre-existing resource は削除対象外です。

## Container Image

`bootstrap/container/Dockerfile` は旧developer-containerの dependency planning / Python / Rust build 部分だけを再利用します。editor、post-create、GPU、
Compose、workspace lifecycle は移植せず、旧developer-container surfaceは削除します。

`bootstrap/container/Dockerfile` は次を必須にします。

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

rootless/rootful daemon の分岐は持ちません。Host-only state/lock/archive/Codex home は
0700 runtime root に残し、container へは `container-runtime/` だけを rw bind します。
この exchange は sticky 01777 とし、sanitized target registry と task I/O だけを置き、
credential、Git state、control manifest は置きません。container UID は常に非rootです。

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

`tools/agent_tools/tool_dispatch.py` は `tool-container` と
`read-only`、`external-artifact`、`explicit-target-write` を列挙値にします。
shell command string を dispatcher authority にしません。

public command inventory は command id、現行 entrypoint、help digest、parity fixture を
versioned fixture として固定します。Rust clap tree と public Python catalog から取得した
inventory に差分がある間は catalog v2 cutover を禁止します。

`tools/fixtures/tool_dispatch/public-command-parity.json` は public Python / Rust command の旧 direct route と新 dispatcher route の
argv、cwd、stdout、stderr、exit code、signal、written paths の parity fixture を
作ります。`tools/fixtures/tool_dispatch/public-command-parity.json` が通らない entry は旧 route を維持し、cutover しません。全 internal
Python file を自動的に public catalog 化しません。

## Typed Host Adapter Registry

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
の GitHub owner が実行します。`tools/agent_tools/bootstrap_runtime.py` の Host operationはargv listとexact pathで実行し、shell fragmentを拒否します。
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

`tools/agent_tools/bootstrap_runtime.py` は分析を read-only mount で実行します。docs / memory / materializer など
意図的な mutation は target root、allowed paths、purpose、authority、before/after、
receipt を `tools/agent_tools/bootstrap_runtime.py` で必須にします。runtime output を source mutation として扱いません。

`RuntimeArtifactBoundary` は implicit output が source root 内なら拒否し、external
rootへ atomic writeします。`__pycache__`、Cargo target、SQLite、event spool、eval、
dashboard、report、tmp、cache を対象にします。

## Skill Installation

Bootstrap は global `$CODEX_HOME` を変更しません。明示 runtime root 内の
`codex-home/` に skills、agents、hooks、config の verified manifest-managed link を
作ります。同名 pre-existing path は同一 managed digestだけをadoptし、その他は
fail-closedです。uninstall は自分が作ったlinkだけを削除します。receiptに
surface id、source commit/digest、target、created/pre-existing を記録します。

`bootstrap.sh ... codex --project-root <path>` は process-local にこの isolated
`CODEX_HOME` を指定して project root で Codex を起動します。Template に
`.codex`、symlink、vendor source を materialize しません。AgentCanon clone から
Codex を起動することも要求しません。install/update 後は現在 session が
自動更新されないことを表示し、launcher が開く新 session で skill/agent/hook/config
inventory、link target、source digest を readback します。

`tools/agent_tools/bootstrap_runtime.py` は isolated Codex homeのskill/agent surfaceを cross-repository
discovery entry とし、project-local `AGENTS.md` は親 repository の責務のままと
する Codex discovery model を前提にします。

## Eval Collection And agent-canon-log

既存 producer、`run_accumulated_agent_evals.py`、`runtime_log_paths.py`、
`runtime_log_archive_git.py` を再利用し、第二 publisher を作りません。

`eval collect` は tool container で producer を実行し、外部 runtime root に
`agent_canon.eval_collection.v1` receiptを作ります。run id、task id、source repository、
source HEAD、AgentCanon commit/tool digest、family status、metrics、timestamp、
`source_tree_unchanged` を必須にします。

`eval sync` はHost adapterでexternal spoolを既存archive ownerへ渡します。network /
archive unavailable時はspoolとfailure receiptを保持し、source treeを汚しません。
non-force push後にremote ref/tree/blob digestをreadbackしてfinalizeします。

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
| `start` | exactly one healthy container | inspect, limits, mounts, generation |
| `target add` | new mount generation active | lock, zero tasks, health, mount readback |
| `exec` | exact command completed | argv/cwd/I/O/exit/source before-after |
| `tool run` | typed catalog dispatch | `tools/agent_tools/tool_dispatch.py` receipt |
| `codex prepare` | isolated managed surfaces active | collision result, link/digest/readback |
| `eval collect` | external eval bundle complete | producer matrix, source unchanged |
| `eval sync` | archive commit published | branch/commit/ref/tree/blob readback |
| `rollback` | previous verified generation active | current/rollback pointer readback |
| `stop` | container absent, state retained | inspect absence |
| `gc` | eligible owned state absent | exact IDs/paths/bytes, active retained |
| `uninstall` | owned runtime/skills absent | absence readback; user roots unchanged |

## Side-Effect Map (`tools/agent_tools/bootstrap_runtime.py`)

| Surface (`tools/agent_tools/bootstrap_runtime.py`) | Owner | Allowed write |
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
bootstrap/manifest.toml
bootstrap/container/Dockerfile
bootstrap/container/entrypoint.sh
bootstrap/container/dependencies.toml
bootstrap/lib/*.sh
tools/agent_tools/bootstrap_runtime.py
tools/agent_tools/runtime_artifacts.py
tools/agent_tools/tool_dispatch.py
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
tools/agent_tools/devcontainer_dependencies.py
tools/agent_tools/runtime_log_paths.py
tools/agent_tools/runtime_log_archive_git.py
tools/agent_tools/run_accumulated_agent_evals.py
tools/agent_tools/eval_accumulation_check.py
eval producer / dashboard / hook writers
rust/agent-canon/src/main.rs
rust graph / semantic / structured-analysis output resolvers
documents/runtime/runtime-log-archive.md
documents/runtime/runtime-profiles-and-check-matrix.md
evidence/agent-evals/skill_workflow_prompt_eval.toml
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
| assumption | Docker platform | `bootstrap/manifest.toml` explicitly supports `linux/amd64`; other platforms fail typed preflight |
| assumption | remote embedding authority | `AGENT_CANON_EMBEDDING_ALLOWED_ENDPOINTS` is explicit and empty by default |

## Reviewer Finding Closure

Design and implementation findings are tracked in repository-qualified
`iwashita-nozomu/agent-canon#841`; validation rechecks only evidence invalidated by the current diff.
