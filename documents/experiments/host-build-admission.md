# Host compiler/linker admission

<!--
@dependency-start
contract design
responsibility Defines host native-build admission, bounded own-tree supervision, persistent evidence and no-rerun closure.
upstream implementation ../../tools/experiments/execution/execution_resource_plan.py canonical shared runtime identity and lock namespace
upstream design ./gpu-direct-command.md independent GPU admission and existing no-kill GPU lifecycle
upstream design ../../CONTAINER_OPERATIONS.md selected execution environment ownership
downstream implementation ../../tools/experiments/execution/host_build_admission.py narrow host-build adapter
downstream implementation ../../tests/tools/test_host_build_admission.py synthetic refusal and lifecycle fixtures
downstream design ../../agents/skills/cpp-review.md native build execution reader
@dependency-end
-->

## Boundary

GPU admission does not admit compiler, Enzyme or linker host memory. Native build
execution uses the host-build adapter in the existing execution package. It reuses
[`execution_resource_plan.py`](../../tools/experiments/execution/execution_resource_plan.py)'s shared runtime provenance and lock namespace; it does
not add a scheduler, resource database, environment bootstrapper, GPU policy or
consumer build graph. The GPU direct adapter's no-signal descendant-retention
contract is unchanged. A successful host build is not GPU/experiment validation.

The adapter launches a local native command in the **already selected** build
execution environment. It does not create containers, launch daemons, enable
controllers, switch Docker contexts, retry a failed probe, or move to an unrestricted
host. Environment/image selection and cgroup delegation remain with their existing
owners. Remote compiler farms, daemon-launched build workers and nested container
build commands are not this local descendant-tree route.

A current user prohibition on workload execution overrides every validation recipe.
Do not turn a prohibited workload into a smaller dimension, shorter run, different
target or renamed command and call that a fixture. `--execute` is used only with
current execution authority; `--rerun-prohibited` wins even when both are present.
A previous task/comment's permission is not authority for a new task.

## Admission and containment

Use the existing provision/readback receipts and the canonical
`/var/lib/agent-canon/runtime` host directory. Both receipt paths are explicit inputs
from the existing runtime provisioner, not newly manufactured assertions. Device /
inode readback and the canonical source/target paths must agree. A task-specific
runtime root, symlink, `/tmp`, `/run`, tmpfs or container overlay is not a substitute.
The accepted persistent filesystems are ext4, xfs, btrfs and zfs; unknown placement
fails closed rather than silently storing evidence in an ephemeral directory.

All sessions using this host-build route take the same nonblocking
`locks/host-build.lock` for the entire operation. The conservative initial policy is
**one host-heavy native build at a time**, not multiple independent free-memory
snapshots. No queue or reservation database is introduced. A durable
`locks/host-build.active` marker is created before launch and removed only after
quiescence and a durable end event. A crash, failed proof or incomplete preflight
can leave it behind: subsequent requests refuse, without automatic stale cleanup
or workload replay. An operator must establish quiescence and preserve the evidence
before clearing an interrupted lease; cleanup is not a retry authorization.

The selected local Docker endpoint and its previously bound daemon ID are explicit.
Fresh `docker info` must report that ID, cgroup v2, and a real systemd/cgroupfs driver.
`CgroupDriver=none`, v1, an unreadable endpoint or a different daemon ID refuses.
Requested Docker flags are never used as evidence of effective limits.

A pre-existing delegated **domain** parent cgroup must have `memory`, `cpu`, `pids`
in `cgroup.subtree_control` and finite memory/swap/CPU/pids limits. The cgroup2 mount
must expose the host-root path so `/proc/PID/cgroup` can be checked exactly. The
adapter does not grant delegation to itself. A private child cgroup is created for
this run, with finite `memory.max`, `cpu.max`, `pids.max` and `memory.swap.max=0`.
Missing files, `max`, malformed values, inaccessible pressure/procfs, or mismatched
readback refuse. A writable `cgroup.kill` is required before any build is released.

Let `j` be the requested worker count, `W` the justified conservative per-worker
memory bound, `F` the fixed build/link overhead, `B` the hard memory cap, `R` host
headroom, `A` current host `MemAvailable`, and `L-C` remaining parent-cgroup memory.
Admission requires:

```text
j * W + F <= B <= min(A - R, L - C)
j * cpu_period <= parent_cpu_quota
requested_pids <= parent_pids_max - parent_pids_current
```

All byte units are explicit. `W`, `F` and `R` are selected from the current build's
engineering evidence; this adapter does not invent universal compiler-memory
constants. CMake/Make/Ninja receive exactly the selected parallelism, and conflicting
CLI job controls or inherited Make job flags are not accepted as a second policy.
Direct compiler/linker and CMake configure/try_compile invocations require one worker. Consumer target definitions,
Ninja pools, optimization flags and Enzyme expressions are not rewritten here.

A fresh child is initially a tiny, isolated Python gate, **not the build**. It is
placed in the private cgroup; effective membership/limits, host headroom, selected
daemon and durable start evidence are read back before the gate opens. The build
then replaces the gate with `exec`, without a shell transport or a daemon launch.
Parent limits and child limits are checked throughout execution.

## Autonomous stop and evidence

The watchdog is a separate session/process outside the build's private cgroup. It
must acknowledge readiness before release. It has only inherited descriptors for
its control pipe, private kill target and host journal, not authority to enumerate
or signal arbitrary processes. It stops the private cgroup on the total deadline,
parent/control-pipe loss, or **10 seconds without a successfully flushed monitoring
heartbeat**. The Docker probe is bounded to 5 seconds. These are autonomous bounds,
not promises that a stalled kernel or storage device can always schedule user space
at an exact instant.

Stop precedes error logging. Kernel `cgroup.kill` covers descendants even when a
child creates another process group/session; no `pkill`, process-name matching or
host-wide kill is used. A never-released gate whose placement failed can only be
stopped through its own unreaped `Popen` identity. The host slot is not recycled when
`cgroup.events: populated=0` cannot be proven. Unkillable kernel tasks or a failed
quiescence readback remain interrupted evidence, not successful cleanup.

Each `host-build-<unique-id>/` directory contains private `events.jsonl`, `stdout.log`
and `stderr.log`. Before release and on every successful sample, the journal is
flushed/fsynced; directory creation and terminal removal of the active marker are
also fsynced. Records include command, cwd, budget, effective limits, PID/cgroup,
wall/monotonic timestamps, host memory/swap, cgroup memory/swap, both memory-pressure
observations, stop reason and raw exit code. Logs are present on the host from the
start, not exported only when a container exits. Do not publish raw commands with
secrets, unrelated host process inventories or journals to GitHub.

`journal_status` reports success only for a complete `end` event with reason
`exited` and exit code zero. A missing/torn terminal record means **interrupted**.
A signal return code or missing log does not establish OOM or the WSL crash cause.

Serialization covers cooperating native builds on the shared host namespace. Other
host processes are included in `MemAvailable`/pressure and can trigger a reserve
stop, but this adapter cannot reserve their future allocations or guarantee host
survival against arbitrary uncooperative tasks. Their workload owners and #1097
are not silently absorbed into this Issue.

## Invocation and acceptance

When current workload execution is authorized, invoke the existing execution
package from the selected source checkout, supplying values from the selected
runtime and the current build plan:

```text
python3 -m tools.experiments.execution.host_build_admission \
  --provision-receipt <existing-provision-receipt> \
  --readback-receipt <existing-readback-receipt> \
  --docker-host <selected-unix-endpoint> --daemon-id <bound-daemon-ID> \
  --parent-cgroup <delegated-bounded-parent> --cwd <consumer-root> \
  --memory-bytes <B> --workers <j> --worker-memory-bytes <W> \
  --fixed-memory-bytes <F> --reserve-bytes <R> --pids <limit> \
  --timeout-seconds <finite-deadline> --execute \
  -- cmake --build <consumer-build-tree>
```

The adapter adds the parallel flag; do not append another one or use a shell/remote
wrapper. Missing runtime prerequisites are a refusal and operator handoff, never
permission to bootstrap another daemon or fall back to bare `cmake --build`.
This is the prescribed native execution route, not a sandbox for malicious build
scripts or a new general-purpose shell parser in the lifecycle hooks.

Fixture-only verification is:

```text
python3 -m pytest tests/tools/test_host_build_admission.py -q
```

The suite uses synthetic proc/cgroup files, fake daemon responses, a mocked native
child, real harmless pipe/watchdog subprocesses, and a separate lock contender.
It does not invoke Clang, Enzyme, Docker, training or a GPU workload. Real rootless
WSL delegation, shared-bind identity, kernel cgroup actuation and host persistence
across a WSL interruption require separate environment evidence. When workload
replay is prohibited, leave those claims `need verification`; do not perform the
crashed or a reduced workload to close them. Repository-required CI remains a
separate exact-head check, not something fixture success can replace.

## Mechanism references

- [Linux cgroup v2: core interface, delegation and controllers](https://docs.kernel.org/admin-guide/cgroup-v2.html)
- [Docker rootless: limiting resources and effective cgroup driver](https://docs.docker.com/engine/security/rootless/tips/#limiting-resources)

These explain kernel/daemon semantics; they do not add another AgentCanon policy owner.
